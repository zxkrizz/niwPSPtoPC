niwPSPtoPC 1.0.1 for Windows
=============================

1. Install the final ViGEmBus 1.22.0 driver:
   https://github.com/nefarius/ViGEmBus/releases/tag/v1.22.0
2. Keep the PSP and PC on the same trusted local network.
3. Start niwPSPtoPC.exe and allow private-network access if Windows asks.
4. Start niwPSPtoPC on the PSP and enter its five-character code.

Connection Doctor reports each network, pairing and ViGEmBus milestone. Guest
Wi-Fi often enables client isolation; use a network that allows PSP-to-PC
traffic.

The PSP discovers this PC automatically. Do not expose UDP 47999 to the
Internet.

The executable is unsigned. Verify its SHA-256 value against SHA256SUMS.txt
from the same GitHub Release.
