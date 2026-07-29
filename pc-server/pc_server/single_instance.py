"""Windows named-mutex guard for the desktop GUI."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os


ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    def __init__(self, name: str) -> None:
        self.name = name
        self.acquired = True
        self._handle: wintypes.HANDLE | None = None
        self._kernel32: object | None = None

    def __enter__(self) -> SingleInstance:
        if os.name != "nt":
            return self
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = (
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        create_mutex.restype = wintypes.HANDLE
        handle = create_mutex(None, False, self.name)
        if not handle:
            raise ctypes.WinError()
        self._kernel32 = kernel32
        self._handle = handle
        self.acquired = ctypes.get_last_error() != ERROR_ALREADY_EXISTS
        return self

    def __exit__(self, *_args: object) -> None:
        if self._handle is not None and self._kernel32 is not None:
            close_handle = self._kernel32.CloseHandle  # type: ignore[attr-defined]
            close_handle.argtypes = (wintypes.HANDLE,)
            close_handle.restype = wintypes.BOOL
            close_handle(self._handle)
            self._handle = None
            self._kernel32 = None

    @staticmethod
    def show_already_running_message() -> None:
        if os.name == "nt":
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            message_box = user32.MessageBoxW
            message_box.argtypes = (
                wintypes.HWND,
                wintypes.LPCWSTR,
                wintypes.LPCWSTR,
                wintypes.UINT,
            )
            message_box.restype = ctypes.c_int
            message_box(
                None,
                "niwPSPtoPC is already running.",
                "niwPSPtoPC",
                0x00000040,
            )
