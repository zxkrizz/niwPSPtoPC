from __future__ import annotations

import re
import unittest
from pathlib import Path

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
        version_source = (
            ROOT / "pc-server" / "pc_server" / "_version.py"
        ).read_text(encoding="utf-8")
        self.assertIn('dynamic = ["version"]', pyproject)
        self.assertIn(
            'version = {attr = "pc_server.__version__"}',
            pyproject,
        )
        self.assertIn(
            f'__version__ = "{__version__}"',
            version_source,
        )
        release_notes = (
            ROOT / "docs" / "releases" / f"{__version__}.md"
        ).read_text(encoding="utf-8")
        self.assertIn(f"# niwPSPtoPC {__version__}", release_notes)
        root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"Current release: **{__version__}**", root_readme)
        for name in ("README-WINDOWS.txt", "README-PSP.txt"):
            package_readme = (
                ROOT / "packaging" / name
            ).read_text(encoding="utf-8")
            self.assertIn(f"niwPSPtoPC {__version__}", package_readme)

        manifest = (
            ROOT / "packaging" / "windows" / "niwPSPtoPC.exe.manifest"
        ).read_text(encoding="utf-8")
        self.assertIn(f'version="{__version__}.0"', manifest)

    def test_public_branding_covers_wired_and_wireless_modes(self) -> None:
        required_phrase = "Ultimate Wireless and Wired Gamepad"
        files = (
            ROOT / "README.md",
            ROOT / "packaging" / "README-WINDOWS.txt",
            ROOT / "packaging" / "README-PSP.txt",
            ROOT / "docs" / "releases" / f"{__version__}.md",
        )
        for path in files:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIn(
                    required_phrase,
                    path.read_text(encoding="utf-8"),
                )

        current_docs = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "README.md",
                ROOT / "docs" / "usb.md",
                ROOT / "packaging" / "README-WINDOWS.txt",
                ROOT / "packaging" / "README-PSP.txt",
            )
        ).lower()
        self.assertNotIn("development preview", current_docs)

    def test_pspdev_image_is_pinned(self) -> None:
        image = (ROOT / "scripts" / "pspdev-image.txt").read_text(
            encoding="utf-8"
        ).strip()
        self.assertRegex(
            image,
            r"^pspdev/pspdev:v[0-9]+@sha256:[0-9a-f]{64}$",
        )
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("pspdev/pspdev:latest", workflow)

    def test_gui_passes_allowed_hosts_to_receiver(self) -> None:
        gui = (ROOT / "pc-server" / "pc_server" / "gui.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "allowed_hosts=set(settings.allowed_hosts) or None",
            gui,
        )

    def test_github_actions_are_pinned_to_full_commit_shas(self) -> None:
        workflows = ROOT / ".github" / "workflows"
        uses_pattern = re.compile(r"^\s*uses:\s*[^@\s]+@([^#\s]+)", re.MULTILINE)
        for path in workflows.glob("*.yml"):
            with self.subTest(workflow=path.name):
                text = path.read_text(encoding="utf-8")
                references = uses_pattern.findall(text)
                self.assertTrue(references)
                self.assertTrue(
                    all(re.fullmatch(r"[0-9a-f]{40}", value) for value in references)
                )

    def test_dependabot_covers_actions_and_python(self) -> None:
        config = (ROOT / ".github" / "dependabot.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn('package-ecosystem: "github-actions"', config)
        self.assertIn('package-ecosystem: "pip"', config)
        self.assertIn('directory: "/pc-server"', config)

    def test_release_workflow_checks_ancestry_and_attests_artifacts(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "release.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("git merge-base --is-ancestor", workflow)
        self.assertIn("attest-build-provenance@", workflow)
        self.assertIn("dist/windows/niwPSPtoPC.exe", workflow)
        self.assertIn("dist/release/*.zip", workflow)
        self.assertIn("gh release upload", workflow)
        self.assertIn("--clobber", workflow)
        self.assertIn("--notes-file $notes", workflow)
        self.assertIn("bash ./scripts/package-psp.sh", workflow)

    def test_release_packages_complete_psp_usb_runtime(self) -> None:
        package_script = (
            ROOT / "scripts" / "package-release.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn('"psp-client\\usbhostfs.prx"', package_script)
        self.assertIn(
            'Copy-Item -LiteralPath $PspUsbHostFs -Destination $PspStage',
            package_script,
        )
        self.assertIn(
            'Copy-Item -LiteralPath $Notices -Destination $PspStage',
            package_script,
        )
        self.assertIn('"niwPSPtoPC/usbhostfs.prx"', package_script)
        self.assertIn(
            '"niwPSPtoPC/THIRD_PARTY_NOTICES.txt"',
            package_script,
        )

        psp_package = (
            ROOT / "scripts" / "package-psp.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("USBHOSTFS_PATH=", psp_package)
        self.assertIn("usbhostfs-winusb.patch", psp_package)

    def test_public_source_has_no_local_workspace_identity(self) -> None:
        public_files = (
            ROOT / "README.md",
            ROOT / "CHANGELOG.md",
            ROOT / "SECURITY.md",
            ROOT / "docs" / "usb.md",
            ROOT / "packaging" / "README-WINDOWS.txt",
            ROOT / "packaging" / "README-PSP.txt",
            ROOT / "scripts" / "build-windows.ps1",
            ROOT / "scripts" / "package-release.ps1",
        )
        forbidden = ("niw3k", "codex-clipboard", "AppData\\Local\\Temp")
        for path in public_files:
            with self.subTest(path=path.relative_to(ROOT)):
                text = path.read_text(encoding="utf-8")
                self.assertFalse(any(value in text for value in forbidden))

    def test_windows_manifest_is_embedded_and_verified(self) -> None:
        manifest = (
            ROOT / "packaging" / "windows" / "niwPSPtoPC.exe.manifest"
        ).read_text(encoding="utf-8")
        build = (ROOT / "scripts" / "build-windows.ps1").read_text(
            encoding="utf-8"
        )
        verify = (
            ROOT / "scripts" / "verify-windows-package.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("PerMonitorV2", manifest)
        self.assertIn("--manifest $Manifest", build)
        self.assertIn("PerMonitorV2", verify)

    def test_psp_sender_has_reconnect_and_nonblocking_input(self) -> None:
        source = (ROOT / "psp-client" / "src" / "main.c").read_text(
            encoding="utf-8"
        )
        self.assertIn("sceCtrlPeekBufferPositive(pad, 1)", source)
        self.assertIn("reconnect_wifi_and_socket", source)
        self.assertIn("RECONNECT_BACKOFF_MAX_SECONDS 10U", source)
        self.assertIn("PSP_NET_APCTL_STATE_GOT_IP", source)
        self.assertIn("MAX_ACK_DATAGRAMS_PER_CYCLE 32U", source)
        self.assertIn(
            "ack_count < MAX_ACK_DATAGRAMS_PER_CYCLE",
            source,
        )
        self.assertIn("set_performance_clock();", source)
        self.assertIn("set_power_save_clock();", source)
        self.assertIn("POWER_SAVE_CPU_MHZ 111", source)
        self.assertIn("POWER_SAVE_BUS_MHZ 55", source)
        self.assertIn("DISPLAY_SLEEP_DELAY_US", source)
        self.assertIn("backlight_turn_off(backlight);", source)
        self.assertIn("backlight_turn_on(backlight);", source)
        self.assertIn("PSP_CTRL_HOME | PSP_CTRL_SCREEN", source)
        self.assertIn('"sceDisplay_Service"', source)
        self.assertIn('"sceDisplay_driver"', source)
        self.assertIn("sctrlHENFindFunction(", source)
        self.assertIn("DISPLAY_SET_BRIGHTNESS_NID", source)
        self.assertIn("DISPLAY_GET_BRIGHTNESS_NID", source)

        makefile = (ROOT / "psp-client" / "Makefile").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("-lpspdisplay_driver", makefile)
        self.assertIn("-lpspsystemctrl_user", makefile)
        self.assertIn("-lpspkubridge", makefile)


if __name__ == "__main__":
    unittest.main()
