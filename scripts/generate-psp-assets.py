"""Generate crisp, dependency-free PNG assets for the PSP EBOOT."""

from __future__ import annotations

import argparse
from pathlib import Path
import struct
import zlib


COLORS = {
    "bg": (6, 16, 20, 255),
    "grid": (11, 26, 30, 255),
    "panel": (13, 28, 32, 255),
    "panel_light": (19, 40, 43, 255),
    "border": (44, 75, 76, 255),
    "text": (233, 255, 247, 255),
    "muted": (130, 169, 160, 255),
    "accent": (100, 241, 189, 255),
    "accent_dark": (23, 61, 52, 255),
    "ink": (4, 16, 13, 255),
}

GLYPHS = {
    "A": (0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "B": (0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E),
    "C": (0x0F, 0x10, 0x10, 0x10, 0x10, 0x10, 0x0F),
    "D": (0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E),
    "E": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F),
    "F": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10),
    "G": (0x0F, 0x10, 0x10, 0x17, 0x11, 0x11, 0x0F),
    "H": (0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "I": (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x1F),
    "J": (0x07, 0x02, 0x02, 0x02, 0x12, 0x12, 0x0C),
    "K": (0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11),
    "L": (0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F),
    "M": (0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11),
    "N": (0x11, 0x19, 0x19, 0x15, 0x13, 0x13, 0x11),
    "O": (0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "P": (0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10),
    "Q": (0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D),
    "R": (0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11),
    "S": (0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E),
    "T": (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04),
    "U": (0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "V": (0x11, 0x11, 0x11, 0x11, 0x0A, 0x0A, 0x04),
    "W": (0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11),
    "X": (0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11),
    "Y": (0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04),
    "Z": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F),
    "0": (0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E),
    "1": (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "2": (0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F),
    "3": (0x1E, 0x01, 0x01, 0x0E, 0x01, 0x01, 0x1E),
    "4": (0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02),
    "5": (0x1F, 0x10, 0x10, 0x1E, 0x01, 0x01, 0x1E),
    "6": (0x0E, 0x10, 0x10, 0x1E, 0x11, 0x11, 0x0E),
    "7": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08),
    "8": (0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E),
    "9": (0x0E, 0x11, 0x11, 0x0F, 0x01, 0x01, 0x0E),
}


class Canvas:
    def __init__(self, width: int, height: int, color: tuple[int, ...]) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(color * (width * height))

    def fill(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        color: tuple[int, ...],
    ) -> None:
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(self.width, x + width)
        y2 = min(self.height, y + height)
        pixel = bytes(color)
        for row in range(y1, y2):
            start = (row * self.width + x1) * 4
            self.pixels[start : start + (x2 - x1) * 4] = pixel * (x2 - x1)

    def panel(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        background: tuple[int, ...],
        border: int = 2,
    ) -> None:
        self.fill(x, y, width, height, COLORS["border"])
        self.fill(
            x + border,
            y + border,
            width - border * 2,
            height - border * 2,
            background,
        )

    def text(
        self,
        x: int,
        y: int,
        value: str,
        scale: int,
        color: tuple[int, ...],
    ) -> None:
        for character in value.upper():
            glyph = GLYPHS.get(character)
            if glyph is not None:
                for row, bits in enumerate(glyph):
                    for column in range(5):
                        if bits & (1 << (4 - column)):
                            self.fill(
                                x + column * scale,
                                y + row * scale,
                                scale,
                                scale,
                                color,
                            )
            x += 6 * scale

    def logo(self, x: int, y: int, scale: int) -> None:
        accent = COLORS["accent"]
        ink = COLORS["ink"]
        self.fill(x + scale, y, 6 * scale, 8 * scale, accent)
        self.fill(x, y + scale, 8 * scale, 6 * scale, accent)
        self.fill(x + 2 * scale, y + 3 * scale, 3 * scale, scale, ink)
        self.fill(x + 3 * scale, y + 2 * scale, scale, 3 * scale, ink)
        self.fill(x + 6 * scale, y + 2 * scale, scale, scale, ink)
        self.fill(x + 7 * scale, y + 5 * scale, scale, scale, ink)

    def grid(self, spacing: int) -> None:
        for x in range(0, self.width, spacing):
            self.fill(x, 0, 1, self.height, COLORS["grid"])
        for y in range(0, self.height, spacing):
            self.fill(0, y, self.width, 1, COLORS["grid"])

    def save_png(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = bytearray()
        row_bytes = self.width * 4
        for y in range(self.height):
            rows.append(0)
            start = y * row_bytes
            rows.extend(self.pixels[start : start + row_bytes])

        def chunk(name: bytes, payload: bytes) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + name
                + payload
                + struct.pack(">I", zlib.crc32(name + payload) & 0xFFFFFFFF)
            )

        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(
                b"IHDR",
                struct.pack(">IIBBBBB", self.width, self.height, 8, 6, 0, 0, 0),
            )
            + chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
            + chunk(b"IEND", b"")
        )
        path.write_bytes(png)


def create_icon(path: Path) -> None:
    canvas = Canvas(144, 80, COLORS["bg"])
    canvas.grid(8)
    canvas.panel(2, 2, 140, 76, COLORS["panel"])
    canvas.logo(10, 20, 5)
    canvas.text(58, 14, "NIWPSP", 2, COLORS["text"])
    canvas.text(70, 34, "TO PC", 2, COLORS["accent"])
    canvas.text(62, 61, "USB WIFI PAD", 1, COLORS["muted"])
    canvas.save_png(path)


def create_background(path: Path) -> None:
    canvas = Canvas(480, 272, COLORS["bg"])
    canvas.grid(16)
    canvas.logo(36, 42, 8)
    canvas.text(120, 52, "NIWPSP TO PC", 4, COLORS["text"])
    canvas.text(120, 90, "WIRELESS AND WIRED GAMEPAD", 2, COLORS["accent"])
    canvas.panel(36, 150, 408, 70, COLORS["panel"])
    steps = (
        (54, "CHOOSE"),
        (180, "CONNECT"),
        (334, "PLAY"),
    )
    for x, label in steps:
        canvas.fill(x, 168, 10, 10, COLORS["accent"])
        canvas.text(x + 18, 166, label, 2, COLORS["text"])
    canvas.text(174, 240, "USB OR WI FI", 1, COLORS["muted"])
    canvas.save_png(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "psp-client" / "assets",
    )
    args = parser.parse_args()
    create_icon(args.output_dir / "ICON0.PNG")
    create_background(args.output_dir / "PIC1.PNG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
