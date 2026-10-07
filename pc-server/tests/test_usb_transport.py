from __future__ import annotations

import unittest
from unittest.mock import Mock

from pc_server.protocol import (
    InputPacket,
    decode_pairing_ack,
    encode_packet,
    parse_pairing_token,
)
from pc_server.receiver import TransportKind, UdpReceiver
from pc_server.usb_transport import (
    USBHOSTFS_ASYNC_CHANNEL,
    USBHOSTFS_COMMAND_ENDPOINT,
    USBHOSTFS_HELLO,
    USBHOSTFS_INPUT_ENDPOINT,
    USBHOSTFS_PROBE,
    PyUsbDevice,
    UsbDriverAccessError,
    UsbDisconnectedError,
    UsbPacketSource,
    decode_async_payload,
    encode_async_payload,
    perform_usbhostfs_handshake,
)


class UsbTransportTests(unittest.TestCase):
    def test_pyusb_close_is_idempotent(self) -> None:
        raw_device = Mock()
        usb_util = Mock()
        device = PyUsbDevice(raw_device, usb_util)

        device.close()
        device.close()

        usb_util.dispose_resources.assert_called_once_with(raw_device)

    def test_usbhostfs_handshake_replies_to_hello(self) -> None:
        class HelloDevice:
            def __init__(self) -> None:
                self.writes = []
                self.reads = iter((b"", USBHOSTFS_HELLO))

            def write(self, endpoint, data, timeout_ms):
                self.writes.append((endpoint, data, timeout_ms))
                return len(data)

            def read(self, endpoint, size, timeout_ms):
                self.assert_read = (endpoint, size, timeout_ms)
                return next(self.reads)

            def close(self):
                pass

        device = HelloDevice()

        first_data = perform_usbhostfs_handshake(device)

        self.assertIsNone(first_data)
        self.assertEqual(
            device.writes,
            [
                (USBHOSTFS_COMMAND_ENDPOINT, USBHOSTFS_PROBE, 1000),
                (USBHOSTFS_COMMAND_ENDPOINT, USBHOSTFS_HELLO, 1000),
            ],
        )
        self.assertEqual(
            device.assert_read,
            (USBHOSTFS_INPUT_ENDPOINT, 512, 250),
        )

    def test_usbhostfs_handshake_resumes_an_existing_session(self) -> None:
        existing_frame = encode_async_payload(b"first input packet")

        class ConnectedDevice:
            def __init__(self) -> None:
                self.writes = []

            def write(self, endpoint, data, timeout_ms):
                self.writes.append((endpoint, data, timeout_ms))
                return len(data)

            def read(self, _endpoint, _size, _timeout_ms):
                return existing_frame

            def close(self):
                pass

        device = ConnectedDevice()

        first_data = perform_usbhostfs_handshake(device)

        self.assertEqual(first_data, existing_frame)
        self.assertEqual(device.writes, [])

    def test_usbhostfs_handshake_rejects_async_data_before_hello(self) -> None:
        class UnexpectedDevice:
            def write(self, _endpoint, data, _timeout_ms):
                return len(data)

            def read(self, _endpoint, _size, _timeout_ms):
                return b"not a HELLO"

            def close(self):
                pass

        with self.assertRaisesRegex(
            UsbDisconnectedError,
            "invalid USBHostFS HELLO size",
        ):
            perform_usbhostfs_handshake(UnexpectedDevice())

    def test_async_channel_round_trip(self) -> None:
        payload = b"one complete controller packet"
        self.assertEqual(decode_async_payload(encode_async_payload(payload)), payload)

    def test_other_async_channel_is_ignored(self) -> None:
        value = bytearray(encode_async_payload(b"ignored"))
        value[4:8] = (USBHOSTFS_ASYNC_CHANNEL + 1).to_bytes(4, "little")
        self.assertIsNone(decode_async_payload(bytes(value)))

    def test_usb_uses_shared_routing_and_acks_without_entering_code(self) -> None:
        token = parse_pairing_token("ABCDE")
        snapshots = []
        acknowledgements = []
        receiver = UdpReceiver(
            "127.0.0.1",
            47999,
            on_packet=snapshots.append,
            pairing_token=None,
            require_pairing=True,
        )
        packet = encode_packet(
            InputPacket(
                sequence=7,
                buttons=0x10,
                analog_x=120,
                analog_y=130,
                timestamp_us=100,
                session_token=token,
            )
        )

        receiver._handle_usb_data(packet, acknowledgements.append)

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].transport, TransportKind.USB)
        self.assertEqual(snapshots[0].address, ("usb", 0))
        self.assertEqual(len(acknowledgements), 1)
        self.assertEqual(decode_pairing_ack(acknowledgements[0]), token)

    def test_usb_ignores_a_different_configured_wifi_code(self) -> None:
        usb_token = parse_pairing_token("ABCDE")
        wifi_token = parse_pairing_token("FGHJK")
        snapshots = []
        receiver = UdpReceiver(
            "127.0.0.1",
            47999,
            on_packet=snapshots.append,
            pairing_token=wifi_token,
            require_pairing=True,
        )
        data = encode_packet(
            InputPacket(
                1,
                0,
                128,
                128,
                100,
                session_token=usb_token,
            )
        )

        receiver._handle_usb_data(data, lambda _ack: None)

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].transport, TransportKind.USB)

    def test_wifi_allowlist_does_not_block_local_usb_identity(self) -> None:
        token = parse_pairing_token("ABCDE")
        snapshots = []
        receiver = UdpReceiver(
            "127.0.0.1",
            47999,
            on_packet=snapshots.append,
            allowed_hosts={"10.0.0.33"},
            pairing_token=token,
            require_pairing=True,
        )
        packet = encode_packet(InputPacket(1, 0, 128, 128, 100, session_token=token))

        receiver._handle_usb_data(packet, lambda _ack: None)

        self.assertEqual(len(snapshots), 1)

    def test_missing_winusb_interface_starts_one_repair_attempt(self) -> None:
        repair = Mock(return_value=True)

        class MissingInterfaceBackend:
            def open(self):
                raise UsbDriverAccessError("interface GUID missing")

        source = UsbPacketSource(
            lambda _packet, _reply: None,
            backend=MissingInterfaceBackend(),
            driver_repair=repair,
            reconnect_interval_s=0.001,
        )

        def stop_after_repair() -> bool:
            source.request_stop()
            return True

        repair.side_effect = stop_after_repair
        source.run()

        repair.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
