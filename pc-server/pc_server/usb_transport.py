"""Reconnectable PSPLink/USBHostFS bulk transport for wired controller input."""

from __future__ import annotations

import logging
import struct
import threading
from collections.abc import Callable
from typing import Protocol

LOGGER = logging.getLogger(__name__)

PSP_USB_VENDOR_ID = 0x054C
PSP_USB_PRODUCT_ID = 0x01C9
USBHOSTFS_MAGIC = 0x782F0812
USBHOSTFS_ASYNC_MAGIC = 0x782F0813
USBHOSTFS_ASYNC_CHANNEL = 4
USBHOSTFS_COMMAND_ENDPOINT = 0x02
USBHOSTFS_ASYNC_ENDPOINT = 0x03
USBHOSTFS_INPUT_ENDPOINT = 0x81
USBHOSTFS_READ_SIZE = 512
USBHOSTFS_HEADER = struct.Struct("<II")
USBHOSTFS_COMMAND_HEADER = struct.Struct("<III")
USBHOSTFS_HELLO_COMMAND = 0x8FFC0000
USBHOSTFS_PROBE = struct.pack("<I", USBHOSTFS_MAGIC)
USBHOSTFS_HELLO = USBHOSTFS_COMMAND_HEADER.pack(
    USBHOSTFS_MAGIC,
    USBHOSTFS_HELLO_COMMAND,
    0,
)
USBHOSTFS_HANDSHAKE_ATTEMPTS = 10


class UsbUnavailableError(RuntimeError):
    """The optional USB runtime or a compatible driver is unavailable."""


class UsbDriverAccessError(UsbUnavailableError):
    """WinUSB is bound, but Windows did not expose an openable interface."""


class UsbDisconnectedError(RuntimeError):
    """The active USB device disappeared or stopped responding."""


class UsbDevice(Protocol):
    def write(self, endpoint: int, data: bytes, timeout_ms: int) -> int: ...

    def read(self, endpoint: int, size: int, timeout_ms: int) -> bytes: ...

    def close(self) -> None: ...


class UsbBackend(Protocol):
    def open(self) -> UsbDevice | None: ...


class PyUsbDevice:
    def __init__(self, device: object, usb_util: object) -> None:
        self._device = device
        self._usb_util = usb_util
        self._close_lock = threading.Lock()
        self._closed = False

    def write(self, endpoint: int, data: bytes, timeout_ms: int) -> int:
        try:
            return int(self._device.write(endpoint, data, timeout=timeout_ms))
        except Exception as exc:
            raise UsbDisconnectedError(str(exc)) from exc

    def read(self, endpoint: int, size: int, timeout_ms: int) -> bytes:
        try:
            return bytes(self._device.read(endpoint, size, timeout=timeout_ms))
        except Exception as exc:
            # PyUSB uses backend-specific exception classes. Error 110/ETIMEDOUT
            # and the common libusb timeout text are normal polling timeouts.
            if (
                getattr(exc, "errno", None) in {60, 110, 116}
                or "timed out" in str(exc).lower()
            ):
                return b""
            raise UsbDisconnectedError(str(exc)) from exc

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            try:
                self._usb_util.dispose_resources(self._device)
            except Exception:
                LOGGER.debug(
                    "Could not release PSP USB resources",
                    exc_info=True,
                )


class PyUsbBackend:
    """Open the USBHostFS device through PyUSB when it is installed."""

    def open(self) -> UsbDevice | None:
        try:
            import libusb_package  # type: ignore[import-not-found]
            import usb.util  # type: ignore[import-not-found]
        except ImportError as exc:
            raise UsbUnavailableError(
                "USB runtime is not installed in this build"
            ) from exc

        try:
            device = libusb_package.find(
                idVendor=PSP_USB_VENDOR_ID,
                idProduct=PSP_USB_PRODUCT_ID,
            )
        except Exception as exc:
            raise UsbUnavailableError(
                "USB runtime could not enumerate devices"
            ) from exc
        if device is None:
            return None

        try:
            device.set_configuration()
            usb.util.claim_interface(device, 0)
        except Exception as exc:
            usb.util.dispose_resources(device)
            try:
                from .winusb_setup import winusb_interface_needs_repair

                needs_repair = winusb_interface_needs_repair()
            except Exception:
                LOGGER.debug(
                    "Could not inspect WinUSB interface registration",
                    exc_info=True,
                )
                needs_repair = False
            if needs_repair:
                raise UsbDriverAccessError(
                    "PSP USB device was found but its WinUSB interface "
                    "is not registered"
                ) from exc
            raise UsbUnavailableError(
                "PSP USB device was found but could not be opened"
            ) from exc
        return PyUsbDevice(device, usb.util)


def decode_async_payload(data: bytes) -> bytes | None:
    """Return channel-4 payload from one USBHostFS async transfer."""
    if len(data) < USBHOSTFS_HEADER.size:
        return None
    magic, channel = USBHOSTFS_HEADER.unpack_from(data)
    if magic != USBHOSTFS_ASYNC_MAGIC or channel != USBHOSTFS_ASYNC_CHANNEL:
        return None
    return data[USBHOSTFS_HEADER.size :]


def encode_async_payload(data: bytes) -> bytes:
    return (
        USBHOSTFS_HEADER.pack(
            USBHOSTFS_ASYNC_MAGIC,
            USBHOSTFS_ASYNC_CHANNEL,
        )
        + data
    )


def _is_usbhostfs_async_frame(data: bytes) -> bool:
    return (
        len(data) >= USBHOSTFS_HEADER.size
        and USBHOSTFS_HEADER.unpack_from(data)[0] == USBHOSTFS_ASYNC_MAGIC
    )


def _reply_to_usbhostfs_hello(device: UsbDevice, data: bytes) -> None:
    if len(data) != len(USBHOSTFS_HELLO):
        raise UsbDisconnectedError(
            f"invalid USBHostFS HELLO size: {len(data)}"
        )
    magic, command, extra_length = USBHOSTFS_COMMAND_HEADER.unpack(data)
    if (
        magic != USBHOSTFS_MAGIC
        or command != USBHOSTFS_HELLO_COMMAND
        or extra_length != 0
    ):
        raise UsbDisconnectedError("invalid USBHostFS HELLO response")
    if device.write(
        USBHOSTFS_COMMAND_ENDPOINT,
        USBHOSTFS_HELLO,
        1000,
    ) != len(USBHOSTFS_HELLO):
        raise UsbDisconnectedError("short USBHostFS HELLO write")


def perform_usbhostfs_handshake(device: UsbDevice) -> bytes | None:
    """Connect HostFS and preserve a frame from an already active session."""
    # USBHostFS remains connected if the Windows process closes while the
    # cable stays inserted. In that state the PSP is usually blocked on its
    # next async IN transfer, so consume it instead of sending a second probe.
    existing_data = device.read(
        USBHOSTFS_INPUT_ENDPOINT,
        USBHOSTFS_READ_SIZE,
        100,
    )
    if existing_data:
        if _is_usbhostfs_async_frame(existing_data):
            return existing_data
        _reply_to_usbhostfs_hello(device, existing_data)
        return None

    if device.write(
        USBHOSTFS_COMMAND_ENDPOINT,
        USBHOSTFS_PROBE,
        1000,
    ) != len(USBHOSTFS_PROBE):
        raise UsbDisconnectedError("short USBHostFS probe write")

    for _attempt in range(USBHOSTFS_HANDSHAKE_ATTEMPTS):
        data = device.read(
            USBHOSTFS_INPUT_ENDPOINT,
            USBHOSTFS_READ_SIZE,
            250,
        )
        if not data:
            continue
        _reply_to_usbhostfs_hello(device, data)
        return None

    raise UsbDisconnectedError("USBHostFS HELLO timed out")


class UsbPacketSource:
    """Reconnectable USB source that presents complete protocol packets."""

    def __init__(
        self,
        on_packet: Callable[[bytes, Callable[[bytes], None]], None],
        *,
        on_connected: Callable[[], None] | None = None,
        on_disconnected: Callable[[], None] | None = None,
        backend: UsbBackend | None = None,
        driver_repair: Callable[[], bool] | None = None,
        reconnect_interval_s: float = 0.5,
    ) -> None:
        self._on_packet = on_packet
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._backend = backend or PyUsbBackend()
        self._driver_repair = driver_repair
        self._reconnect_interval_s = reconnect_interval_s
        self._stop_event = threading.Event()
        self._device_lock = threading.Lock()
        self._device: UsbDevice | None = None
        self._runtime_warning_logged = False
        self._driver_repair_attempted = False

    def request_stop(self) -> None:
        self._stop_event.set()
        with self._device_lock:
            device = self._device
            self._device = None
        if device is not None:
            device.close()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                device = self._backend.open()
            except UsbUnavailableError as exc:
                if (
                    isinstance(exc, UsbDriverAccessError)
                    and not self._driver_repair_attempted
                ):
                    self._driver_repair_attempted = True
                    repair = self._driver_repair
                    if repair is None:
                        from .winusb_setup import (
                            request_elevated_winusb_repair,
                        )

                        repair = request_elevated_winusb_repair
                    try:
                        repair()
                    except Exception:
                        LOGGER.exception(
                            "Could not start WinUSB interface registration"
                        )
                if not self._runtime_warning_logged:
                    LOGGER.info("USB mode unavailable: %s", exc)
                    self._runtime_warning_logged = True
                self._stop_event.wait(self._reconnect_interval_s)
                continue
            if device is None:
                self._stop_event.wait(self._reconnect_interval_s)
                continue

            self._runtime_warning_logged = False
            with self._device_lock:
                self._device = device
            try:
                first_data = perform_usbhostfs_handshake(device)
                LOGGER.info("PSP USB cable transport connected")
                if self._on_connected is not None:
                    self._on_connected()
                self._read_device(device, first_data=first_data)
            except UsbDisconnectedError:
                LOGGER.info("PSP USB cable transport disconnected")
            finally:
                with self._device_lock:
                    if self._device is device:
                        self._device = None
                device.close()
                if self._on_disconnected is not None:
                    self._on_disconnected()

    def _read_device(
        self,
        device: UsbDevice,
        *,
        first_data: bytes | None = None,
    ) -> None:
        def send_reply(payload: bytes) -> None:
            encoded = encode_async_payload(payload)
            written = device.write(
                USBHOSTFS_ASYNC_ENDPOINT,
                encoded,
                1000,
            )
            if written != len(encoded):
                raise UsbDisconnectedError("short USB async write")

        if first_data is not None:
            payload = decode_async_payload(first_data)
            if payload is not None:
                self._on_packet(payload, send_reply)

        while not self._stop_event.is_set():
            data = device.read(
                USBHOSTFS_INPUT_ENDPOINT,
                USBHOSTFS_READ_SIZE,
                200,
            )
            if not data:
                continue
            payload = decode_async_payload(data)
            if payload is not None:
                self._on_packet(payload, send_reply)
