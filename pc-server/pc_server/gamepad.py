"""Safe virtual Xbox 360 controller output.

The controller service deliberately owns its timeout.  Frontends may display
the same state, but they are not responsible for releasing game input.
"""

from __future__ import annotations

import importlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, IntFlag
from typing import ClassVar, Protocol

from .protocol import Buttons, InputPacket
from .receiver import ReceiverSnapshot, SequenceEvent

LOGGER = logging.getLogger(__name__)
DEFAULT_NEUTRAL_TIMEOUT_S = 0.5
DEFAULT_SESSION_TIMEOUT_S = 1.75
DEFAULT_BACKEND_RETRY_DELAY_S = 3.0
# Kept as the public CLI default name for compatibility.
DEFAULT_INPUT_TIMEOUT_S = DEFAULT_SESSION_TIMEOUT_S


class XInputButtons(IntFlag):
    NONE = 0x0000
    DPAD_UP = 0x0001
    DPAD_DOWN = 0x0002
    DPAD_LEFT = 0x0004
    DPAD_RIGHT = 0x0008
    START = 0x0010
    BACK = 0x0020
    LEFT_SHOULDER = 0x0100
    RIGHT_SHOULDER = 0x0200
    A = 0x1000
    B = 0x2000
    X = 0x4000
    Y = 0x8000


PSP_TO_XINPUT = {
    Buttons.UP: XInputButtons.DPAD_UP,
    Buttons.DOWN: XInputButtons.DPAD_DOWN,
    Buttons.LEFT: XInputButtons.DPAD_LEFT,
    Buttons.RIGHT: XInputButtons.DPAD_RIGHT,
    Buttons.CROSS: XInputButtons.A,
    Buttons.CIRCLE: XInputButtons.B,
    Buttons.SQUARE: XInputButtons.X,
    Buttons.TRIANGLE: XInputButtons.Y,
    Buttons.L: XInputButtons.LEFT_SHOULDER,
    Buttons.R: XInputButtons.RIGHT_SHOULDER,
    Buttons.START: XInputButtons.START,
    Buttons.SELECT: XInputButtons.BACK,
}


class BackendFailureKind(Enum):
    MISSING_LIBRARY = "missing-library"
    MISSING_DRIVER = "missing-driver"
    DRIVER_CONNECTION = "driver-connection"
    UPDATE_FAILED = "update-failed"


class GamepadBackendError(RuntimeError):
    def __init__(self, kind: BackendFailureKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True, slots=True)
class Xbox360State:
    buttons: XInputButtons = XInputButtons.NONE
    left_x: int = 0
    left_y: int = 0


NEUTRAL_STATE = Xbox360State()


def _horizontal_axis(value: int) -> int:
    if not 0 <= value <= 255:
        raise ValueError("analog value must be between 0 and 255")
    if value < 128:
        return round((value - 128) * 32768 / 128)
    if value > 128:
        return round((value - 128) * 32767 / 127)
    return 0


def _vertical_axis(value: int) -> int:
    """Map PSP screen coordinates to XInput's positive-up Y axis."""
    if not 0 <= value <= 255:
        raise ValueError("analog value must be between 0 and 255")
    if value < 128:
        return round((128 - value) * 32767 / 128)
    if value > 128:
        return -round((value - 128) * 32768 / 127)
    return 0


def map_packet_to_xbox360(packet: InputPacket) -> Xbox360State:
    buttons = XInputButtons(0)
    pressed = packet.pressed_buttons
    for psp_button, xinput_button in PSP_TO_XINPUT.items():
        if pressed & psp_button:
            buttons |= xinput_button
    return Xbox360State(
        buttons=buttons,
        left_x=_horizontal_axis(packet.analog_x),
        left_y=_vertical_axis(packet.analog_y),
    )


class GamepadBackend(Protocol):
    """Minimal backend contract used by the safety controller."""

    def connect(self) -> None: ...

    def apply(self, state: Xbox360State) -> None: ...

    def neutralize(self) -> None: ...

    def disconnect(self) -> None: ...


class VGamepadBackend:
    """Xbox 360 backend powered by vgamepad and the ViGEmBus driver."""

    def __init__(self) -> None:
        self._module: object | None = None
        self._gamepad: object | None = None

    def connect(self) -> None:
        if self._gamepad is not None:
            return
        try:
            module = importlib.import_module("vgamepad")
        except ImportError as exc:
            raise GamepadBackendError(
                BackendFailureKind.MISSING_LIBRARY,
                "The vgamepad package is missing. Install the application's "
                "'windows' extra.",
            ) from exc
        self._module = module
        try:
            self._gamepad = module.VX360Gamepad()  # type: ignore[attr-defined]
        except Exception as exc:
            self._module = None
            name_and_message = f"{type(exc).__name__} {exc}".lower()
            missing_library = (
                "dll" in name_and_message
                and (
                    "not found" in name_and_message
                    or "winerror 126" in name_and_message
                )
            )
            missing_driver = (
                "vigembus" in name_and_message
                and (
                    "not found" in name_and_message
                    or "notfound" in name_and_message
                    or "not installed" in name_and_message
                )
            )
            kind = (
                BackendFailureKind.MISSING_LIBRARY
                if missing_library
                else BackendFailureKind.MISSING_DRIVER
                if missing_driver
                else BackendFailureKind.DRIVER_CONNECTION
            )
            detail = (
                "The ViGEm client library could not be loaded."
                if missing_library
                else "The ViGEmBus driver is not installed."
                if missing_driver
                else "Could not connect to the ViGEmBus driver."
            )
            raise GamepadBackendError(
                kind,
                detail,
            ) from exc

    def apply(self, state: Xbox360State) -> None:
        if self._gamepad is None or self._module is None:
            raise RuntimeError("virtual gamepad is not connected")
        gamepad = self._gamepad
        module = self._module
        gamepad.reset()  # type: ignore[attr-defined]
        if state.buttons:
            gamepad.press_button(  # type: ignore[attr-defined]
                button=module.XUSB_BUTTON(int(state.buttons))  # type: ignore[attr-defined]
            )
        gamepad.left_joystick(  # type: ignore[attr-defined]
            x_value=state.left_x,
            y_value=state.left_y,
        )
        gamepad.update()  # type: ignore[attr-defined]

    def neutralize(self) -> None:
        if self._gamepad is None:
            return
        self._gamepad.reset()  # type: ignore[attr-defined]
        self._gamepad.update()  # type: ignore[attr-defined]

    def disconnect(self) -> None:
        # vgamepad removes the ViGEm target when the last Python reference is
        # released.  Neutralize is always called by ControllerService first.
        self._gamepad = None
        self._module = None


class ControllerEventType(Enum):
    GAMEPAD_READY = "gamepad-ready"
    CONNECTED = "connected"
    NEUTRALIZED = "neutralized"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ControllerEvent:
    event: ControllerEventType
    address: tuple[str, int] | None = None
    reason: str = ""
    error: str | None = None
    failure: BackendFailureKind | None = None


class ControllerService:
    """Apply fresh receiver states and fail closed after input silence."""

    _ACCEPTED_EVENTS: ClassVar[frozenset[SequenceEvent]] = frozenset(
        {
            SequenceEvent.FIRST,
            SequenceEvent.IN_ORDER,
            SequenceEvent.GAP,
        }
    )

    def __init__(
        self,
        backend_factory: Callable[[], GamepadBackend] = VGamepadBackend,
        *,
        timeout_s: float = DEFAULT_INPUT_TIMEOUT_S,
        neutral_timeout_s: float | None = None,
        on_event: Callable[[ControllerEvent], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        start_watchdog: bool = True,
        backend_retry_delay_s: float = DEFAULT_BACKEND_RETRY_DELAY_S,
    ) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if neutral_timeout_s is None:
            neutral_timeout_s = min(
                DEFAULT_NEUTRAL_TIMEOUT_S,
                timeout_s / 3,
            )
        if neutral_timeout_s <= 0 or neutral_timeout_s >= timeout_s:
            raise ValueError(
                "neutral_timeout_s must be positive and shorter than timeout_s"
            )
        if backend_retry_delay_s <= 0:
            raise ValueError("backend_retry_delay_s must be positive")
        self._backend_factory = backend_factory
        self._timeout_s = timeout_s
        self._neutral_timeout_s = neutral_timeout_s
        self._on_event = on_event
        self._clock = clock
        self._backend_retry_delay_s = backend_retry_delay_s
        self._backend: GamepadBackend | None = None
        self._address: tuple[str, int] | None = None
        self._last_update_at: float | None = None
        self._neutralized_for_silence = False
        self._connected = False
        self._backend_failed = False
        self._backend_failure: BackendFailureKind | None = None
        self._automatic_retry_due: float | None = None
        self._automatic_retry_used = False
        self._stopped = False
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._watchdog_thread: threading.Thread | None = None
        if start_watchdog:
            self._watchdog_thread = threading.Thread(
                target=self._watchdog,
                name="niwPSPtoPC controller safety watchdog",
                daemon=True,
            )
            self._watchdog_thread.start()

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def address(self) -> tuple[str, int] | None:
        with self._lock:
            return self._address

    @property
    def gamepad_ready(self) -> bool:
        with self._lock:
            return self._backend is not None and not self._backend_failed

    @property
    def backend_failure(self) -> BackendFailureKind | None:
        with self._lock:
            return self._backend_failure

    def ensure_backend(
        self,
        *,
        force_retry: bool = False,
        automatic: bool = False,
    ) -> bool:
        """Create the virtual target early and keep it for the process lifetime."""
        event: ControllerEvent | None = None
        with self._lock:
            if self._stopped:
                return False
            if self._backend_failed and not force_retry:
                return False
            if self._backend is not None:
                return True
            if force_retry:
                self._backend_failed = False
                self._backend_failure = None
                if not automatic:
                    self._automatic_retry_used = False
            try:
                self._backend = self._backend_factory()
                self._backend.connect()
                self._backend.neutralize()
            except Exception as exc:
                LOGGER.exception("Virtual gamepad preflight failed")
                self._destroy_backend_locked("backend-error")
                event = self._record_backend_failure_locked(
                    exc,
                    phase="preflight",
                    automatic=automatic,
                )
            else:
                self._backend_failed = False
                self._backend_failure = None
                self._automatic_retry_due = None
                self._automatic_retry_used = False
                event = ControllerEvent(ControllerEventType.GAMEPAD_READY)
        if event is not None:
            self._emit(event)
        return event is not None and event.event is ControllerEventType.GAMEPAD_READY

    def retry_backend(self) -> bool:
        """Run a fresh preflight without stopping the UDP receiver."""
        return self.ensure_backend(force_retry=True)

    def check_backend_retry(self, now: float | None = None) -> bool:
        """Perform the single delayed retry scheduled for a failure episode."""
        checked_at = self._clock() if now is None else now
        with self._lock:
            if (
                self._stopped
                or self._automatic_retry_due is None
                or checked_at < self._automatic_retry_due
            ):
                return False
            self._automatic_retry_due = None
            self._automatic_retry_used = True
        return self.ensure_backend(force_retry=True, automatic=True)

    def handle_snapshot(self, snapshot: ReceiverSnapshot) -> bool:
        """Apply an actionable snapshot; reject diagnostics defensively."""
        if (
            not snapshot.is_state_update
            or snapshot.sequence_result.event not in self._ACCEPTED_EVENTS
        ):
            return False

        event: ControllerEvent | None = None
        with self._lock:
            if self._stopped or self._backend_failed:
                return False
            if self._connected and self._address != snapshot.address:
                self._release_session_locked("client-changed")

            try:
                if self._backend is None:
                    self._backend = self._backend_factory()
                    self._backend.connect()
                self._backend.apply(map_packet_to_xbox360(snapshot.packet))
            except Exception as exc:
                LOGGER.exception("Virtual gamepad update failed")
                self._destroy_backend_locked("backend-error")
                event = self._record_backend_failure_locked(
                    exc,
                    phase="update",
                    address=snapshot.address,
                )
            else:
                was_connected = self._connected
                self._connected = True
                self._address = snapshot.address
                self._last_update_at = self._clock()
                self._neutralized_for_silence = False
                if not was_connected:
                    event = ControllerEvent(
                        ControllerEventType.CONNECTED,
                        address=snapshot.address,
                    )
        if event is not None:
            self._emit(event)
        return event is None or event.event is ControllerEventType.CONNECTED

    def check_timeout(self, now: float | None = None) -> bool:
        """Neutralize stale input, then release only the PSP session lock."""
        events: list[ControllerEvent] = []
        with self._lock:
            if not self._connected or self._last_update_at is None:
                return False
            checked_at = self._clock() if now is None else now
            silence_s = checked_at - self._last_update_at
            if silence_s < self._neutral_timeout_s:
                return False
            if not self._neutralized_for_silence:
                if self._backend is not None:
                    try:
                        self._backend.neutralize()
                    except Exception:
                        LOGGER.exception("Failed to neutralize stale controller input")
                self._neutralized_for_silence = True
                events.append(
                    ControllerEvent(
                        ControllerEventType.NEUTRALIZED,
                        address=self._address,
                        reason="input-silence",
                    )
                )
            released = silence_s >= self._timeout_s
            if released:
                address = self._address
                self._release_session_locked("timeout", neutralize=False)
                events.append(
                    ControllerEvent(
                        ControllerEventType.DISCONNECTED,
                        address=address,
                        reason="timeout",
                    )
                )
        for event in events:
            self._emit(event)
        return released

    def disconnect(self, reason: str = "manual") -> None:
        event: ControllerEvent | None = None
        with self._lock:
            address = self._address
            had_connection = self._connected
            self._release_session_locked(reason)
            if had_connection:
                event = ControllerEvent(
                    ControllerEventType.DISCONNECTED,
                    address=address,
                    reason=reason,
                )
        if event is not None:
            self._emit(event)

    def stop(self) -> None:
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
        self._stop_event.set()
        self.disconnect("receiver-stopped")
        with self._lock:
            self._destroy_backend_locked("application-stopped")
        thread = self._watchdog_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    def _release_session_locked(
        self,
        reason: str,
        *,
        neutralize: bool = True,
    ) -> None:
        self._connected = False
        self._address = None
        self._last_update_at = None
        self._neutralized_for_silence = False
        if neutralize and self._backend is not None:
            try:
                self._backend.neutralize()
            except Exception:
                LOGGER.exception(
                    "Failed to send neutral state while releasing session (%s)",
                    reason,
                )

    def _destroy_backend_locked(self, reason: str) -> None:
        backend = self._backend
        self._backend = None
        self._release_session_locked(reason, neutralize=False)
        if backend is None:
            return
        try:
            backend.neutralize()
        except Exception:
            LOGGER.exception(
                "Failed to send neutral state while removing gamepad (%s)", reason
            )
        try:
            backend.disconnect()
        except Exception:
            LOGGER.exception("Failed to disconnect virtual gamepad (%s)", reason)

    @staticmethod
    def _classify_backend_failure(
        error: Exception,
        *,
        phase: str,
    ) -> BackendFailureKind:
        if isinstance(error, GamepadBackendError):
            return error.kind
        if isinstance(error, (ImportError, ModuleNotFoundError)):
            return BackendFailureKind.MISSING_LIBRARY
        if phase == "update":
            return BackendFailureKind.UPDATE_FAILED
        name_and_message = f"{type(error).__name__} {error}".lower()
        if (
            "dll" in name_and_message
            and (
                "not found" in name_and_message
                or "winerror 126" in name_and_message
            )
        ):
            return BackendFailureKind.MISSING_LIBRARY
        if (
            "vigembus" in name_and_message
            and (
                "not found" in name_and_message
                or "notfound" in name_and_message
                or "not installed" in name_and_message
            )
        ):
            return BackendFailureKind.MISSING_DRIVER
        return BackendFailureKind.DRIVER_CONNECTION

    def _record_backend_failure_locked(
        self,
        error: Exception,
        *,
        phase: str,
        address: tuple[str, int] | None = None,
        automatic: bool = False,
    ) -> ControllerEvent:
        failure = self._classify_backend_failure(error, phase=phase)
        self._backend_failed = True
        self._backend_failure = failure
        if not automatic and not self._automatic_retry_used:
            self._automatic_retry_due = (
                self._clock() + self._backend_retry_delay_s
            )
        else:
            self._automatic_retry_due = None
        return ControllerEvent(
            ControllerEventType.ERROR,
            address=address,
            reason=failure.value,
            error=str(error),
            failure=failure,
        )

    def _watchdog(self) -> None:
        interval = min(0.1, self._timeout_s / 4)
        while not self._stop_event.wait(interval):
            self.check_timeout()
            self.check_backend_retry()

    def _emit(self, event: ControllerEvent) -> None:
        if self._on_event is not None:
            try:
                self._on_event(event)
            except Exception:
                LOGGER.exception("Controller event callback failed")
