from __future__ import annotations

import threading
import unittest

from pc_server.gamepad import (
    ControllerEventType,
    ControllerService,
    XInputButtons,
    Xbox360State,
    map_packet_to_xbox360,
)
from pc_server.protocol import Buttons, InputPacket
from pc_server.receiver import (
    ReceiverSnapshot,
    SequenceEvent,
    SequenceResult,
)


ADDRESS = ("10.0.0.33", 51060)


def make_snapshot(
    sequence: int,
    event: SequenceEvent,
    *,
    state_update: bool = True,
    buttons: int = 0,
    analog_x: int = 128,
    analog_y: int = 128,
    address: tuple[str, int] = ADDRESS,
) -> ReceiverSnapshot:
    return ReceiverSnapshot(
        packet=InputPacket(
            sequence=sequence,
            buttons=buttons,
            analog_x=analog_x,
            analog_y=analog_y,
            timestamp_us=100,
        ),
        address=address,
        packets_per_second=60.0,
        latency_ms=None,
        sequence_result=SequenceResult(event),
        received=sequence + 1,
        lost=0,
        duplicates=0,
        out_of_order=0,
        is_active_client=state_update,
        is_state_update=state_update,
    )


class FakeBackend:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def connect(self) -> None:
        self.calls.append("connect")

    def apply(self, state: Xbox360State) -> None:
        self.calls.append(("apply", state))

    def neutralize(self) -> None:
        self.calls.append("neutralize")

    def disconnect(self) -> None:
        self.calls.append("disconnect")


class MutableClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class GamepadMappingTests(unittest.TestCase):
    def test_maps_every_psp_button_to_xinput(self) -> None:
        packet = InputPacket(
            sequence=1,
            buttons=sum(button.value for button in Buttons),
            analog_x=128,
            analog_y=128,
            timestamp_us=1,
        )

        state = map_packet_to_xbox360(packet)

        self.assertEqual(
            state.buttons,
            XInputButtons.DPAD_UP
            | XInputButtons.DPAD_DOWN
            | XInputButtons.DPAD_LEFT
            | XInputButtons.DPAD_RIGHT
            | XInputButtons.A
            | XInputButtons.B
            | XInputButtons.X
            | XInputButtons.Y
            | XInputButtons.LEFT_SHOULDER
            | XInputButtons.RIGHT_SHOULDER
            | XInputButtons.START
            | XInputButtons.BACK,
        )

    def test_maps_analog_extremes_and_inverts_y(self) -> None:
        top_left = map_packet_to_xbox360(
            InputPacket(1, 0, 0, 0, 1)
        )
        bottom_right = map_packet_to_xbox360(
            InputPacket(2, 0, 255, 255, 2)
        )
        center = map_packet_to_xbox360(
            InputPacket(3, 0, 128, 128, 3)
        )

        self.assertEqual((top_left.left_x, top_left.left_y), (-32768, 32767))
        self.assertEqual(
            (bottom_right.left_x, bottom_right.left_y),
            (32767, -32768),
        )
        self.assertEqual((center.left_x, center.left_y), (0, 0))


class ControllerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = MutableClock()
        self.backend = FakeBackend()
        self.events = []
        self.service = ControllerService(
            lambda: self.backend,
            timeout_s=1.5,
            on_event=self.events.append,
            clock=self.clock,
            start_watchdog=False,
        )

    def tearDown(self) -> None:
        self.service.stop()

    def test_only_first_in_order_and_gap_update_backend(self) -> None:
        snapshots = (
            make_snapshot(0, SequenceEvent.FIRST),
            make_snapshot(1, SequenceEvent.IN_ORDER),
            make_snapshot(1, SequenceEvent.DUPLICATE, state_update=False),
            make_snapshot(0, SequenceEvent.OUT_OF_ORDER, state_update=False),
            make_snapshot(4, SequenceEvent.GAP),
        )

        results = [self.service.handle_snapshot(item) for item in snapshots]

        applies = [
            call for call in self.backend.calls
            if isinstance(call, tuple) and call[0] == "apply"
        ]
        self.assertEqual(results, [True, True, False, False, True])
        self.assertEqual(len(applies), 3)

    def test_timeout_neutralizes_before_disconnect(self) -> None:
        self.service.handle_snapshot(
            make_snapshot(
                0,
                SequenceEvent.FIRST,
                buttons=int(Buttons.CROSS),
                analog_x=255,
            )
        )
        self.clock.now += 1.49
        self.assertFalse(self.service.check_timeout())

        self.clock.now += 0.02
        self.assertTrue(self.service.check_timeout())

        self.assertEqual(
            self.backend.calls[-2:],
            ["neutralize", "disconnect"],
        )
        self.assertFalse(self.service.connected)
        self.assertEqual(self.events[-1].event, ControllerEventType.DISCONNECTED)
        self.assertEqual(self.events[-1].reason, "timeout")

    def test_client_change_neutralizes_old_backend_before_new_state(self) -> None:
        self.service.handle_snapshot(make_snapshot(0, SequenceEvent.FIRST))
        other = ("10.0.0.44", 52000)

        self.service.handle_snapshot(
            make_snapshot(0, SequenceEvent.FIRST, address=other)
        )

        self.assertEqual(self.backend.calls.count("connect"), 2)
        first_disconnect = self.backend.calls.index("disconnect")
        second_connect = self.backend.calls.index("connect", 1)
        self.assertLess(first_disconnect, second_connect)
        self.assertEqual(self.service.address, other)

    def test_watchdog_runs_without_frontend_polling(self) -> None:
        backend = FakeBackend()
        disconnected = threading.Event()
        service = ControllerService(
            lambda: backend,
            timeout_s=0.05,
            on_event=lambda event: (
                disconnected.set()
                if event.event is ControllerEventType.DISCONNECTED
                else None
            ),
        )
        try:
            service.handle_snapshot(make_snapshot(0, SequenceEvent.FIRST))

            self.assertTrue(disconnected.wait(1.0))
            self.assertEqual(
                backend.calls[-2:],
                ["neutralize", "disconnect"],
            )
        finally:
            service.stop()


if __name__ == "__main__":
    unittest.main()
