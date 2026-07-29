from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from pc_server.gui_settings import (
    GuiSettings,
    load_settings,
    save_settings,
    validate_bind_settings,
)


class GuiHelperTests(unittest.TestCase):
    def test_validate_bind_settings(self) -> None:
        self.assertEqual(
            validate_bind_settings(" 0.0.0.0 ", "47999"),
            GuiSettings("0.0.0.0", 47999),
        )
        self.assertEqual(
            validate_bind_settings(
                "0.0.0.0",
                "47999",
                " 10.0.0.33; 10.0.0.44,10.0.0.33 ",
            ),
            GuiSettings(
                "0.0.0.0",
                47999,
                ("10.0.0.33", "10.0.0.44"),
            ),
        )

    def test_invalid_bind_settings_are_rejected(self) -> None:
        for host, port in (
            ("localhost", "47999"),
            ("999.1.1.1", "47999"),
            ("0.0.0.0", "0"),
            ("0.0.0.0", "65536"),
            ("0.0.0.0", "not-a-port"),
        ):
            with self.subTest(host=host, port=port):
                with self.assertRaises(ValueError):
                    validate_bind_settings(host, port)
        with self.assertRaises(ValueError):
            validate_bind_settings("0.0.0.0", "47999", "not-an-ip")

    def test_settings_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            expected = GuiSettings(
                "127.0.0.1",
                48000,
                ("10.0.0.33", "10.0.0.44"),
            )
            save_settings(expected, path)
            self.assertEqual(load_settings(path), expected)

    def test_malformed_settings_fall_back_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({"host": "bad", "port": -1}))
            self.assertEqual(load_settings(path), GuiSettings())


if __name__ == "__main__":
    unittest.main()
