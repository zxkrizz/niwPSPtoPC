"""Pixel-art Windows pairing UI for niwPSPtoPC."""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk

from . import __version__
from .connection_doctor import ConnectionDoctor, DoctorStage
from .gamepad import (
    BackendFailureKind,
    ControllerEvent,
    ControllerEventType,
    ControllerService,
)
from .gui_settings import (
    APP_NAME,
    load_settings,
    save_settings,
    validate_bind_settings,
)
from .protocol import Buttons, InputPacket, format_pairing_token, parse_pairing_token
from .receiver import (
    ReceiverEvent,
    ReceiverSnapshot,
    ReceiverStage,
    UdpReceiver,
)
from .single_instance import SingleInstance
from .windows_diagnostics import collect_windows_network_diagnostics

COLOR_BG = "#061014"
COLOR_BG_GRID = "#0B1A1E"
COLOR_PANEL = "#0D1C20"
COLOR_PANEL_LIGHT = "#13282B"
COLOR_BORDER = "#2C4B4C"
COLOR_TEXT = "#E9FFF7"
COLOR_MUTED = "#82A9A0"
COLOR_ACCENT = "#64F1BD"
COLOR_ACCENT_DARK = "#173D34"
COLOR_BLUE = "#70C8FF"
COLOR_WARN = "#FFD166"
COLOR_DANGER = "#FF7182"
COLOR_INK = "#04100D"
COLOR_PSP = "#1A2529"
COLOR_PSP_LIGHT = "#33464A"
COLOR_CONTROL = "#2A3B40"
COLOR_SCREEN = "#08261F"
COLOR_SCREEN_GRID = "#10382E"
PIXEL_FONT = "Cascadia Mono"


BUTTON_LABELS = {
    Buttons.UP: "UP",
    Buttons.DOWN: "DOWN",
    Buttons.LEFT: "LEFT",
    Buttons.RIGHT: "RIGHT",
    Buttons.CROSS: "CROSS",
    Buttons.CIRCLE: "CIRCLE",
    Buttons.SQUARE: "SQUARE",
    Buttons.TRIANGLE: "TRIANGLE",
    Buttons.L: "L",
    Buttons.R: "R",
    Buttons.START: "START",
    Buttons.SELECT: "SELECT",
}


class PixelPspView(tk.Canvas):
    """A deliberately low-resolution PSP view that mirrors live input."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(
            master,
            width=590,
            height=400,
            bg=COLOR_PANEL,
            highlightthickness=0,
            bd=0,
        )
        self._button_items: dict[Buttons, list[int]] = {}
        self._analog_center = (116, 277)
        self._analog_marker: int
        self._link_text: int
        self._link_detail: int
        self._axis_text: int
        self._input_text: int
        self._draw()
        self.set_link_state("PAIRING MODE", "ENTER CODE ON PC")
        self.neutralize()

    def _draw(self) -> None:
        for x in range(18, 590, 16):
            self.create_line(x, 16, x, 380, fill=COLOR_BG_GRID)
        for y in range(16, 381, 16):
            self.create_line(18, y, 572, y, fill=COLOR_BG_GRID)

        self.create_text(
            24,
            22,
            text="LIVE INPUT // PSP",
            anchor="w",
            fill=COLOR_MUTED,
            font=(PIXEL_FONT, 9, "bold"),
        )
        self.create_rectangle(
            454,
            16,
            566,
            30,
            fill=COLOR_ACCENT_DARK,
            outline="",
        )
        self._rate_text = self.create_text(
            510,
            23,
            text="-- HZ INPUT",
            fill=COLOR_ACCENT,
            font=(PIXEL_FONT, 7, "bold"),
        )

        self.create_polygon(
            62,
            78,
            78,
            62,
            512,
            62,
            528,
            78,
            548,
            110,
            548,
            306,
            530,
            330,
            510,
            342,
            80,
            342,
            60,
            330,
            42,
            306,
            42,
            110,
            fill="#050A0C",
            outline="",
        )
        self.create_polygon(
            66,
            72,
            82,
            58,
            508,
            58,
            524,
            72,
            542,
            108,
            542,
            300,
            524,
            326,
            504,
            336,
            86,
            336,
            66,
            326,
            48,
            300,
            48,
            108,
            fill=COLOR_PSP,
            outline=COLOR_PSP_LIGHT,
            width=2,
        )
        self.create_line(
            72,
            82,
            518,
            82,
            fill=COLOR_PSP_LIGHT,
            width=2,
        )

        self._draw_shoulder(Buttons.L, 72, 54, 172, 78, "L")
        self._draw_shoulder(Buttons.R, 418, 54, 518, 78, "R")
        self._draw_screen()
        self._draw_dpad()
        self._draw_face_buttons()
        self._draw_analog()
        self._draw_small_button(Buttons.SELECT, 248, 286, 294, 301, "SELECT")
        self._draw_small_button(Buttons.START, 306, 286, 352, 301, "START")

        self.create_rectangle(
            22,
            360,
            568,
            386,
            fill=COLOR_PANEL_LIGHT,
            outline=COLOR_BORDER,
        )
        self._input_text = self.create_text(
            34,
            373,
            text="INPUT // ---",
            anchor="w",
            fill=COLOR_TEXT,
            font=(PIXEL_FONT, 8, "bold"),
        )

    def _draw_screen(self) -> None:
        self.create_rectangle(
            165,
            100,
            425,
            260,
            fill="#030807",
            outline=COLOR_PSP_LIGHT,
            width=2,
        )
        self.create_rectangle(
            174,
            109,
            416,
            251,
            fill=COLOR_SCREEN,
            outline=COLOR_BORDER,
        )
        for x in range(182, 416, 12):
            self.create_line(x, 109, x, 251, fill=COLOR_SCREEN_GRID)
        for y in range(117, 252, 12):
            self.create_line(174, y, 416, y, fill=COLOR_SCREEN_GRID)
        self.create_text(
            187,
            124,
            text="[+] NIW LINK / V2",
            anchor="w",
            fill=COLOR_ACCENT,
            font=(PIXEL_FONT, 8, "bold"),
        )
        self.create_rectangle(186, 138, 404, 140, fill=COLOR_BORDER, outline="")
        self._link_text = self.create_text(
            295,
            169,
            text="PAIRING MODE",
            fill=COLOR_TEXT,
            font=(PIXEL_FONT, 13, "bold"),
        )
        self._link_detail = self.create_text(
            295,
            192,
            text="ENTER CODE ON PC",
            fill=COLOR_MUTED,
            font=(PIXEL_FONT, 8),
        )
        self._axis_text = self.create_text(
            295,
            230,
            text="LX 128  //  LY 128",
            fill=COLOR_ACCENT,
            font=(PIXEL_FONT, 8, "bold"),
        )

    def _register_button(
        self,
        button: Buttons,
        shape: int,
        label: int,
    ) -> None:
        self._button_items[button] = [shape, label]

    def _draw_shoulder(
        self,
        button: Buttons,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        label: str,
    ) -> None:
        shape = self.create_polygon(
            x1,
            y1 + 7,
            x1 + 9,
            y1,
            x2 - 9,
            y1,
            x2,
            y1 + 7,
            x2,
            y2,
            x1,
            y2,
            fill=COLOR_CONTROL,
            outline=COLOR_PSP_LIGHT,
        )
        text = self.create_text(
            (x1 + x2) // 2,
            (y1 + y2) // 2 + 1,
            text=label,
            fill=COLOR_MUTED,
            font=(PIXEL_FONT, 8, "bold"),
        )
        self._register_button(button, shape, text)

    def _draw_dpad(self) -> None:
        self.create_polygon(
            94,
            145,
            116,
            145,
            116,
            171,
            142,
            171,
            142,
            195,
            116,
            195,
            116,
            221,
            94,
            221,
            94,
            195,
            68,
            195,
            68,
            171,
            94,
            171,
            fill="#05090A",
            outline=COLOR_PSP_LIGHT,
        )
        regions = (
            (Buttons.UP, (96, 147, 114, 178), "▲"),
            (Buttons.DOWN, (96, 188, 114, 219), "▼"),
            (Buttons.LEFT, (70, 173, 101, 193), "◀"),
            (Buttons.RIGHT, (109, 173, 140, 193), "▶"),
        )
        for button, coordinates, label in regions:
            x1, y1, x2, y2 = coordinates
            shape = self.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill=COLOR_CONTROL,
                outline="",
            )
            text = self.create_text(
                (x1 + x2) // 2,
                (y1 + y2) // 2,
                text=label,
                fill=COLOR_MUTED,
                font=("Segoe UI Symbol", 8, "bold"),
            )
            self._register_button(button, shape, text)
        self.create_rectangle(97, 175, 113, 191, fill="#152126", outline="")

    def _draw_face_button(
        self,
        button: Buttons,
        x: int,
        y: int,
        label: str,
    ) -> None:
        shape = self.create_polygon(
            x - 13,
            y - 7,
            x - 7,
            y - 13,
            x + 7,
            y - 13,
            x + 13,
            y - 7,
            x + 13,
            y + 7,
            x + 7,
            y + 13,
            x - 7,
            y + 13,
            x - 13,
            y + 7,
            fill=COLOR_CONTROL,
            outline=COLOR_PSP_LIGHT,
        )
        text = self.create_text(
            x,
            y,
            text=label,
            fill=COLOR_MUTED,
            font=("Segoe UI Symbol", 9, "bold"),
        )
        self._register_button(button, shape, text)

    def _draw_face_buttons(self) -> None:
        self._draw_face_button(Buttons.TRIANGLE, 486, 150, "△")
        self._draw_face_button(Buttons.CIRCLE, 518, 183, "○")
        self._draw_face_button(Buttons.CROSS, 486, 216, "×")
        self._draw_face_button(Buttons.SQUARE, 454, 183, "□")

    def _draw_analog(self) -> None:
        x, y = self._analog_center
        self.create_polygon(
            x - 23,
            y - 14,
            x - 14,
            y - 23,
            x + 14,
            y - 23,
            x + 23,
            y - 14,
            x + 23,
            y + 14,
            x + 14,
            y + 23,
            x - 14,
            y + 23,
            x - 23,
            y + 14,
            fill="#05090A",
            outline=COLOR_PSP_LIGHT,
        )
        self._analog_marker = self.create_rectangle(
            x - 10,
            y - 10,
            x + 10,
            y + 10,
            fill=COLOR_CONTROL,
            outline=COLOR_MUTED,
        )
        self.create_text(
            x,
            y + 34,
            text="ANALOG",
            fill=COLOR_MUTED,
            font=(PIXEL_FONT, 6, "bold"),
        )

    def _draw_small_button(
        self,
        button: Buttons,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        label: str,
    ) -> None:
        shape = self.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            fill=COLOR_CONTROL,
            outline=COLOR_PSP_LIGHT,
        )
        text = self.create_text(
            (x1 + x2) // 2,
            (y1 + y2) // 2,
            text=label,
            fill=COLOR_MUTED,
            font=(PIXEL_FONT, 6, "bold"),
        )
        self._register_button(button, shape, text)

    def set_link_state(self, title: str, detail: str) -> None:
        self.itemconfigure(self._link_text, text=title)
        self.itemconfigure(self._link_detail, text=detail)

    def set_packet(self, packet: InputPacket) -> None:
        pressed = packet.pressed_buttons
        for button, items in self._button_items.items():
            active = bool(pressed & button)
            self.itemconfigure(
                items[0],
                fill=COLOR_ACCENT if active else COLOR_CONTROL,
            )
            self.itemconfigure(
                items[1],
                fill=COLOR_INK if active else COLOR_MUTED,
            )

        x, y = self._analog_center
        offset_x = round((packet.analog_x - 128) * 11 / 127)
        offset_y = round((packet.analog_y - 128) * 11 / 127)
        marker_x = x + max(-11, min(11, offset_x))
        marker_y = y + max(-11, min(11, offset_y))
        self.coords(
            self._analog_marker,
            marker_x - 10,
            marker_y - 10,
            marker_x + 10,
            marker_y + 10,
        )
        self.itemconfigure(
            self._analog_marker,
            fill=(
                COLOR_ACCENT
                if packet.analog_x != 128 or packet.analog_y != 128
                else COLOR_CONTROL
            ),
        )
        self.itemconfigure(
            self._axis_text,
            text=f"LX {packet.analog_x:03d}  //  LY {packet.analog_y:03d}",
        )
        labels = [
            label
            for button, label in BUTTON_LABELS.items()
            if pressed & button
        ]
        summary = " + ".join(labels) if labels else "---"
        if len(summary) > 55:
            summary = summary[:52] + "..."
        self.itemconfigure(self._input_text, text=f"INPUT // {summary}")

    def neutralize(self) -> None:
        self.set_packet(
            InputPacket(
                sequence=0,
                buttons=0,
                analog_x=128,
                analog_y=128,
                timestamp_us=0,
            )
        )

    def set_input_rate(self, packets_per_second: float) -> None:
        rate = max(0, round(packets_per_second))
        self.itemconfigure(self._rate_text, text=f"{rate:02d} HZ INPUT")


class NiwPspToPcApp:
    def __init__(self, root: tk.Tk, *, auto_start: bool = True) -> None:
        self.root = root
        self.root.title(f"{APP_NAME} — PSP Wi-Fi Controller")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(1120, max(720, screen_width - 80))
        height = min(700, max(520, screen_height - 80))
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(
            min(900, max(640, screen_width - 120)),
            min(560, max(480, screen_height - 120)),
        )
        self.root.configure(bg=COLOR_BG)

        self._settings = load_settings()
        self._doctor = ConnectionDoctor()
        self._doctor_port = self._settings.port
        self._messages: queue.Queue[tuple[str, object | None]] = queue.Queue()
        self._receiver: UdpReceiver | None = None
        self._receiver_thread: threading.Thread | None = None
        self._controller_service: ControllerService | None = None
        self._running = False
        self._closing = False
        self._paired_address: tuple[str, int] | None = None
        self._active_token: int | None = None
        self._doctor_row_labels: list[tk.Label] = []
        self._doctor_window: tk.Toplevel | None = None
        self._doctor_text: tk.Text | None = None
        self._settings_window: tk.Toplevel | None = None
        self._restart_pending = False
        self._compact_layout = False
        self._short_layout = False

        self.code_var = tk.StringVar()
        self.status_var = tk.StringVar(value="BOOTING RECEIVER…")
        self.status_detail_var = tk.StringVar(
            value="The pairing code field will be ready in a moment."
        )
        self.gamepad_var = tk.StringVar(value="OFFLINE")

        self._configure_styles()
        self._build_ui()
        self.root.bind("<Configure>", self._on_window_resize)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(50, self._poll_messages)
        self.root.after(300, self._refresh_system_diagnostics)
        self.root.after(1000, self._refresh_live_diagnostics)
        if auto_start:
            self.root.after(150, self.start_receiver)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

    def _build_ui(self) -> None:
        shell = tk.Frame(self.root, bg=COLOR_BG)
        shell.pack(fill="both", expand=True, padx=30, pady=24)
        self._build_header(shell)

        self._content = tk.Frame(shell, bg=COLOR_BG)
        self._content.pack(fill="both", expand=True, pady=(20, 0))
        self._content.grid_columnconfigure(0, weight=5)
        self._content.grid_columnconfigure(1, weight=3)
        self._content.grid_rowconfigure(0, weight=1)

        self._visual_panel = tk.Frame(
            self._content,
            bg=COLOR_PANEL,
            highlightbackground=COLOR_BORDER,
            highlightthickness=2,
        )
        self._visual_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 10),
        )
        self.controller_view = PixelPspView(self._visual_panel)
        self.controller_view.pack(expand=True, padx=8, pady=8)

        self._pairing_panel = tk.Frame(
            self._content,
            bg=COLOR_PANEL,
            highlightbackground=COLOR_BORDER,
            highlightthickness=2,
        )
        self._pairing_panel.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(10, 0),
        )
        self._build_pairing_card(self._pairing_panel)

        self._footer = tk.Frame(shell, bg=COLOR_BG)
        self._footer.pack(fill="x", pady=(12, 0))
        tk.Label(
            self._footer,
            text="PSP 1000-GO  //  ONE ANALOG  //  XINPUT",
            bg=COLOR_BG,
            fg=COLOR_MUTED,
            font=(PIXEL_FONT, 8, "bold"),
        ).pack(side="left")
        tk.Label(
            self._footer,
            text="HOME NETWORK TOOL",
            bg=COLOR_BG,
            fg=COLOR_BORDER,
            font=(PIXEL_FONT, 8, "bold"),
        ).pack(side="right")

    def _on_window_resize(self, event: tk.Event[tk.Misc]) -> None:
        if event.widget is not self.root:
            return
        compact = event.width < 1000
        if compact != self._compact_layout:
            self._compact_layout = compact
            if compact:
                self._visual_panel.grid_remove()
                self._pairing_panel.grid_configure(
                    column=0,
                    columnspan=2,
                    padx=0,
                )
            else:
                self._visual_panel.grid()
                self._pairing_panel.grid_configure(
                    column=1,
                    columnspan=1,
                    padx=(10, 0),
                )
        short = event.height < 620
        if short == self._short_layout:
            return
        self._short_layout = short
        if short:
            self._link_status_caption.pack_forget()
            self._pair_section_label.pack_forget()
            self._pair_help_label.pack_forget()
            self._gamepad_panel.pack_forget()
            self._footer.pack_forget()
        else:
            self._link_status_caption.pack(
                anchor="w",
                before=self._status_row,
            )
            self._pair_section_label.pack(
                anchor="w",
                before=self.code_entry,
            )
            self._pair_help_label.pack(
                anchor="w",
                pady=(6, 11),
                before=self.code_entry,
            )
            self._gamepad_panel.pack(
                fill="x",
                side="bottom",
                pady=(5, 0),
            )
            self._footer.pack(fill="x", pady=(12, 0))

    def _build_header(self, master: tk.Misc) -> None:
        header = tk.Frame(master, bg=COLOR_BG)
        header.pack(fill="x")

        logo = tk.Canvas(
            header,
            width=50,
            height=50,
            bg=COLOR_BG,
            highlightthickness=0,
        )
        logo.pack(side="left")
        logo.create_rectangle(4, 4, 46, 46, fill=COLOR_ACCENT, outline="")
        logo.create_rectangle(4, 4, 12, 12, fill=COLOR_BG, outline="")
        logo.create_rectangle(38, 4, 46, 12, fill=COLOR_BG, outline="")
        logo.create_rectangle(4, 38, 12, 46, fill=COLOR_BG, outline="")
        logo.create_rectangle(38, 38, 46, 46, fill=COLOR_BG, outline="")
        logo.create_rectangle(13, 21, 29, 29, fill=COLOR_INK, outline="")
        logo.create_rectangle(17, 17, 25, 33, fill=COLOR_INK, outline="")
        logo.create_rectangle(34, 17, 39, 22, fill=COLOR_INK, outline="")
        logo.create_rectangle(39, 27, 44, 32, fill=COLOR_INK, outline="")

        title = tk.Frame(header, bg=COLOR_BG)
        title.pack(side="left", padx=(14, 0))
        tk.Label(
            title,
            text=APP_NAME,
            bg=COLOR_BG,
            fg=COLOR_TEXT,
            font=(PIXEL_FONT, 19, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title,
            text="PSP WI-FI CONTROLLER // DESKTOP LINK",
            bg=COLOR_BG,
            fg=COLOR_MUTED,
            font=(PIXEL_FONT, 8, "bold"),
        ).pack(anchor="w", pady=(4, 0))

        version = tk.Frame(
            header,
            bg=COLOR_PANEL_LIGHT,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
        )
        version.pack(side="right")
        tk.Label(
            version,
            text=f"BUILD {__version__}",
            bg=COLOR_PANEL_LIGHT,
            fg=COLOR_ACCENT,
            padx=12,
            pady=8,
            font=(PIXEL_FONT, 8, "bold"),
        ).pack()
        tk.Button(
            header,
            text="SETTINGS",
            command=self.open_settings,
            bg=COLOR_PANEL_LIGHT,
            fg=COLOR_TEXT,
            activebackground=COLOR_BORDER,
            activeforeground=COLOR_TEXT,
            relief="flat",
            bd=0,
            padx=12,
            pady=8,
            cursor="hand2",
            font=(PIXEL_FONT, 8, "bold"),
        ).pack(side="right", padx=(0, 8))

    def _build_pairing_card(self, master: tk.Misc) -> None:
        body = tk.Frame(master, bg=COLOR_PANEL)
        body.pack(fill="both", expand=True, padx=24, pady=16)

        self._link_status_caption = tk.Label(
            body,
            text="LINK STATUS",
            bg=COLOR_PANEL,
            fg=COLOR_MUTED,
            font=(PIXEL_FONT, 8, "bold"),
        )
        self._link_status_caption.pack(anchor="w")

        self._status_row = tk.Frame(body, bg=COLOR_PANEL_LIGHT)
        self._status_row.pack(fill="x", pady=(9, 0))
        self.status_dot = tk.Canvas(
            self._status_row,
            width=26,
            height=50,
            bg=COLOR_PANEL_LIGHT,
            highlightthickness=0,
        )
        self.status_dot.pack(side="left", padx=(8, 4))
        self.status_dot_item = self.status_dot.create_rectangle(
            8,
            20,
            18,
            30,
            fill=COLOR_WARN,
            outline="",
        )
        status_text = tk.Frame(self._status_row, bg=COLOR_PANEL_LIGHT)
        status_text.pack(side="left", fill="x", expand=True, padx=(4, 8))
        tk.Label(
            status_text,
            textvariable=self.status_var,
            bg=COLOR_PANEL_LIGHT,
            fg=COLOR_TEXT,
            font=(PIXEL_FONT, 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            status_text,
            textvariable=self.status_detail_var,
            bg=COLOR_PANEL_LIGHT,
            fg=COLOR_MUTED,
            justify="left",
            wraplength=270,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 0))

        tk.Frame(body, bg=COLOR_BORDER, height=2).pack(fill="x", pady=12)

        self._pair_section_label = tk.Label(
            body,
            text="01 // PAIR DEVICE",
            bg=COLOR_PANEL,
            fg=COLOR_ACCENT,
            font=(PIXEL_FONT, 9, "bold"),
        )
        self._pair_section_label.pack(anchor="w")
        self._pair_help_label = tk.Label(
            body,
            text="Enter the code displayed on the PSP.",
            bg=COLOR_PANEL,
            fg=COLOR_TEXT,
            font=("Segoe UI", 10),
        )
        self._pair_help_label.pack(anchor="w", pady=(6, 11))

        validate = (self.root.register(self._validate_code_entry), "%P")
        self.code_entry = tk.Entry(
            body,
            textvariable=self.code_var,
            bg=COLOR_SCREEN,
            fg=COLOR_ACCENT,
            insertbackground=COLOR_ACCENT,
            selectbackground=COLOR_ACCENT_DARK,
            selectforeground=COLOR_TEXT,
            relief="flat",
            bd=0,
            highlightbackground=COLOR_BORDER,
            highlightcolor=COLOR_ACCENT,
            highlightthickness=2,
            justify="center",
            font=(PIXEL_FONT, 25, "bold"),
            validate="key",
            validatecommand=validate,
        )
        self.code_entry.pack(fill="x", ipady=6)
        self.code_entry.bind("<Return>", lambda _event: self.authorize())

        self.pair_button = tk.Button(
            body,
            text="[ CONNECT PSP ]",
            command=self.authorize,
            bg=COLOR_ACCENT,
            fg=COLOR_INK,
            activebackground=COLOR_TEXT,
            activeforeground=COLOR_INK,
            relief="flat",
            bd=0,
            padx=18,
            pady=9,
            cursor="hand2",
            font=(PIXEL_FONT, 9, "bold"),
        )
        self.pair_button.pack(fill="x", pady=(8, 0))

        self.change_button = tk.Button(
            body,
            text="USE ANOTHER CODE",
            command=self.clear_pairing,
            bg=COLOR_PANEL_LIGHT,
            fg=COLOR_TEXT,
            activebackground=COLOR_BORDER,
            activeforeground=COLOR_TEXT,
            relief="flat",
            bd=0,
            padx=18,
            pady=7,
            cursor="hand2",
            font=(PIXEL_FONT, 8, "bold"),
        )
        self.change_button.pack(fill="x", pady=(6, 0))

        doctor = tk.Frame(body, bg=COLOR_PANEL)
        doctor.pack(fill="x", pady=(8, 5))
        doctor.grid_columnconfigure(0, weight=1)
        doctor.grid_columnconfigure(1, weight=1)
        tk.Label(
            doctor,
            text="CONNECTION DOCTOR",
            bg=COLOR_PANEL,
            fg=COLOR_BLUE,
            font=(PIXEL_FONT, 8, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        for index, (stage, complete) in enumerate(self._doctor.rows()):
            label = tk.Label(
                doctor,
                text=f"[{'OK' if complete else '--'}] {stage}",
                bg=COLOR_PANEL,
                fg=COLOR_MUTED,
                font=(PIXEL_FONT, 7, "bold"),
            )
            label.grid(
                row=1 + index // 2,
                column=index % 2,
                sticky="w",
                pady=(2, 0),
            )
            self._doctor_row_labels.append(label)
        self.doctor_detail_var = tk.StringVar()
        self.doctor_metrics_var = tk.StringVar(value="UDP: waiting for data")
        tk.Label(
            doctor,
            textvariable=self.doctor_metrics_var,
            bg=COLOR_PANEL,
            fg=COLOR_BLUE,
            justify="left",
            font=(PIXEL_FONT, 7, "bold"),
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))
        tk.Label(
            doctor,
            textvariable=self.doctor_detail_var,
            bg=COLOR_PANEL,
            fg=COLOR_MUTED,
            justify="left",
            wraplength=350,
            font=("Segoe UI", 7),
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(3, 0))
        tk.Button(
            doctor,
            text="OPEN DOCTOR 2.0",
            command=self.open_doctor,
            bg=COLOR_PANEL_LIGHT,
            fg=COLOR_BLUE,
            activebackground=COLOR_BORDER,
            activeforeground=COLOR_TEXT,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=(PIXEL_FONT, 7, "bold"),
        ).grid(row=6, column=0, sticky="ew", padx=(0, 3), pady=(5, 0))
        tk.Button(
            doctor,
            text="COPY REPORT",
            command=self.copy_diagnostic_report,
            bg=COLOR_PANEL_LIGHT,
            fg=COLOR_ACCENT,
            activebackground=COLOR_BORDER,
            activeforeground=COLOR_TEXT,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=(PIXEL_FONT, 7, "bold"),
        ).grid(row=6, column=1, sticky="ew", padx=(3, 0), pady=(5, 0))
        self._refresh_doctor()

        self._gamepad_panel = tk.Frame(
            body,
            bg=COLOR_SCREEN,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
        )
        self._gamepad_panel.pack(fill="x", side="bottom", pady=(5, 0))
        tk.Label(
            self._gamepad_panel,
            text="VIRTUAL PAD",
            bg=COLOR_SCREEN,
            fg=COLOR_MUTED,
            font=(PIXEL_FONT, 8, "bold"),
        ).pack(side="left", padx=12, pady=11)
        tk.Label(
            self._gamepad_panel,
            textvariable=self.gamepad_var,
            bg=COLOR_SCREEN,
            fg=COLOR_ACCENT,
            font=(PIXEL_FONT, 8, "bold"),
        ).pack(side="right", padx=12, pady=11)
        self.retry_gamepad_button = tk.Button(
            self._gamepad_panel,
            text="RETRY GAMEPAD",
            command=self.retry_gamepad,
            bg=COLOR_PANEL_LIGHT,
            fg=COLOR_WARN,
            activebackground=COLOR_BORDER,
            activeforeground=COLOR_TEXT,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=(PIXEL_FONT, 7, "bold"),
        )
        self.retry_gamepad_button.pack(side="right", padx=(4, 0), pady=7)

    @staticmethod
    def _normalize_code_text(value: str) -> str:
        return value.upper().replace(" ", "").replace("-", "")

    def _validate_code_entry(self, proposed: str) -> bool:
        normalized = self._normalize_code_text(proposed)
        if len(normalized) > 5:
            return False
        if any(
            character not in "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            for character in normalized
        ):
            return False
        if proposed != normalized:
            self.root.after(0, lambda: self.code_var.set(normalized))
        return True

    def _set_status(self, title: str, detail: str, color: str) -> None:
        self.status_var.set(title)
        self.status_detail_var.set(detail)
        self.status_dot.itemconfigure(self.status_dot_item, fill=color)

    def _refresh_doctor(self) -> None:
        rows = self._doctor.rows()
        for label, (stage, complete) in zip(
            getattr(self, "_doctor_row_labels", []),
            rows,
        ):
            label.configure(
                text=f"[{'OK' if complete else '--'}] {stage}",
                fg=COLOR_ACCENT if complete else COLOR_MUTED,
            )
        if hasattr(self, "doctor_detail_var"):
            self.doctor_detail_var.set(
                self._doctor.guidance(port=self._doctor_port)
            )
        metrics = self._doctor.metrics
        if hasattr(self, "doctor_metrics_var") and metrics is not None:
            age = (
                f"{metrics.last_datagram_age_s:.1f}s"
                if metrics.last_datagram_age_s is not None
                else "never"
            )
            self.doctor_metrics_var.set(
                f"UDP {metrics.valid_packets} OK / "
                f"{metrics.rejected_datagrams} REJECTED  //  "
                f"{metrics.packets_per_second:.0f} HZ  //  "
                f"LOSS {metrics.loss_percent:.1f}%  //  LAST {age}"
            )
        self._update_doctor_window()

    def _diagnostic_report(self) -> str:
        receiver = self._receiver
        active_client = receiver.active_client if receiver is not None else None
        settings = self._settings
        return self._doctor.diagnostic_report(
            app_version=__version__,
            configured_host=settings.host,
            port=settings.port,
            allowed_hosts=settings.allowed_hosts,
            active_client=active_client,
        )

    def _update_doctor_window(self) -> None:
        text = getattr(self, "_doctor_text", None)
        window = getattr(self, "_doctor_window", None)
        if (
            text is None
            or window is None
            or not window.winfo_exists()
        ):
            return
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", self._diagnostic_report())
        text.configure(state="disabled")

    def open_doctor(self) -> None:
        if (
            self._doctor_window is not None
            and self._doctor_window.winfo_exists()
        ):
            self._doctor_window.lift()
            self._doctor_window.focus_force()
            return
        window = tk.Toplevel(self.root)
        self._doctor_window = window
        window.title("Connection Doctor 2.0")
        window.geometry("720x560")
        window.minsize(560, 420)
        window.configure(bg=COLOR_BG)
        text = tk.Text(
            window,
            bg=COLOR_SCREEN,
            fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            relief="flat",
            wrap="word",
            padx=16,
            pady=16,
            font=("Cascadia Mono", 9),
        )
        self._doctor_text = text
        text.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        actions = tk.Frame(window, bg=COLOR_BG)
        actions.pack(fill="x", padx=16, pady=(0, 16))
        tk.Button(
            actions,
            text="REFRESH WINDOWS CHECKS",
            command=self._refresh_system_diagnostics,
            bg=COLOR_BLUE,
            fg=COLOR_INK,
            relief="flat",
            bd=0,
            padx=12,
            pady=8,
            font=(PIXEL_FONT, 8, "bold"),
        ).pack(side="left")
        tk.Button(
            actions,
            text="COPY DIAGNOSTIC REPORT",
            command=self.copy_diagnostic_report,
            bg=COLOR_ACCENT,
            fg=COLOR_INK,
            relief="flat",
            bd=0,
            padx=12,
            pady=8,
            font=(PIXEL_FONT, 8, "bold"),
        ).pack(side="right")

        def close_doctor() -> None:
            self._doctor_text = None
            self._doctor_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close_doctor)
        self._update_doctor_window()

    def copy_diagnostic_report(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self._diagnostic_report())
        self.root.update_idletasks()
        self._set_status(
            "REPORT COPIED",
            "Connection Doctor diagnostics are on the clipboard.",
            COLOR_BLUE,
        )

    def _refresh_system_diagnostics(self) -> None:
        if self._closing:
            return
        port = self._settings.port

        def worker() -> None:
            result = collect_windows_network_diagnostics(port)
            self._messages.put(("network-diagnostics", (port, result)))

        threading.Thread(
            target=worker,
            name="niwPSPtoPC Windows diagnostics",
            daemon=True,
        ).start()

    def _refresh_live_diagnostics(self) -> None:
        if self._closing:
            return
        if self._receiver is not None:
            self._doctor.update_metrics(self._receiver.metrics())
            self._refresh_doctor()
        self.root.after(1000, self._refresh_live_diagnostics)

    def open_settings(self) -> None:
        if (
            self._settings_window is not None
            and self._settings_window.winfo_exists()
        ):
            self._settings_window.lift()
            self._settings_window.focus_force()
            return
        window = tk.Toplevel(self.root)
        self._settings_window = window
        window.title("niwPSPtoPC Settings")
        window.geometry("520x330")
        window.resizable(False, False)
        window.configure(bg=COLOR_BG)
        settings = self._settings
        host_var = tk.StringVar(value=settings.host)
        port_var = tk.StringVar(value=str(settings.port))
        allowed_var = tk.StringVar(value=", ".join(settings.allowed_hosts))
        form = tk.Frame(window, bg=COLOR_BG)
        form.pack(fill="both", expand=True, padx=24, pady=20)

        def add_field(label: str, variable: tk.StringVar) -> None:
            tk.Label(
                form,
                text=label,
                bg=COLOR_BG,
                fg=COLOR_MUTED,
                font=(PIXEL_FONT, 8, "bold"),
            ).pack(anchor="w", pady=(8, 3))
            tk.Entry(
                form,
                textvariable=variable,
                bg=COLOR_SCREEN,
                fg=COLOR_TEXT,
                insertbackground=COLOR_TEXT,
                relief="flat",
                highlightbackground=COLOR_BORDER,
                highlightthickness=1,
                font=("Segoe UI", 10),
            ).pack(fill="x", ipady=5)

        add_field("LISTEN IPV4 ADDRESS", host_var)
        add_field("UDP PORT", port_var)
        add_field("PSP IPV4 ALLOWLIST (COMMA-SEPARATED, EMPTY = ANY)", allowed_var)
        tk.Label(
            form,
            text="Saving restarts only the UDP receiver and gamepad preflight.",
            bg=COLOR_BG,
            fg=COLOR_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(10, 4))
        tk.Button(
            form,
            text="[ SAVE AND RESTART RECEIVER ]",
            command=lambda: self.apply_settings(
                host_var.get(),
                port_var.get(),
                allowed_var.get(),
                window=window,
            ),
            bg=COLOR_ACCENT,
            fg=COLOR_INK,
            relief="flat",
            bd=0,
            pady=9,
            font=(PIXEL_FONT, 8, "bold"),
        ).pack(fill="x", pady=(8, 0))

        def close_settings() -> None:
            self._settings_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close_settings)

    def apply_settings(
        self,
        host_text: str,
        port_text: str,
        allowed_hosts_text: str,
        *,
        window: tk.Toplevel | None = None,
    ) -> bool:
        try:
            settings = validate_bind_settings(
                host_text,
                port_text,
                allowed_hosts_text,
            )
            save_settings(settings)
        except (OSError, ValueError) as exc:
            self._set_status("SETTINGS ERROR", str(exc), COLOR_DANGER)
            return False

        self._settings = settings
        if window is not None and window.winfo_exists():
            window.destroy()
            self._settings_window = None

        self._set_status(
            "RESTARTING RECEIVER",
            f"Applying UDP {settings.host}:{settings.port}.",
            COLOR_WARN,
        )
        if self._running and self._receiver is not None:
            self._restart_pending = True
            self._receiver.request_stop()
            if self._controller_service is not None:
                self._controller_service.stop()
        else:
            self.start_receiver()
        return True

    def retry_gamepad(self) -> None:
        service = self._controller_service
        if service is None:
            self._set_status(
                "GAMEPAD NOT READY",
                "Start the receiver before retrying the gamepad.",
                COLOR_WARN,
            )
            return
        self.gamepad_var.set("RETRYING")
        self._set_status(
            "RETRYING GAMEPAD",
            "Running virtual-controller preflight again.",
            COLOR_BLUE,
        )
        service.retry_backend()

    def start_receiver(self) -> None:
        if self._running or self._closing:
            return
        settings = self._settings
        # A settings restart is scheduled only after the old receiver's
        # messages, including its terminal "stopped" event, have been drained.
        # Reset diagnostics here so stale events cannot be attributed to the
        # new bind configuration.
        self._doctor = ConnectionDoctor()
        self._doctor_port = settings.port
        self._refresh_doctor()
        self._refresh_system_diagnostics()
        self._running = True
        self._controller_service = ControllerService(
            on_event=lambda event: self._messages.put(("controller", event))
        )
        controller_service = self._controller_service

        def apply_controller_state(snapshot: ReceiverSnapshot) -> None:
            if controller_service.handle_snapshot(snapshot):
                self._messages.put(("packet", snapshot))

        receiver = UdpReceiver(
            settings.host,
            settings.port,
            on_packet=apply_controller_state,
            on_listening=lambda address: self._messages.put(("listening", address)),
            on_stage=lambda event: self._messages.put(("stage", event)),
            pairing_ack_allowed=lambda: controller_service.gamepad_ready,
            allowed_hosts=set(settings.allowed_hosts) or None,
            pairing_token=self._active_token,
            require_pairing=True,
        )
        self._receiver = receiver
        controller_service.ensure_backend()

        def worker() -> None:
            try:
                receiver.run()
            except OSError as exc:
                self._messages.put(("error", exc))
            finally:
                controller_service.stop()
                self._messages.put(
                    ("stopped", (receiver, controller_service))
                )

        self._receiver_thread = threading.Thread(
            target=worker,
            name="niwPSPtoPC UDP receiver",
            daemon=True,
        )
        self._receiver_thread.start()

    def authorize(self) -> None:
        try:
            token = parse_pairing_token(self.code_var.get())
        except ValueError as exc:
            self._set_status("CHECK CODE", str(exc), COLOR_DANGER)
            self.code_entry.focus_set()
            return

        self._active_token = token
        self._doctor.reset_pairing()
        self._refresh_doctor()
        self.code_var.set(format_pairing_token(token))
        self._paired_address = None
        self.gamepad_var.set(
            "READY"
            if self._controller_service is not None
            and getattr(self._controller_service, "gamepad_ready", False)
            else "OFFLINE"
        )
        self.controller_view.neutralize()
        self.controller_view.set_link_state("SEARCHING PSP", "CODE ACCEPTED")
        if self._controller_service is not None:
            self._controller_service.disconnect("pairing-changed")
        if self._receiver is not None:
            self._receiver.set_pairing_token(token)
        self._set_status(
            "WAITING FOR PSP",
            "Code saved. The console will discover this PC automatically.",
            COLOR_BLUE,
        )

    def clear_pairing(self) -> None:
        self._active_token = None
        self._doctor.reset_pairing()
        self._refresh_doctor()
        self._paired_address = None
        self.code_var.set("")
        self.gamepad_var.set(
            "READY"
            if self._controller_service is not None
            and getattr(self._controller_service, "gamepad_ready", False)
            else "OFFLINE"
        )
        self.controller_view.neutralize()
        self.controller_view.set_link_state("PAIRING MODE", "ENTER CODE ON PC")
        if self._controller_service is not None:
            self._controller_service.disconnect("pairing-cleared")
        if self._receiver is not None:
            self._receiver.set_pairing_token(None)
        self._set_status(
            "ENTER PSP CODE",
            "The console creates a new code every time it starts.",
            COLOR_BLUE,
        )
        self.code_entry.focus_set()

    def _poll_messages(self) -> None:
        try:
            while True:
                kind, payload = self._messages.get_nowait()
                if kind == "listening":
                    address = payload
                    if isinstance(address, tuple):
                        self._doctor.set_bound_address(address)
                    self._set_status(
                        "ENTER PSP CODE",
                        "The receiver is ready.",
                        COLOR_BLUE,
                    )
                    self.code_entry.focus_set()
                elif kind == "stage":
                    self._apply_receiver_stage(payload)  # type: ignore[arg-type]
                elif kind == "packet":
                    self._apply_snapshot(payload)  # type: ignore[arg-type]
                elif kind == "controller":
                    self._apply_controller_event(payload)  # type: ignore[arg-type]
                elif kind == "network-diagnostics":
                    diagnostic_port, diagnostics = payload  # type: ignore[misc]
                    if diagnostic_port == self._settings.port:
                        self._doctor.update_network(diagnostics)
                        self._refresh_doctor()
                elif kind == "error":
                    error = payload
                    if getattr(error, "winerror", None) == 10048:
                        detail = "The port is already used by another app instance."
                    else:
                        detail = str(error)
                    self._set_status("RECEIVER ERROR", detail, COLOR_DANGER)
                    self.controller_view.set_link_state("RECEIVER ERROR", "CHECK PC")
                elif kind == "stopped":
                    stopped_receiver = (
                        payload[0]
                        if isinstance(payload, tuple) and len(payload) == 2
                        else self._receiver
                    )
                    if stopped_receiver is self._receiver:
                        self._running = False
                        self._receiver = None
                        self._controller_service = None
                        if self._restart_pending and not self._closing:
                            self._restart_pending = False
                            self.root.after(50, self.start_receiver)
        except queue.Empty:
            pass
        if not self._closing:
            self.root.after(50, self._poll_messages)

    def _apply_snapshot(self, snapshot: ReceiverSnapshot) -> None:
        self._paired_address = snapshot.address
        self.controller_view.set_packet(snapshot.packet)
        self.controller_view.set_input_rate(snapshot.packets_per_second)
        self.controller_view.set_link_state("LINK ACTIVE", "CONTROLLER READY")
        self._set_status(
            "PSP CONNECTED",
            "The controller is ready to play.",
            COLOR_ACCENT,
        )

    def _apply_controller_event(self, event: ControllerEvent) -> None:
        if event.event is ControllerEventType.GAMEPAD_READY:
            self._doctor.mark(DoctorStage.GAMEPAD_CREATED)
            self._refresh_doctor()
            self.gamepad_var.set("READY")
            if hasattr(self, "retry_gamepad_button"):
                self.retry_gamepad_button.configure(state="disabled")
            return
        if event.event is ControllerEventType.CONNECTED:
            self.gamepad_var.set("ACTIVE")
            return
        if event.event is ControllerEventType.NEUTRALIZED:
            self.gamepad_var.set("READY")
            self.controller_view.neutralize()
            if self._running:
                self.controller_view.set_link_state(
                    "INPUT PAUSED",
                    "CONTROLS RELEASED",
                )
                self._set_status(
                    "SIGNAL PAUSED",
                    "Input is neutral; the PSP session remains reserved briefly.",
                    COLOR_WARN,
                )
            return
        self.controller_view.neutralize()
        if event.event is ControllerEventType.ERROR:
            self.gamepad_var.set("OFFLINE")
            self._doctor.fail_gamepad(event.error or "ViGEmBus unavailable")
            self._refresh_doctor()
            if hasattr(self, "retry_gamepad_button"):
                self.retry_gamepad_button.configure(state="normal")
            failure_copy = {
                BackendFailureKind.MISSING_LIBRARY: (
                    "GAMEPAD LIBRARY MISSING",
                    "Reinstall the Windows application package, then retry.",
                    "LIBRARY MISSING",
                ),
                BackendFailureKind.MISSING_DRIVER: (
                    "GAMEPAD DRIVER MISSING",
                    "Install ViGEmBus, then use RETRY GAMEPAD.",
                    "INSTALL VIGEMBUS",
                ),
                BackendFailureKind.DRIVER_CONNECTION: (
                    "GAMEPAD DRIVER ERROR",
                    "The driver is present but unavailable. Check it, then retry.",
                    "DRIVER CONNECTION",
                ),
                BackendFailureKind.UPDATE_FAILED: (
                    "GAMEPAD UPDATE ERROR",
                    "The virtual pad connection failed during input. Retry it.",
                    "UPDATE FAILED",
                ),
            }
            title, detail, link_detail = failure_copy.get(
                event.failure,
                (
                    "GAMEPAD ERROR",
                    event.error or "Correct the backend error, then retry.",
                    "BACKEND ERROR",
                ),
            )
            self.controller_view.set_link_state("DRIVER ERROR", link_detail)
            self._set_status(
                title,
                detail,
                COLOR_DANGER,
            )
        elif event.reason == "timeout" and self._running:
            self.gamepad_var.set(
                "READY"
                if self._controller_service is not None
                and getattr(self._controller_service, "gamepad_ready", False)
                else "OFFLINE"
            )
            self.controller_view.set_link_state("SIGNAL LOST", "WAITING FOR PSP")
            self._set_status(
                "CONNECTION LOST",
                "All controls were released. Waiting for the PSP.",
                COLOR_WARN,
            )

    def _apply_receiver_stage(self, event: ReceiverEvent) -> None:
        mapping = {
            ReceiverStage.PORT_BOUND: DoctorStage.PORT_BOUND,
            ReceiverStage.DATAGRAM_RECEIVED: DoctorStage.DATAGRAM_RECEIVED,
            ReceiverStage.VALID_PACKET: DoctorStage.VALID_PACKET,
            ReceiverStage.CODE_MATCHED: DoctorStage.CODE_MATCHED,
            ReceiverStage.ACK_SENT: DoctorStage.ACK_SENT,
        }
        self._doctor.mark(mapping[event.stage])
        self._refresh_doctor()

    def close(self) -> None:
        self._closing = True
        self._restart_pending = False
        if self._receiver is not None:
            self._receiver.request_stop()
        if self._controller_service is not None:
            self._controller_service.stop()
        self.root.after(80, self.root.destroy)


def main() -> int:
    smoke_test = (
        "--smoke-test" in sys.argv[1:]
        or os.environ.get("NIWPSPTOPC_SMOKE_TEST") == "1"
    )
    with SingleInstance("Local\\niwPSPtoPC.GUI.v1") as instance:
        if not instance.acquired:
            instance.show_already_running_message()
            return 2
        root = tk.Tk()
        if smoke_test:
            root.withdraw()
        NiwPspToPcApp(root, auto_start=not smoke_test)
        if smoke_test:
            root.update_idletasks()
            root.destroy()
            return 0
        root.mainloop()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
