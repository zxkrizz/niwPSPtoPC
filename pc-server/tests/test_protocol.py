from __future__ import annotations

import struct
import unittest

from pc_server.protocol import (
    INPUT_MAGIC,
    INPUT_VERSION,
    PACKET_SIZE,
    PACKET_STRUCT,
    PAIRING_ACK_SIZE,
    V1_PACKET_SIZE,
    V1_PACKET_STRUCT,
    InputPacket,
    InvalidMagicError,
    InvalidPacketSizeError,
    InvalidReservedFieldError,
    PacketLengthError,
    UnsupportedVersionError,
    decode_packet,
    decode_pairing_ack,
    encode_packet,
    encode_pairing_ack,
    format_pairing_token,
    parse_pairing_token,
)


class ProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packet = InputPacket(
            sequence=42,
            buttons=0xA55,
            analog_x=127,
            analog_y=201,
            reserved=0,
            timestamp_us=1_234_567_890,
            session_token=0x01234567,
        )

    def test_valid_packet(self) -> None:
        encoded = encode_packet(self.packet)

        self.assertEqual(len(encoded), 32)
        self.assertEqual(decode_packet(encoded), self.packet)

    def test_invalid_magic(self) -> None:
        data = bytearray(encode_packet(self.packet))
        struct.pack_into("!I", data, 0, 0xDEADBEEF)

        with self.assertRaises(InvalidMagicError):
            decode_packet(bytes(data))

    def test_unsupported_version(self) -> None:
        data = bytearray(encode_packet(self.packet))
        struct.pack_into("!H", data, 4, INPUT_VERSION + 1)

        with self.assertRaises(UnsupportedVersionError):
            decode_packet(bytes(data))

    def test_invalid_embedded_size(self) -> None:
        data = bytearray(encode_packet(self.packet))
        struct.pack_into("!H", data, 6, PACKET_SIZE + 4)

        with self.assertRaises(InvalidPacketSizeError):
            decode_packet(bytes(data))

    def test_invalid_datagram_length(self) -> None:
        with self.assertRaises(PacketLengthError):
            decode_packet(encode_packet(self.packet)[:-1])

    def test_nonzero_reserved_field_is_rejected(self) -> None:
        data = bytearray(encode_packet(self.packet))
        struct.pack_into("!H", data, 18, 1)

        with self.assertRaises(InvalidReservedFieldError):
            decode_packet(bytes(data))

        with self.assertRaises(ValueError):
            encode_packet(
                InputPacket(
                    sequence=1,
                    buttons=0,
                    analog_x=128,
                    analog_y=128,
                    reserved=1,
                    timestamp_us=1,
                    session_token=0,
                )
            )

    def test_wire_format_is_network_byte_order(self) -> None:
        encoded = encode_packet(self.packet)
        self.assertEqual(encoded[:4], INPUT_MAGIC.to_bytes(4, "big"))
        self.assertEqual(PACKET_STRUCT.format, "!IHHIIBBHIQ")

    def test_pairing_token_text_round_trip(self) -> None:
        for value in (0, 1, 0x01234567, (1 << 25) - 1):
            with self.subTest(value=value):
                code = format_pairing_token(value)
                self.assertEqual(len(code), 5)
                self.assertEqual(parse_pairing_token(code), value)
                self.assertNotIn("I", code)
                self.assertNotIn("O", code)

    def test_pairing_token_accepts_user_separators(self) -> None:
        token = parse_pairing_token("AB-CD E")
        self.assertEqual(format_pairing_token(token), "ABCDE")

    def test_invalid_pairing_token_is_rejected(self) -> None:
        for value in ("ABCD", "ABCDEF", "AB0DE", "ABIDE"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_pairing_token(value)

    def test_pairing_ack_round_trip(self) -> None:
        encoded = encode_pairing_ack(0x01234567)

        self.assertEqual(len(encoded), PAIRING_ACK_SIZE)
        self.assertEqual(decode_pairing_ack(encoded), 0x01234567)

    def test_legacy_v1_packet_remains_diagnostic_compatible(self) -> None:
        encoded = V1_PACKET_STRUCT.pack(
            INPUT_MAGIC,
            1,
            V1_PACKET_SIZE,
            self.packet.sequence,
            self.packet.buttons,
            self.packet.analog_x,
            self.packet.analog_y,
            self.packet.reserved,
            self.packet.timestamp_us,
        )

        decoded = decode_packet(encoded)

        self.assertIsNone(decoded.session_token)
        self.assertEqual(decoded.sequence, self.packet.sequence)


if __name__ == "__main__":
    unittest.main()
