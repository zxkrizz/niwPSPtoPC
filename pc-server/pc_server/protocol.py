"""Binary input and pairing protocol shared by the PSP and PC."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntFlag
import struct

INPUT_MAGIC = 0x50535049  # ASCII "PSPI"
INPUT_VERSION = 2
LEGACY_INPUT_VERSION = 1

# Network byte order (big-endian), packed without implicit alignment.
HEADER_STRUCT = struct.Struct("!IHH")
V1_PACKET_STRUCT = struct.Struct("!IHHIIBBHQ")
PACKET_STRUCT = struct.Struct("!IHHIIBBHIQ")
V1_PACKET_SIZE = V1_PACKET_STRUCT.size
PACKET_SIZE = PACKET_STRUCT.size

PAIRING_ACK_MAGIC = 0x50535041  # ASCII "PSPA"
PAIRING_ACK_VERSION = 1
PAIRING_ACK_STRUCT = struct.Struct("!IHHI")
PAIRING_ACK_SIZE = PAIRING_ACK_STRUCT.size

PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAIRING_TOKEN_LENGTH = 5
PAIRING_TOKEN_MAX = (1 << 25) - 1
_PAIRING_VALUES = {character: index for index, character in enumerate(PAIRING_ALPHABET)}


class Buttons(IntFlag):
    UP = 1 << 0
    DOWN = 1 << 1
    LEFT = 1 << 2
    RIGHT = 1 << 3
    CROSS = 1 << 4
    CIRCLE = 1 << 5
    SQUARE = 1 << 6
    TRIANGLE = 1 << 7
    L = 1 << 8
    R = 1 << 9
    START = 1 << 10
    SELECT = 1 << 11


KNOWN_BUTTON_MASK = sum(button.value for button in Buttons)


class PacketError(ValueError):
    """Base class for malformed or unsupported protocol datagrams."""


class PacketLengthError(PacketError):
    """The datagram length does not match its protocol message."""


class InvalidMagicError(PacketError):
    """The datagram is not a niwPSPtoPC protocol message."""


class UnsupportedVersionError(PacketError):
    """The packet uses a version this receiver cannot decode."""


class InvalidPacketSizeError(PacketError):
    """The embedded packet_size field is inconsistent with the version."""


@dataclass(frozen=True, slots=True)
class InputPacket:
    sequence: int
    buttons: int
    analog_x: int
    analog_y: int
    timestamp_us: int
    reserved: int = 0
    session_token: int | None = 0

    @property
    def pressed_buttons(self) -> Buttons:
        return Buttons(self.buttons & KNOWN_BUTTON_MASK)

    @property
    def unknown_buttons(self) -> int:
        return self.buttons & ~KNOWN_BUTTON_MASK


def format_pairing_token(value: int) -> str:
    """Return a five-character, ambiguity-free pairing code."""
    if not 0 <= value <= PAIRING_TOKEN_MAX:
        raise ValueError("pairing token must be an unsigned 25-bit integer")
    characters = ["A"] * PAIRING_TOKEN_LENGTH
    remaining = value
    for index in range(PAIRING_TOKEN_LENGTH - 1, -1, -1):
        characters[index] = PAIRING_ALPHABET[remaining & 0x1F]
        remaining >>= 5
    return "".join(characters)


def parse_pairing_token(text: str) -> int:
    """Parse a user-entered pairing code, ignoring spaces and hyphens."""
    normalized = text.strip().upper().replace(" ", "").replace("-", "")
    if len(normalized) != PAIRING_TOKEN_LENGTH:
        raise ValueError("The pairing code must contain exactly 5 characters.")
    value = 0
    for character in normalized:
        try:
            digit = _PAIRING_VALUES[character]
        except KeyError as exc:
            raise ValueError(
                f"Invalid pairing-code character: {character}"
            ) from exc
        value = (value << 5) | digit
    return value


def decode_packet(data: bytes) -> InputPacket:
    """Validate and decode one complete v1 or v2 input datagram."""
    if len(data) < HEADER_STRUCT.size:
        raise PacketLengthError(
            f"datagram has {len(data)} bytes; header requires {HEADER_STRUCT.size}"
        )
    magic, version, packet_size = HEADER_STRUCT.unpack_from(data)
    if magic != INPUT_MAGIC:
        raise InvalidMagicError(
            f"invalid magic 0x{magic:08X}; expected 0x{INPUT_MAGIC:08X}"
        )

    if version == LEGACY_INPUT_VERSION:
        expected_size = V1_PACKET_SIZE
        packet_struct = V1_PACKET_STRUCT
    elif version == INPUT_VERSION:
        expected_size = PACKET_SIZE
        packet_struct = PACKET_STRUCT
    else:
        raise UnsupportedVersionError(
            f"unsupported version {version}; receiver supports "
            f"{LEGACY_INPUT_VERSION} and {INPUT_VERSION}"
        )
    if packet_size != expected_size:
        raise InvalidPacketSizeError(
            f"packet_size is {packet_size}; version {version} "
            f"requires {expected_size}"
        )
    if len(data) != expected_size:
        raise PacketLengthError(
            f"datagram has {len(data)} bytes; version {version} "
            f"requires {expected_size}"
        )

    unpacked = packet_struct.unpack(data)
    if version == LEGACY_INPUT_VERSION:
        (
            _magic,
            _version,
            _packet_size,
            sequence,
            buttons,
            analog_x,
            analog_y,
            reserved,
            timestamp_us,
        ) = unpacked
        session_token = None
    else:
        (
            _magic,
            _version,
            _packet_size,
            sequence,
            buttons,
            analog_x,
            analog_y,
            reserved,
            session_token,
            timestamp_us,
        ) = unpacked
        if session_token > PAIRING_TOKEN_MAX:
            raise PacketError("session token exceeds the 25-bit pairing range")

    return InputPacket(
        sequence=sequence,
        buttons=buttons,
        analog_x=analog_x,
        analog_y=analog_y,
        reserved=reserved,
        timestamp_us=timestamp_us,
        session_token=session_token,
    )


def encode_packet(packet: InputPacket) -> bytes:
    """Encode a version 2 input packet for tests and protocol tooling."""
    if packet.session_token is None:
        raise ValueError("version 2 packets require a session token")
    if not 0 <= packet.session_token <= PAIRING_TOKEN_MAX:
        raise ValueError("session token must be an unsigned 25-bit integer")
    return PACKET_STRUCT.pack(
        INPUT_MAGIC,
        INPUT_VERSION,
        PACKET_SIZE,
        packet.sequence,
        packet.buttons,
        packet.analog_x,
        packet.analog_y,
        packet.reserved,
        packet.session_token,
        packet.timestamp_us,
    )


def encode_pairing_ack(session_token: int) -> bytes:
    if not 0 <= session_token <= PAIRING_TOKEN_MAX:
        raise ValueError("session token must be an unsigned 25-bit integer")
    return PAIRING_ACK_STRUCT.pack(
        PAIRING_ACK_MAGIC,
        PAIRING_ACK_VERSION,
        PAIRING_ACK_SIZE,
        session_token,
    )


def decode_pairing_ack(data: bytes) -> int:
    if len(data) != PAIRING_ACK_SIZE:
        raise PacketLengthError(
            f"pairing ACK has {len(data)} bytes; expected {PAIRING_ACK_SIZE}"
        )
    magic, version, packet_size, session_token = PAIRING_ACK_STRUCT.unpack(data)
    if magic != PAIRING_ACK_MAGIC:
        raise InvalidMagicError(
            f"invalid ACK magic 0x{magic:08X}; expected 0x{PAIRING_ACK_MAGIC:08X}"
        )
    if version != PAIRING_ACK_VERSION:
        raise UnsupportedVersionError(f"unsupported pairing ACK version {version}")
    if packet_size != PAIRING_ACK_SIZE:
        raise InvalidPacketSizeError(
            f"pairing ACK size is {packet_size}; expected {PAIRING_ACK_SIZE}"
        )
    if session_token > PAIRING_TOKEN_MAX:
        raise PacketError("pairing ACK token exceeds the 25-bit range")
    return session_token
