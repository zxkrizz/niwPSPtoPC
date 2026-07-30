niwPSPtoPC 1.2.0 for Windows
=============================

The Ultimate Wireless and Wired Gamepad for PSP and Windows.

USB cable mode uses the Microsoft-signed WinUSB driver included with Windows.
On a clean Windows 10/11 PC it is selected automatically from descriptors
reported by the PSP; do not install Zadig or an unsigned driver package.
If Windows needs the application interface registered, niwPSPtoPC requests
one UAC confirmation, restarts only the connected PSP device, and then retries
automatically. Later connections through that Windows device instance do not
require elevation; a different USB port can create a new instance and prompt
once again.

1. Install the final ViGEmBus 1.22.0 driver:
   https://github.com/nefarius/ViGEmBus/releases/tag/v1.22.0
2. For Wi-Fi, keep the PSP and PC on the same trusted local network. USB mode
   needs only a PSP data cable.
3. Start niwPSPtoPC.exe. Allow private-network access if Windows asks and you
   intend to use Wi-Fi.
4. Start niwPSPtoPC on the PSP and choose USB or WIFI.
5. Select the same large USB or Wi-Fi field at the top of this app.
6. USB connects automatically without a code. For Wi-Fi, enter the
   five-character code shown on the PSP.

The app listens for USB and Wi-Fi together. Switching transport on the PSP does
not require restarting the Windows app or recreating the virtual controller.
After a connection succeeds, the pairing form is replaced with connection
status and a Disconnect button. Connection Doctor reports input,
authorization and gamepad milestones plus Wi-Fi network/profile/firewall
state. Use Settings to change the UDP bind, port or PSP IP allowlist. Use Retry
after correcting a virtual-controller error; the first failure also gets one
automatic retry.

Guest Wi-Fi often enables client isolation; use a network that allows
PSP-to-PC traffic.

The PSP discovers this PC automatically. Do not expose UDP 47999 to the
Internet.

The executable is unsigned. Verify its SHA-256 value against SHA256SUMS.txt
from the same GitHub Release.
