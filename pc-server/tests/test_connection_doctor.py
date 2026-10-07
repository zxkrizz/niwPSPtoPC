from __future__ import annotations

import unittest

from pc_server import __version__
from pc_server.connection_doctor import ConnectionDoctor, DoctorStage
from pc_server.receiver import ReceiverMetrics
from pc_server.windows_diagnostics import (
    NetworkInterface,
    WindowsNetworkDiagnostics,
)


class ConnectionDoctorTests(unittest.TestCase):
    def test_reports_targeted_network_guidance(self) -> None:
        doctor = ConnectionDoctor()
        doctor.mark(DoctorStage.PORT_BOUND)
        doctor.mark(DoctorStage.GAMEPAD_CREATED)

        guidance = doctor.guidance(port=47999)

        self.assertIn("UDP 47999", guidance)
        self.assertIn("client isolation", guidance)
        self.assertIn("Guest Wi-Fi", guidance)

    def test_packet_without_code_points_to_code_or_port(self) -> None:
        doctor = ConnectionDoctor()
        doctor.completed.update(
            {
                DoctorStage.PORT_BOUND,
                DoctorStage.GAMEPAD_CREATED,
                DoctorStage.DATAGRAM_RECEIVED,
                DoctorStage.VALID_PACKET,
            }
        )

        guidance = doctor.guidance(port=48000)

        self.assertIn("For Wi-Fi", guidance)
        self.assertIn("same UDP port", guidance)

    def test_reset_pairing_keeps_pc_preflight_results(self) -> None:
        doctor = ConnectionDoctor()
        doctor.completed.update(DoctorStage)

        doctor.reset_pairing()

        self.assertEqual(
            doctor.completed,
            {DoctorStage.PORT_BOUND, DoctorStage.GAMEPAD_CREATED},
        )

    def test_report_contains_network_and_udp_evidence(self) -> None:
        doctor = ConnectionDoctor()
        doctor.set_bound_address(("0.0.0.0", 47999))
        doctor.update_metrics(
            ReceiverMetrics(
                datagrams_received=120,
                valid_packets=115,
                rejected_datagrams=5,
                pairing_rejections=2,
                callback_errors=1,
                last_datagram_age_s=0.25,
                packets_per_second=59.0,
                loss_percent=1.5,
            )
        )
        doctor.update_network(
            WindowsNetworkDiagnostics(
                interfaces=(
                    NetworkInterface(
                        "Ethernet",
                        ("192.168.1.20",),
                        "Private",
                    ),
                    NetworkInterface(
                        "WireGuard",
                        ("10.9.0.2",),
                        "Public",
                    ),
                ),
                firewall_status="Inbound UDP 47999 allow rule found",
                vpn_detected=True,
            )
        )

        report = doctor.diagnostic_report(
            app_version=__version__,
            configured_host="0.0.0.0",
            port=47999,
            allowed_hosts=("192.168.1.33",),
            active_client=("192.168.1.33", 51060),
        )

        self.assertIn("Actual bind: 0.0.0.0:47999", report)
        self.assertIn("valid packets: 115", report)
        self.assertIn("packet loss: 1.50%", report)
        self.assertIn("Ethernet: 192.168.1.20; profile=Private", report)
        self.assertIn("VPN-like adapter: yes", report)


if __name__ == "__main__":
    unittest.main()
