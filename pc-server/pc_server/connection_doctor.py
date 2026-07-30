"""Connection-stage diagnostics shared by the GUI and unit tests."""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from .receiver import ReceiverMetrics
from .windows_diagnostics import WindowsNetworkDiagnostics


class DoctorStage(Enum):
    PORT_BOUND = "PORT BOUND"
    DATAGRAM_RECEIVED = "DATAGRAM RECEIVED"
    VALID_PACKET = "VALID PACKET"
    CODE_MATCHED = "CODE MATCHED"
    ACK_SENT = "ACK SENT"
    GAMEPAD_CREATED = "GAMEPAD CREATED"


DOCTOR_STAGE_ORDER = tuple(DoctorStage)


class ConnectionDoctor:
    """Track observable milestones and explain the first missing one."""

    def __init__(self) -> None:
        self.completed: set[DoctorStage] = set()
        self.gamepad_error: str | None = None
        self.bound_address: tuple[str, int] | None = None
        self.metrics: ReceiverMetrics | None = None
        self.network: WindowsNetworkDiagnostics | None = None

    def mark(self, stage: DoctorStage) -> None:
        self.completed.add(stage)
        if stage is DoctorStage.GAMEPAD_CREATED:
            self.gamepad_error = None

    def reset_pairing(self) -> None:
        self.completed.difference_update(
            {
                DoctorStage.DATAGRAM_RECEIVED,
                DoctorStage.VALID_PACKET,
                DoctorStage.CODE_MATCHED,
                DoctorStage.ACK_SENT,
            }
        )

    def fail_gamepad(self, error: str) -> None:
        self.completed.discard(DoctorStage.GAMEPAD_CREATED)
        self.gamepad_error = error

    def set_bound_address(self, address: tuple[str, int]) -> None:
        self.bound_address = address

    def update_metrics(self, metrics: ReceiverMetrics) -> None:
        self.metrics = metrics

    def update_network(self, network: WindowsNetworkDiagnostics) -> None:
        self.network = network

    def rows(self) -> tuple[tuple[str, bool], ...]:
        return tuple(
            (stage.value, stage in self.completed)
            for stage in DOCTOR_STAGE_ORDER
        )

    def guidance(self, *, port: int) -> str:
        if self.gamepad_error:
            return (
                "Virtual gamepad preflight failed. Check the detail and use "
                "RETRY GAMEPAD after correcting the library or driver."
            )
        if DoctorStage.PORT_BOUND not in self.completed:
            return (
                f"Waiting to bind UDP {port}. Another app instance may already "
                "own the port."
            )
        if DoctorStage.GAMEPAD_CREATED not in self.completed:
            return "Checking the ViGEmBus virtual-controller driver."
        if (
            DoctorStage.DATAGRAM_RECEIVED not in self.completed
            and DoctorStage.VALID_PACKET not in self.completed
        ):
            return (
                f"No UDP datagram on UDP {port}. Check the same LAN, Windows "
                "Private profile/firewall, and client isolation. Guest Wi-Fi "
                "often blocks PSP-to-PC traffic; broadcast may not cross "
                "network interfaces."
            )
        if DoctorStage.VALID_PACKET not in self.completed:
            return (
                "UDP traffic reaches the app, but no valid PSP packet passed "
                "protocol decoding and the IP allowlist."
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

    def diagnostic_report(
        self,
        *,
        app_version: str,
        configured_host: str,
        port: int,
        allowed_hosts: Iterable[str],
        active_client: tuple[str, int] | None,
    ) -> str:
        lines = [
            f"niwPSPtoPC {app_version} diagnostic report",
            f"Configured bind: {configured_host}:{port}",
            (
                f"Actual bind: {self.bound_address[0]}:{self.bound_address[1]}"
                if self.bound_address is not None
                else "Actual bind: not bound"
            ),
            "Allowlist: " + (", ".join(allowed_hosts) or "(any IPv4 host)"),
            (
                f"Active PSP: {active_client[0]}:{active_client[1]}"
                if active_client is not None
                else "Active PSP: none"
            ),
            "",
            "Connection stages:",
        ]
        lines.extend(
            f"- [{'OK' if complete else '--'}] {stage}"
            for stage, complete in self.rows()
        )

        metrics = self.metrics
        lines.extend(("", "UDP metrics:"))
        if metrics is None:
            lines.append("- unavailable")
        else:
            age = (
                f"{metrics.last_datagram_age_s:.2f} s"
                if metrics.last_datagram_age_s is not None
                else "never"
            )
            lines.extend(
                (
                    f"- datagrams received: {metrics.datagrams_received}",
                    f"- valid packets: {metrics.valid_packets}",
                    f"- rejected datagrams: {metrics.rejected_datagrams}",
                    f"- pairing rejections: {metrics.pairing_rejections}",
                    f"- callback errors: {metrics.callback_errors}",
                    f"- last datagram age: {age}",
                    f"- current rate: {metrics.packets_per_second:.1f} pps",
                    f"- packet loss: {metrics.loss_percent:.2f}%",
                )
            )

        lines.extend(("", "Windows network:"))
        network = self.network
        if network is None:
            lines.append("- scan pending")
        elif network.error:
            lines.append(f"- {network.error}")
        else:
            if not network.interfaces:
                lines.append("- no active IPv4 interface found")
            for interface in network.interfaces:
                addresses = ", ".join(interface.addresses) or "(no IPv4)"
                lines.append(
                    f"- {interface.name}: {addresses}; "
                    f"profile={interface.profile}"
                )
            lines.append(f"- firewall: {network.firewall_status}")
            lines.append(
                "- multiple interfaces: "
                + ("yes" if network.multiple_interfaces else "no")
            )
            lines.append(
                "- VPN-like adapter: "
                + ("yes" if network.vpn_detected else "no")
            )
        lines.extend(("", f"Doctor: {self.guidance(port=port)}"))
        return "\n".join(lines) + "\n"
