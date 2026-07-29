from __future__ import annotations

import unittest

from pc_server.connection_doctor import ConnectionDoctor, DoctorStage


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
                DoctorStage.PACKET_RECEIVED,
            }
        )

        guidance = doctor.guidance(port=48000)

        self.assertIn("code does not match", guidance)
        self.assertIn("same UDP port", guidance)

    def test_reset_pairing_keeps_pc_preflight_results(self) -> None:
        doctor = ConnectionDoctor()
        doctor.completed.update(DoctorStage)

        doctor.reset_pairing()

        self.assertEqual(
            doctor.completed,
            {DoctorStage.PORT_BOUND, DoctorStage.GAMEPAD_CREATED},
        )


if __name__ == "__main__":
    unittest.main()
