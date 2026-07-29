"""Terminal formatting for controller state."""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING, TextIO

from .protocol import Buttons, InputPacket

if TYPE_CHECKING:
    from .receiver import SequenceResult, SequenceTracker


BUTTON_ORDER = (
    Buttons.UP,
    Buttons.DOWN,
    Buttons.LEFT,
    Buttons.RIGHT,
    Buttons.CROSS,
    Buttons.CIRCLE,
    Buttons.SQUARE,
    Buttons.TRIANGLE,
    Buttons.L,
    Buttons.R,
    Buttons.START,
    Buttons.SELECT,
)

EVENT_LABELS = {
    "first": "first",
    "in-order": "ok",
    "gap": "gap",
    "duplicate": "dup",
    "out-of-order": "ooo",
}


def format_buttons(packet: InputPacket) -> str:
    pressed = packet.pressed_buttons
    names = [button.name for button in BUTTON_ORDER if pressed & button]
    if packet.unknown_buttons:
        names.append(f"UNKNOWN(0x{packet.unknown_buttons:08X})")
    return "+".join(names) if names else "-"


def format_status_line(
    *,
    packet: InputPacket,
    address: tuple[str, int],
    packets_per_second: float,
    latency_ms: float | None,
    sequence_result: SequenceResult,
    tracker: SequenceTracker,
) -> str:
    """Build a compact status line that fits a typical terminal."""
    latency_text = "n/a" if latency_ms is None else f"{latency_ms:.2f}ms"
    event_text = EVENT_LABELS.get(
        sequence_result.event.value,
        sequence_result.event.value,
    )
    return (
        f"{address[0]}:{address[1]} "
        f"seq={packet.sequence} {event_text} "
        f"pps={packets_per_second:.1f} "
        f"stick={packet.analog_x:3d},{packet.analog_y:3d} "
        f"keys={format_buttons(packet)} "
        f"lost={tracker.lost} dup={tracker.duplicates} "
        f"ooo={tracker.out_of_order} lat={latency_text}"
    )


class ControllerDisplay:
    """Render a bounded-rate status as a live line or append-only log."""

    def __init__(
        self,
        *,
        stream: TextIO = sys.stdout,
        refresh_hz: float = 10.0,
        mode: str = "auto",
    ) -> None:
        if refresh_hz <= 0:
            raise ValueError("refresh_hz must be greater than zero")
        if mode not in {"auto", "live", "lines"}:
            raise ValueError("mode must be auto, live, or lines")

        self.stream = stream
        self.refresh_period = 1.0 / refresh_hz
        self._last_render = 0.0
        self._last_width = 0
        self._line_active = False
        self.live = mode == "live" or (
            mode == "auto"
            and bool(getattr(stream, "isatty", lambda: False)())
        )

    def render(
        self,
        *,
        packet: InputPacket,
        address: tuple[str, int],
        packets_per_second: float,
        latency_ms: float | None,
        sequence_result: SequenceResult,
        tracker: SequenceTracker,
    ) -> None:
        now = time.monotonic()
        if (
            sequence_result.event.value == "in-order"
            and now - self._last_render < self.refresh_period
        ):
            return
        self._last_render = now

        line = format_status_line(
            packet=packet,
            address=address,
            packets_per_second=packets_per_second,
            latency_ms=latency_ms,
            sequence_result=sequence_result,
            tracker=tracker,
        )
        if not self.live:
            print(line, file=self.stream, flush=True)
            return

        padding = " " * max(0, self._last_width - len(line))
        self.stream.write(f"\r{line}{padding}")
        self.stream.flush()
        self._last_width = len(line)
        self._line_active = True

    def break_line(self) -> None:
        """Finish the live line before a warning is logged."""
        if self.live and self._line_active:
            self.stream.write("\n")
            self.stream.flush()
            self._line_active = False
            self._last_width = 0

    def finish(self) -> None:
        self.break_line()
