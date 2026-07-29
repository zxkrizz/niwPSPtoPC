"""Connection-stage diagnostics shared by the GUI and unit tests."""

from __future__ import annotations

from enum import Enum


class DoctorStage(Enum):
    PORT_BOUND = "PORT BOUND"
    PACKET_RECEIVED = "PACKET RECEIVED"
    CODE_MATCHED = "CODE MATCHED"
    ACK_SENT = "ACK SENT"
    GAMEPAD_CREATED = "GAMEPAD CREATED"


DOCTOR_STAGE_ORDER = tuple(DoctorStage)


class ConnectionDoctor:
    """Track observable milestones and explain the first missing one."""

    def __init__(self) -> None:
        self.completed: set[DoctorStage] = set()
        self.gamepad_error: str | None = None

    def mark(self, stage: DoctorStage) -> None:
        self.completed.add(stage)
        if stage is DoctorStage.GAMEPAD_CREATED:
            self.gamepad_error = None

    def reset_pairing(self) -> None:
        self.completed.difference_update(
            {
                DoctorStage.PACKET_RECEIVED,
                DoctorStage.CODE_MATCHED,
                DoctorStage.ACK_SENT,
            }
        )

    def fail_gamepad(self, error: str) -> None:
        self.completed.discard(DoctorStage.GAMEPAD_CREATED)
        self.gamepad_error = error

    def rows(self) -> tuple[tuple[str, bool], ...]:
        return tuple(
            (stage.value, stage in self.completed)
            for stage in DOCTOR_STAGE_ORDER
        )

    def guidance(self, *, port: int) -> str:
        if self.gamepad_error:
            return (
                "ViGEmBus check failed. Install the driver, then restart "
                "niwPSPtoPC."
            )
        if DoctorStage.PORT_BOUND not in self.completed:
            return (
                f"Waiting to bind UDP {port}. Another app instance may already "
                "own the port."
            )
        if DoctorStage.GAMEPAD_CREATED not in self.completed:
            return "Checking the ViGEmBus virtual-controller driver."
        if DoctorStage.PACKET_RECEIVED not in self.completed:
            return (
                f"No PSP packet on UDP {port}. Check the same LAN, Windows "
                "Private profile/firewall, and client isolation. Guest Wi-Fi "
                "often blocks PSP-to-PC traffic; broadcast may not cross "
                "network interfaces."
            )
        if DoctorStage.CODE_MATCHED not in self.completed:
            return (
                "Packets reach this PC, but the code does not match. Re-enter "
                "the PSP code and confirm both sides use the same UDP port."
            )
        if DoctorStage.ACK_SENT not in self.completed:
            return (
                "The code matched, but the ACK was not sent. Check the local "
                "socket and firewall state."
            )
        return "All connection checks passed."
