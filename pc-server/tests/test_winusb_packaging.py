from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "psp-client" / "vendor" / "usbhostfs-winusb.patch"
BUILD_SCRIPT = ROOT / "scripts" / "build-usbhostfs.sh"
USB_TRANSPORT = ROOT / "psp-client" / "src" / "usb_transport.c"
PSP_MAIN = ROOT / "psp-client" / "src" / "main.c"
PSP_UI = ROOT / "psp-client" / "src" / "ui.c"
WINDOWS_SETUP = ROOT / "pc-server" / "pc_server" / "winusb_setup.py"
WINDOWS_GUI = ROOT / "pc-server" / "pc_server" / "gui.py"


class WinUsbPackagingTests(unittest.TestCase):
    def test_usbhostfs_reports_inbox_winusb_compatibility(self) -> None:
        source = PATCH.read_text(encoding="utf-8")
        self.assertIn(
            "'M', 0, 'S', 0, 'F', 0, 'T', 0, '1', 0, '0', 0, '0', 0",
            source,
        )
        self.assertIn("'W', 'I', 'N', 'U', 'S', 'B'", source)
        self.assertIn("sizeof(strp) == 18", source)
        self.assertIn("winusb_compatible_id) == 40", source)
        self.assertIn("winusb_extended_properties) == 142", source)
        self.assertIn("req->wValue == 0x0000", source)
        self.assertIn("req->wValue == 0x03EE", source)
        self.assertEqual(source.count("+\t.bcdDevice = 0x102"), 2)
        self.assertIn("req->bmRequestType == 0xC1", source)
        self.assertIn("niwUsbGetDescriptorDebug", source)

    def test_usbhostfs_registers_stable_device_interface_guid(self) -> None:
        source = PATCH.read_text(encoding="utf-8")
        self.assertIn("DeviceInterfaceGUID", source)
        self.assertIn("{25B21F00-3140-49D7-9625-1F109B77ECFA}", source)

    def test_pinned_usbhostfs_is_patched_before_build(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        apply_position = script.index("apply --recount")
        build_position = script.index('make -C "$BUILD_DIR/usbhostfs"')
        self.assertLess(apply_position, build_position)
        self.assertIn("usbhostfs-winusb.patch", script)

    def test_kernel_usbhostfs_exports_use_privilege_bridge(self) -> None:
        source = USB_TRANSPORT.read_text(encoding="utf-8")
        self.assertIn("kuKernelCall((void *)(uintptr_t)address, &args)", source)
        self.assertIn("return (int32_t)args.ret1;", source)
        self.assertNotIn("transport->async_register(", source)
        self.assertNotIn("transport->async_write(", source)

    def test_psp_uses_explicit_nonfatal_transport_menu(self) -> None:
        source = PSP_MAIN.read_text(encoding="utf-8")
        ui_source = PSP_UI.read_text(encoding="utf-8")
        self.assertIn("select_transport(selected_transport)", source)
        self.assertIn("ui_render_transport_selector(selected, wifi_available)", source)
        self.assertIn('"CONNECT USB DATA CABLE"', source)
        self.assertIn("!usb_transport_cable_connected()", source)
        self.assertIn("return LINK_RESULT_MENU;", source)
        self.assertIn(
            "(pressed & (PSP_CTRL_LEFT | PSP_CTRL_RIGHT)) != 0",
            source,
        )
        self.assertIn("LINK_MENU_CHORD", source)
        self.assertIn('"WLAN SWITCH OFF"', ui_source)
        self.assertIn('"NO CODE REQUIRED"', ui_source)
        self.assertIn('"RETURNING TO CONNECTION MENU..."', ui_source)

    def test_usb_status_does_not_claim_wifi_is_connected(self) -> None:
        source = PSP_UI.read_text(encoding="utf-8")
        self.assertIn('"TRANSPORT"', source)
        self.assertIn('is_usb ? "USB" : "WI-FI"', source)
        self.assertIn('"WINDOWS USB ENUMERATION"', source)

    def test_windows_app_can_finish_inbox_winusb_registration(self) -> None:
        source = WINDOWS_SETUP.read_text(encoding="utf-8")
        gui_source = WINDOWS_GUI.read_text(encoding="utf-8")
        self.assertIn("SetupDiOpenDevRegKey", source)
        self.assertNotIn("winreg.HKEYType", source)
        self.assertIn('"DeviceInterfaceGUIDs"', source)
        self.assertIn('"pnputil.exe", "/restart-device"', source)
        self.assertIn('"runas"', source)
        self.assertIn('"--repair-winusb"', gui_source)


if __name__ == "__main__":
    unittest.main()
