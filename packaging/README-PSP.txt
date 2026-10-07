niwPSPtoPC 1.2.0 for PSP
=========================

The Ultimate Wireless and Wired Gamepad for PSP and Windows.

Copy the complete niwPSPtoPC directory to:

ms0:/PSP/GAME/niwPSPtoPC/

On PSP Go internal storage, copy it to:

ef0:/PSP/GAME/niwPSPtoPC/

EBOOT.PBP and usbhostfs.prx are required. Keep them in the same directory.
config.ini is optional; safe defaults are used when it is missing.
PSP Street/E1000 has no Wi-Fi hardware. USB-only operation is expected, but
that model has not yet been physically verified for version 1.2.0.

USB needs only a compatible PSP data cable. Wi-Fi requires a working saved
profile and local connectivity to the PC. Recent ARK-4 and ARK-5 CFW releases
support compatible 2.4 GHz WPA2-PSK networks; legacy firmware may require an
older WPA-PSK access point. WPA3-only networks are unsupported. Client
isolation must be disabled.

Start the Windows application first or afterwards; either order works.
On the first screen, choose USB or WIFI with LEFT/RIGHT and confirm with CROSS.
WIFI is greyed out while the physical WLAN switch is off.

USB: select USB in the Windows application and connect the data cable. No
pairing code is required.
Wi-Fi: choose a saved profile, select Wi-Fi in the Windows application, then
enter the code shown on the PSP.

Hold L+R+START for 0.75 seconds while connected to return to the connection
selector. CIRCLE returns there from connection/setup screens. Removing the USB
cable also returns to the selector; it does not close the application.

The backlight turns off ten seconds after pairing to save power. Press SCREEN
or HOME to restore it. Connection loss and application exit also restore it.

If the access point disappears, leave the app running. The PSP reconnects with
increasing delays, recreates its UDP link and rediscovers the PC automatically.
CIRCLE cancels reconnecting and returns to the connection selector. HOME exits
the application.

The PC address is discovered automatically. config.ini normally does not need
to be edited. send_rate accepts 15 through 60 Hz.
