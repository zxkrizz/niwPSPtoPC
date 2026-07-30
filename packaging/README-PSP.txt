niwPSPtoPC 1.1.0 for PSP
=========================

Copy the complete niwPSPtoPC directory to:

ms0:/PSP/GAME/niwPSPtoPC/

On PSP Go internal storage, copy it to:

ef0:/PSP/GAME/niwPSPtoPC/

EBOOT.PBP is required. config.ini is optional; safe defaults are used when it
is missing. PSP Street/E1000 is unsupported because it has no Wi-Fi.

The app only requires a working saved Wi-Fi profile and local connectivity to
the PC. Recent ARK-4 and ARK-5 CFW releases support compatible 2.4 GHz WPA2-PSK
networks; legacy firmware may require an older WPA-PSK access point. WPA3-only
networks are unsupported. Client isolation must be disabled.

Start the Windows application first or afterwards; either order works.
Choose a saved Wi-Fi profile with LEFT/RIGHT, confirm with CROSS, then enter
the code shown on the PSP in the Windows application.

The backlight turns off ten seconds after pairing to save power. Press SCREEN
or HOME to restore it. Connection loss and application exit also restore it.

If the access point disappears, leave the app running. The PSP reconnects with
increasing delays, recreates its UDP link and rediscovers the PC automatically.
HOME cancels reconnecting and returns to the PSP menu.

The PC address is discovered automatically. config.ini normally does not need
to be edited. send_rate accepts 15 through 60 Hz.
