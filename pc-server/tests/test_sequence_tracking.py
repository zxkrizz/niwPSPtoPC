from __future__ import annotations

import unittest

from pc_server.receiver import SequenceEvent, SequenceTracker


class SequenceTrackerTests(unittest.TestCase):
    def test_lost_sequence_number(self) -> None:
        tracker = SequenceTracker()
        tracker.observe(10)

        result = tracker.observe(13)

        self.assertEqual(result.event, SequenceEvent.GAP)
        self.assertEqual(result.lost, 2)
        self.assertEqual(tracker.lost, 2)
        self.assertEqual(tracker.last_sequence, 13)

    def test_duplicate_packet(self) -> None:
        tracker = SequenceTracker()
        tracker.observe(7)

        result = tracker.observe(7)

        self.assertEqual(result.event, SequenceEvent.DUPLICATE)
        self.assertEqual(tracker.duplicates, 1)
        self.assertEqual(tracker.last_sequence, 7)

    def test_out_of_order_packet(self) -> None:
        tracker = SequenceTracker()
        tracker.observe(100)

        result = tracker.observe(99)

        self.assertEqual(result.event, SequenceEvent.OUT_OF_ORDER)
        self.assertEqual(tracker.out_of_order, 1)
        self.assertEqual(tracker.last_sequence, 100)

    def test_uint32_wrap_is_in_order(self) -> None:
        tracker = SequenceTracker()
        tracker.observe(0xFFFFFFFF)

        result = tracker.observe(0)

        self.assertEqual(result.event, SequenceEvent.IN_ORDER)
        self.assertEqual(tracker.lost, 0)
        self.assertEqual(tracker.last_sequence, 0)


if __name__ == "__main__":
    unittest.main()
