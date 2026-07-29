from __future__ import annotations

from io import StringIO
import unittest

from pc_server.display import ControllerDisplay, format_buttons, format_status_line
from pc_server.protocol import Buttons, InputPacket
from pc_server.receiver import (
    MAX_CLOCK_SKEW_US,
    RateTracker,
    SequenceEvent,
    SequenceResult,
    SequenceTracker,
    UdpReceiver,
    estimate_latency_ms,
)
from pc_server.simulator import BUTTON_PATTERN, build_demo_packet


class ReceiverHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packet = InputPacket(
            sequence=42,
            buttons=int(Buttons.CROSS | Buttons.R),
            analog_x=122,
            analog_y=115,
            timestamp_us=100,
        )
        self.sequence_result = SequenceResult(SequenceEvent.FIRST)
        self.tracker = SequenceTracker(last_sequence=42, received=1)

    def test_synchronized_latency_is_reported(self) -> None:
        self.assertEqual(estimate_latency_ms(1_000_000, 1_012_500), 12.5)

    def test_unsynchronized_latency_is_not_reported(self) -> None:
        self.assertIsNone(
            estimate_latency_ms(1_000_000, 1_000_000 + MAX_CLOCK_SKEW_US + 1)
        )
        self.assertIsNone(estimate_latency_ms(2_000_000, 1_000_000))

    def test_rate_tracker_uses_rolling_one_second_window(self) -> None:
        tracker = RateTracker()
        self.assertEqual(tracker.observe(10.0), 1.0)
        self.assertEqual(tracker.observe(10.5), 2.0)
        self.assertEqual(tracker.observe(11.01), 2.0)

    def test_button_display_includes_known_and_unknown_bits(self) -> None:
        packet = InputPacket(
            sequence=1,
            buttons=int(Buttons.CROSS | Buttons.R) | (1 << 31),
            analog_x=128,
            analog_y=128,
            timestamp_us=100,
        )
        self.assertEqual(format_buttons(packet), "CROSS+R+UNKNOWN(0x80000000)")

    def test_compact_status_does_not_explain_unsynchronized_clock_inline(self) -> None:
        line = format_status_line(
            packet=self.packet,
            address=("10.0.0.33", 51060),
            packets_per_second=60.0,
            latency_ms=None,
            sequence_result=self.sequence_result,
            tracker=self.tracker,
        )
        self.assertIn("stick=122,115", line)
        self.assertIn("keys=CROSS+R", line)
        self.assertIn("lat=n/a", line)
        self.assertNotIn("clocks unsynchronized", line)
        self.assertLess(len(line), 120)

    def test_live_display_reuses_one_line_and_finishes_with_newline(self) -> None:
        stream = StringIO()
        display = ControllerDisplay(stream=stream, mode="live")
        display.render(
            packet=self.packet,
            address=("10.0.0.33", 51060),
            packets_per_second=60.0,
            latency_ms=None,
            sequence_result=self.sequence_result,
            tracker=self.tracker,
        )
        self.assertTrue(stream.getvalue().startswith("\r"))
        self.assertNotIn("\n", stream.getvalue())

        display.finish()
        self.assertTrue(stream.getvalue().endswith("\n"))

    def test_lines_display_appends_a_newline(self) -> None:
        stream = StringIO()
        display = ControllerDisplay(stream=stream, mode="lines")
        display.render(
            packet=self.packet,
            address=("10.0.0.33", 51060),
            packets_per_second=60.0,
            latency_ms=None,
            sequence_result=self.sequence_result,
            tracker=self.tracker,
        )
        self.assertTrue(stream.getvalue().endswith("\n"))
        self.assertFalse(stream.getvalue().startswith("\r"))

    def test_simulator_packet_is_valid_and_deterministic(self) -> None:
        packet = build_demo_packet(index=30, sequence=99, timestamp_us=1234)
        self.assertEqual(packet.sequence, 99)
        self.assertEqual(packet.timestamp_us, 1234)
        self.assertEqual(packet.buttons, BUTTON_PATTERN[1])
        self.assertEqual(packet.analog_x, 150)
        self.assertEqual(packet.analog_y, 105)

    def test_receiver_emits_snapshot_for_gui_frontends(self) -> None:
        snapshots = []
        receiver = UdpReceiver(
            "127.0.0.1",
            47999,
            on_packet=snapshots.append,
        )

        receiver._handle_packet(self.packet, ("10.0.0.33", 51060))

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].packet, self.packet)
        self.assertEqual(snapshots[0].address, ("10.0.0.33", 51060))
        self.assertEqual(snapshots[0].received, 1)
        self.assertEqual(snapshots[0].lost, 0)


if __name__ == "__main__":
    unittest.main()
