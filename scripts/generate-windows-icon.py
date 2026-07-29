"""Generate the code-native niwPSPtoPC Windows icon without image dependencies."""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path


SIZE = 256
ACCENT = (72, 216, 155, 255)
DARK = (9, 17, 31, 255)
LIGHT = (245, 248, 252, 255)
TRANSPARENT = (0, 0, 0, 0)


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(payload, checksum)
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", checksum & 0xFFFFFFFF)
    )


def set_pixel(
    pixels: list[list[tuple[int, int, int, int]]],
    x: int,
    y: int,
    color: tuple[int, int, int, int],
) -> None:
    if 0 <= x < SIZE and 0 <= y < SIZE:
        pixels[y][x] = color


def fill_circle(
    pixels: list[list[tuple[int, int, int, int]]],
    center_x: int,
    center_y: int,
    radius: int,
    color: tuple[int, int, int, int],
) -> None:
    radius_squared = radius * radius
    for y in range(center_y - radius, center_y + radius + 1):
        for x in range(center_x - radius, center_x + radius + 1):
            if (x - center_x) ** 2 + (y - center_y) ** 2 <= radius_squared:
                set_pixel(pixels, x, y, color)


def fill_rect(
    pixels: list[list[tuple[int, int, int, int]]],
    left: int,
    top: int,
    right: int,
    bottom: int,
    color: tuple[int, int, int, int],
) -> None:
    for y in range(top, bottom):
        for x in range(left, right):
            set_pixel(pixels, x, y, color)


def build_png() -> bytes:
    pixels = [[TRANSPARENT for _ in range(SIZE)] for _ in range(SIZE)]
    fill_circle(pixels, 128, 128, 114, DARK)
    fill_circle(pixels, 128, 128, 105, ACCENT)

    # D-pad
    fill_rect(pixels, 48, 104, 108, 132, DARK)
    fill_rect(pixels, 64, 88, 92, 148, DARK)

    # PSP face buttons
    for x, y in ((181, 96), (205, 120), (181, 144), (157, 120)):
        fill_circle(pixels, x, y, 13, DARK)
        fill_circle(pixels, x, y, 5, LIGHT)

    # Start/Select
    fill_rect(pixels, 103, 174, 125, 183, DARK)
    fill_rect(pixels, 133, 174, 155, 183, DARK)

    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for red, green, blue, alpha in row:
            raw.extend((red, green, blue, alpha))

    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(bytes(raw), level=9))
        + png_chunk(b"IEND", b"")
    )


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: generate-windows-icon.py OUTPUT.ico")
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    png = build_png()
    icon_header = struct.pack("<HHH", 0, 1, 1)
    icon_entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)
    output.write_bytes(icon_header + icon_entry + png)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
