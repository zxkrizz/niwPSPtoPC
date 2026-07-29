"""niwPSPtoPC UDP controller receiver."""

from .protocol import (
    INPUT_MAGIC,
    INPUT_VERSION,
    PACKET_SIZE,
    InputPacket,
    PacketError,
    decode_packet,
)

__all__ = [
    "INPUT_MAGIC",
    "INPUT_VERSION",
    "PACKET_SIZE",
    "InputPacket",
    "PacketError",
    "decode_packet",
]

__version__ = "1.0.0"
