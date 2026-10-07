"""niwPSPtoPC wireless and wired gamepad receiver."""

from ._version import __version__
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
    "__version__",
]
