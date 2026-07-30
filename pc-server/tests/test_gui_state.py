from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    import tkinter  # noqa: F401
except ModuleNotFoundError as exc:
    raise unittest.SkipTest("Tkinter is not available in this environment") from exc

from pc_server.connection_doctor import ConnectionDoctor, DoctorStage
from pc_server.gamepad import ControllerEvent, ControllerEventType
from pc_server.gui import NiwPspToPcApp
from pc_server.gui_settings import GuiSettings
from pc_server.protocol import InputPacket, parse_pairing_token
from pc_server.receiver import (
    ReceiverEvent,
    ReceiverSnapshot,
    ReceiverStage,
    SequenceEvent,
    SequenceResult,
)


class FakeVar:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def set(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class FakeReceiver:
    def __init__(self) -> None:
        self.tokens: list[int | None] = []

    def set_pairing_token(self, token: int | None) -> None:
        self.tokens.append(token)


class FakeControllerService:
    def __init__(self) -> None:
        self.reasons: list[str] = []
        self.gamepad_ready = True

    def disconnect(self, reason: str) -> None:
        self.reasons.append(reason)


class StartControllerService:
    def __init__(self, **_kwargs: object) -> None:
        self.ready_checks = 0

    def ensure_backend(self) -> bool:
        self.ready_checks += 1
        return True

    def stop(self) -> None:
        pass


class StartReceiver:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def run(self) -> None:
        pass


class FakeThread:
    def __init__(self, **_kwargs: object) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True


class FakeEntry:
    def focus_set(self) -> None:
        pass


class FakeControllerView:
    def __init__(self) -> None:
        self.packets: list[InputPacket] = []
        self.links: list[tuple[str, str]] = []
        self.neutralized = 0
        self.rates: list[float] = []

    def set_packet(self, packet: InputPacket) -> None:
        self.packets.append(packet)

    def set_link_state(self, title: str, detail: str) -> None:
        self.links.append((title, detail))

    def neutralize(self) -> None:
        self.neutralized += 1

    def set_input_rate(self, rate: float) -> None:
        self.rates.append(rate)


def snapshot() -> ReceiverSnapshot:
    return ReceiverSnapshot(
        packet=InputPacket(
            7,
            0x10,
            120,
            130,
            100,
            session_token=parse_pairing_token("ABCDE"),
        ),
        address=("10.0.0.33", 51060),
        packets_per_second=59.5,
        latency_ms=None,
        sequence_result=SequenceResult(SequenceEvent.IN_ORDER),
        received=100,
        lost=2,
        duplicates=3,
        out_of_order=4,
        is_active_client=True,
        is_state_update=True,
    )


class GuiStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = NiwPspToPcApp.__new__(NiwPspToPcApp)
        self.app.code_var = FakeVar()
        self.app.status_var = FakeVar()
        self.app.status_detail_var = FakeVar()
        self.app.gamepad_var = FakeVar("OFFLINE")
        self.app.code_entry = FakeEntry()
        self.app.controller_view = FakeControllerView()
        self.app._receiver = FakeReceiver()
        self.app._controller_service = FakeControllerService()
        self.app._running = True
        self.app._paired_address = None
        self.app._active_token = None
        self.app._doctor = ConnectionDoctor()
        self.app._doctor_port = 47999
        self.app._doctor_row_labels = []
        self.statuses = []
        self.app._set_status = lambda *args: self.statuses.append(args)

    def test_normalizes_pairing_code(self) -> None:
        self.assertEqual(
            self.app._normalize_code_text("ab-c de"),
            "ABCDE",
        )

    def test_authorize_applies_token_to_running_receiver(self) -> None:
        self.app.code_var.set("ABCDE")

        self.app.authorize()

        expected = parse_pairing_token("ABCDE")
        self.assertEqual(self.app._active_token, expected)
        self.assertEqual(self.app._receiver.tokens, [expected])
        self.assertEqual(
            self.app._controller_service.reasons,
            ["pairing-changed"],
        )
        self.assertEqual(self.statuses[-1][0], "WAITING FOR PSP")
        self.assertEqual(self.app.controller_view.neutralized, 1)
        self.assertEqual(
            self.app.controller_view.links[-1],
            ("SEARCHING PSP", "CODE ACCEPTED"),
        )

    def test_snapshot_marks_product_connected(self) -> None:
        current = snapshot()

        self.app._apply_snapshot(current)

        self.assertEqual(self.app._paired_address, ("10.0.0.33", 51060))
        self.assertEqual(self.statuses[-1][0], "PSP CONNECTED")
        self.assertEqual(self.app.controller_view.packets, [current.packet])
        self.assertEqual(self.app.controller_view.rates, [59.5])
        self.assertEqual(
            self.app.controller_view.links[-1],
            ("LINK ACTIVE", "CONTROLLER READY"),
        )

    def test_timeout_marks_gamepad_disconnected(self) -> None:
        self.app._apply_controller_event(
            ControllerEvent(
                ControllerEventType.DISCONNECTED,
                address=("10.0.0.33", 51060),
                reason="timeout",
            )
        )

        self.assertEqual(self.app.gamepad_var.value, "READY")
        self.assertEqual(self.statuses[-1][0], "CONNECTION LOST")
        self.assertEqual(self.app.controller_view.neutralized, 1)
        self.assertEqual(
            self.app.controller_view.links[-1],
            ("SIGNAL LOST", "WAITING FOR PSP"),
        )

    def test_receiver_stage_updates_connection_doctor(self) -> None:
        self.app._apply_receiver_stage(
            ReceiverEvent(
                ReceiverStage.VALID_PACKET,
                ("10.0.0.33", 51060),
            )
        )

        self.assertIn(
            DoctorStage.VALID_PACKET,
            self.app._doctor.completed,
        )

    def test_gamepad_ready_updates_connection_doctor(self) -> None:
        self.app._apply_controller_event(
            ControllerEvent(ControllerEventType.GAMEPAD_READY)
        )

        self.assertEqual(self.app.gamepad_var.value, "READY")
        self.assertIn(
            DoctorStage.GAMEPAD_CREATED,
            self.app._doctor.completed,
        )

    def test_starting_new_receiver_discards_stale_doctor_stages(self) -> None:
        self.app._doctor.completed.update(DoctorStage)
        self.app._settings = GuiSettings()
        self.app._running = False
        self.app._closing = False
        self.app._refresh_doctor = lambda: None
        self.app._refresh_system_diagnostics = lambda: None

        with (
            patch("pc_server.gui.ControllerService", StartControllerService),
            patch("pc_server.gui.UdpReceiver", StartReceiver),
            patch("pc_server.gui.threading.Thread", FakeThread),
        ):
            self.app.start_receiver()

        self.assertEqual(self.app._doctor.completed, set())

    def test_clear_pairing_forgets_session(self) -> None:
        self.app.code_var.set("ABCDE")
        self.app._active_token = parse_pairing_token("ABCDE")

        self.app.clear_pairing()

        self.assertIsNone(self.app._active_token)
        self.assertEqual(self.app.code_var.value, "")
        self.assertEqual(self.app._receiver.tokens, [None])
        self.assertEqual(self.app.controller_view.neutralized, 1)


if __name__ == "__main__":
    unittest.main()
