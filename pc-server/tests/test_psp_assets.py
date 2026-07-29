from __future__ import annotations

from pathlib import Path
import struct
import unittest


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "psp-client" / "assets"


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path.name} is not a PNG file")
    if data[12:16] != b"IHDR":
        raise ValueError(f"{path.name} has no leading IHDR chunk")
    return struct.unpack(">II", data[16:24])


class PspAssetTests(unittest.TestCase):
    def test_xmb_icon_has_native_psp_dimensions(self) -> None:
        self.assertEqual(png_dimensions(ASSETS / "ICON0.PNG"), (144, 80))

    def test_xmb_background_matches_psp_screen(self) -> None:
        self.assertEqual(png_dimensions(ASSETS / "PIC1.PNG"), (480, 272))


if __name__ == "__main__":
    unittest.main()
