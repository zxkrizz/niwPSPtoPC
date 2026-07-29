from __future__ import annotations

from pathlib import Path
import re
import unittest

from pc_server.protocol import InputPacket, decode_packet, encode_packet


ROOT = Path(__file__).resolve().parents[2]
GOLDEN_INCLUDE = ROOT / "psp-client" / "tests" / "golden_packet_v2.inc"


def load_c_golden_packet() -> bytes:
    values = re.findall(r"0x([0-9A-Fa-f]{2})", GOLDEN_INCLUDE.read_text())
    return bytes(int(value, 16) for value in values)


class GoldenPacketTests(unittest.TestCase):
    def test_c_encoder_fixture_decodes_in_python(self) -> None:
        expected = InputPacket(
            sequence=0x01020304,
            buttons=0x00000A55,
            analog_x=0x7F,
            analog_y=0xC9,
            reserved=0,
            session_token=0x01234567,
            timestamp_us=0x0102030405060708,
        )

        golden = load_c_golden_packet()

        self.assertEqual(len(golden), 32)
        self.assertEqual(decode_packet(golden), expected)
        self.assertEqual(encode_packet(expected), golden)


if __name__ == "__main__":
    unittest.main()
