"""One-time Windows provisioning for the inbox WinUSB device interface.

USBHostFS can identify itself as a WinUSB device with the short Microsoft OS
compatible-ID descriptor.  Some PSP firmware/USB combinations do not deliver
the longer extended-properties descriptor reliably, so Windows binds its
signed WinUSB driver but does not create an application-visible interface.

The normal desktop process detects that exact state and launches itself once
with elevation.  The elevated helper registers the same interface property an
INF package would add and restarts only matching, present PSP devices.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import subprocess
import sys
import winreg
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)

PSP_USB_ENUM_KEY = r"SYSTEM\CurrentControlSet\Enum\USB\VID_054C&PID_01C9"
WINUSB_SERVICE = "WINUSB"
WINUSB_INTERFACE_GUID = "{25B21F00-3140-49D7-9625-1F109B77ECFA}"
REPAIR_ARGUMENT = "--repair-winusb"
REPAIR_REPORT_NAME = "winusb-repair.json"
SW_HIDE = 0
CM_LOCATE_DEVNODE_NORMAL = 0
CR_SUCCESS = 0
DICS_FLAG_GLOBAL = 0x00000001
DIREG_DEV = 0x00000001
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class _Guid(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _SpDevInfoData(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", _Guid),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.c_size_t),
    ]


@dataclass(frozen=True, slots=True)
class WinUsbRepairResult:
    configured: tuple[str, ...]
    restarted: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def succeeded(self) -> bool:
        return bool(self.configured) and not self.errors


def write_repair_report(result: WinUsbRepairResult) -> Path:
    """Persist helper diagnostics where the normal desktop process can read it."""
    base = Path(
        os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
    )
    report_directory = base / "niwPSPtoPC"
    report_directory.mkdir(parents=True, exist_ok=True)
    report_path = report_directory / REPAIR_REPORT_NAME
    report_path.write_text(
        json.dumps(
            {
                "succeeded": result.succeeded,
                "configured": result.configured,
                "restarted": result.restarted,
                "errors": result.errors,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return report_path


def _iter_winusb_psp_instances() -> list[str]:
    instances: list[str] = []
    access = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            PSP_USB_ENUM_KEY,
            0,
            access,
        ) as product_key:
            index = 0
            while True:
                try:
                    instance_name = winreg.EnumKey(product_key, index)
                except OSError:
                    break
                index += 1
                with winreg.OpenKey(product_key, instance_name, 0, access) as key:
                    try:
                        service, _value_type = winreg.QueryValueEx(key, "Service")
                    except FileNotFoundError:
                        continue
                if str(service).upper() == WINUSB_SERVICE:
                    instances.append(
                        rf"USB\VID_054C&PID_01C9\{instance_name}"
                    )
    except FileNotFoundError:
        return []
    return instances


def _configure_instance(instance_id: str) -> None:
    setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    create_list = setupapi.SetupDiCreateDeviceInfoList
    create_list.argtypes = [ctypes.POINTER(_Guid), wintypes.HWND]
    create_list.restype = wintypes.HANDLE
    open_info = setupapi.SetupDiOpenDeviceInfoW
    open_info.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCWSTR,
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.POINTER(_SpDevInfoData),
    ]
    open_info.restype = wintypes.BOOL
    open_key = setupapi.SetupDiOpenDevRegKey
    open_key.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_SpDevInfoData),
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    open_key.restype = wintypes.HANDLE
    destroy_list = setupapi.SetupDiDestroyDeviceInfoList
    destroy_list.argtypes = [wintypes.HANDLE]
    destroy_list.restype = wintypes.BOOL

    device_set = create_list(None, None)
    if device_set == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        device_info = _SpDevInfoData()
        device_info.cbSize = ctypes.sizeof(device_info)
        if not open_info(
            device_set,
            instance_id,
            None,
            0,
            ctypes.byref(device_info),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        raw_key = open_key(
            device_set,
            ctypes.byref(device_info),
            DICS_FLAG_GLOBAL,
            0,
            DIREG_DEV,
            winreg.KEY_SET_VALUE,
        )
        if raw_key == INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            # DeviceInterfaceGUIDs is the value used by WinUSB INF packages.
            # The singular value mirrors the Microsoft OS 1.0 property name.
            winreg.SetValueEx(
                raw_key,
                "DeviceInterfaceGUIDs",
                0,
                winreg.REG_MULTI_SZ,
                [WINUSB_INTERFACE_GUID],
            )
            winreg.SetValueEx(
                raw_key,
                "DeviceInterfaceGUID",
                0,
                winreg.REG_SZ,
                WINUSB_INTERFACE_GUID,
            )
        finally:
            winreg.CloseKey(raw_key)
    finally:
        destroy_list(device_set)


def _is_present(instance_id: str) -> bool:
    cfgmgr32 = ctypes.WinDLL("cfgmgr32", use_last_error=True)
    locate = cfgmgr32.CM_Locate_DevNodeW
    locate.argtypes = [
        ctypes.POINTER(wintypes.ULONG),
        wintypes.LPCWSTR,
        wintypes.ULONG,
    ]
    locate.restype = wintypes.ULONG
    devinst = wintypes.ULONG()
    return (
        locate(
            ctypes.byref(devinst),
            instance_id,
            CM_LOCATE_DEVNODE_NORMAL,
        )
        == CR_SUCCESS
    )


def winusb_interface_needs_repair() -> bool:
    """Return true only for a present WinUSB PSP missing the app GUID."""
    access = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
    expected = WINUSB_INTERFACE_GUID.upper()
    for instance_id in _iter_winusb_psp_instances():
        if not _is_present(instance_id):
            continue
        key_path = (
            rf"SYSTEM\CurrentControlSet\Enum\{instance_id}\Device Parameters"
        )
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                key_path,
                0,
                access,
            ) as parameters:
                values: list[str] = []
                for value_name in (
                    "DeviceInterfaceGUIDs",
                    "DeviceInterfaceGUID",
                ):
                    try:
                        value, _value_type = winreg.QueryValueEx(
                            parameters,
                            value_name,
                        )
                    except FileNotFoundError:
                        continue
                    if isinstance(value, list):
                        values.extend(str(item) for item in value)
                    else:
                        values.append(str(value))
        except FileNotFoundError:
            return True
        if not any(value.upper() == expected for value in values):
            return True
    return False


def _restart_instance(instance_id: str) -> None:
    completed = subprocess.run(
        ["pnputil.exe", "/restart-device", instance_id],
        check=False,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(detail or f"pnputil exited with {completed.returncode}")


def repair_winusb_interfaces() -> WinUsbRepairResult:
    """Register the app interface and restart matching present PSP devices."""
    configured: list[str] = []
    restarted: list[str] = []
    errors: list[str] = []

    for instance_id in _iter_winusb_psp_instances():
        if not _is_present(instance_id):
            continue
        try:
            _configure_instance(instance_id)
            configured.append(instance_id)
            _restart_instance(instance_id)
            restarted.append(instance_id)
        except Exception as exc:
            errors.append(f"{instance_id}: {exc}")

    return WinUsbRepairResult(
        tuple(configured),
        tuple(restarted),
        tuple(errors),
    )


def _elevation_command() -> tuple[str, str, str]:
    if getattr(sys, "frozen", False):
        executable = sys.executable
        parameters = subprocess.list2cmdline([REPAIR_ARGUMENT])
    else:
        executable = sys.executable
        parameters = subprocess.list2cmdline(
            ["-m", "pc_server.gui", REPAIR_ARGUMENT]
        )
    return executable, parameters, str(Path(executable).resolve().parent)


def request_elevated_winusb_repair() -> bool:
    """Launch the narrowly scoped repair helper through the standard UAC flow."""
    if os.name != "nt":
        return False
    executable, parameters, working_directory = _elevation_command()
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        parameters,
        working_directory,
        SW_HIDE,
    )
    launched = int(result) > 32
    if launched:
        LOGGER.info(
            "Requested one-time elevated WinUSB interface registration"
        )
    else:
        LOGGER.info("WinUSB interface registration was not authorized")
    return launched
