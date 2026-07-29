from __future__ import annotations

from pathlib import Path
import re
import unittest

from pc_server import __version__


ROOT = Path(__file__).resolve().parents[2]
POLISH_DIACRITICS = {
    chr(codepoint)
    for codepoint in (
        0x0105,
        0x0107,
        0x0119,
        0x0142,
        0x0144,
        0x00F3,
        0x015B,
        0x017A,
        0x017C,
        0x0104,
        0x0106,
        0x0118,
        0x0141,
        0x0143,
        0x00D3,
        0x015A,
        0x0179,
        0x017B,
    )
}


class ReleaseQualityTests(unittest.TestCase):
    def test_public_psp_config_uses_automatic_discovery(self) -> None:
        config = (ROOT / "psp-client" / "config.ini").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("server_ip", config)
        self.assertIn("server_port=47999", config)

    def test_windows_build_has_no_user_specific_python_path(self) -> None:
        script = (ROOT / "scripts" / "build-windows.ps1").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(r"C:\Users", script)

    def test_public_product_text_is_english_only(self) -> None:
        files = [
            ROOT / "README.md",
            ROOT / "SECURITY.md",
            ROOT / "CHANGELOG.md",
            ROOT / "docs" / "input-protocol.md",
            ROOT / "pc-server" / "README.md",
            ROOT / "pc-server" / "pc_server" / "gui.py",
            ROOT / "pc-server" / "pc_server" / "gamepad.py",
            ROOT / "pc-server" / "pc_server" / "gui_settings.py",
            ROOT / "pc-server" / "pc_server" / "protocol.py",
        ]
        for path in files:
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                self.assertFalse(POLISH_DIACRITICS.intersection(text))

    def test_release_version_is_consistent(self) -> None:
        pyproject = (ROOT / "pc-server" / "pyproject.toml").read_text(
            encoding="utf-8"
        )
        version_info = (
            ROOT / "pc-server" / "windows-version-info.txt"
        ).read_text(encoding="utf-8")
        self.assertRegex(
            pyproject,
            rf'(?m)^version = "{re.escape(__version__)}"$',
        )
        self.assertIn(
            f"StringStruct('ProductVersion', '{__version__}')",
            version_info,
        )


if __name__ == "__main__":
    unittest.main()
