from __future__ import annotations

import unittest
from unittest.mock import patch

from pc_server.winusb_setup import (
    WINUSB_INTERFACE_GUID,
    WinUsbRepairResult,
    repair_winusb_interfaces,
)


class WinUsbSetupTests(unittest.TestCase):
    @patch("pc_server.winusb_setup._restart_instance")
    @patch("pc_server.winusb_setup._is_present", return_value=True)
    @patch("pc_server.winusb_setup._configure_instance")
    @patch(
        "pc_server.winusb_setup._iter_winusb_psp_instances",
        return_value=[r"USB\VID_054C&PID_01C9\INSTANCE"],
    )
    def test_repair_configures_and_restarts_only_present_psp(
        self,
        _instances,
        configure,
        _present,
        restart,
    ) -> None:
        result = repair_winusb_interfaces()

        self.assertTrue(result.succeeded)
        configure.assert_called_once_with(r"USB\VID_054C&PID_01C9\INSTANCE")
        restart.assert_called_once_with(r"USB\VID_054C&PID_01C9\INSTANCE")
        self.assertEqual(
            result,
            WinUsbRepairResult(
                configured=(r"USB\VID_054C&PID_01C9\INSTANCE",),
                restarted=(r"USB\VID_054C&PID_01C9\INSTANCE",),
                errors=(),
            ),
        )

    @patch("pc_server.winusb_setup._restart_instance")
    @patch("pc_server.winusb_setup._is_present", return_value=False)
    @patch("pc_server.winusb_setup._configure_instance")
    @patch(
        "pc_server.winusb_setup._iter_winusb_psp_instances",
        return_value=[r"USB\VID_054C&PID_01C9\OLD"],
    )
    def test_phantom_instance_is_not_modified(
        self,
        _instances,
        configure,
        _present,
        restart,
    ) -> None:
        result = repair_winusb_interfaces()

        self.assertFalse(result.succeeded)
        configure.assert_not_called()
        restart.assert_not_called()
        self.assertEqual(
            result,
            WinUsbRepairResult(
                configured=(),
                restarted=(),
                errors=(),
            ),
        )

    def test_interface_guid_is_stable(self) -> None:
        self.assertEqual(
            WINUSB_INTERFACE_GUID,
            "{25B21F00-3140-49D7-9625-1F109B77ECFA}",
        )


if __name__ == "__main__":
    unittest.main()
