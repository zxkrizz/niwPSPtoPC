# niwPSPtoPC

niwPSPtoPC turns a Sony PSP into a wireless Xbox 360 controller for Windows.
The PSP homebrew client reads the console's controls, discovers the PC
automatically on the local network, and sends input over Wi-Fi.

The project has been tested on a physical PSP-2004 and across multiple Windows
games.

Current release: **1.1.0**. See the
[complete 1.1.0 release notes](docs/releases/1.1.0.md) and
[changelog](CHANGELOG.md).

![niwPSPtoPC PSP branding](psp-client/assets/PIC1.PNG)

## Features

- automatic PC discovery — no IP address configuration;
- five-character pairing code generated on every PSP launch;
- exclusive control for the first paired PSP;
- virtual Xbox 360 controller through ViGEmBus;
- live pixel-art input view on Windows;
- graphical PSP interface and custom XMB icon/background;
- automatic PSP Wi-Fi reconnect and PC rediscovery after an AP outage;
- automatic PSP backlight shutoff after a stable controller connection;
- stale, duplicate and out-of-order packets never roll input back;
- automatic neutral input after 0.5 seconds of silence without unplugging the
  virtual controller;
- automatic PSP session release after 1.75 seconds without fresh input;
- Connection Doctor 2.0 with Windows interfaces, profile/firewall checks,
  live UDP health and a copyable report;
- editable UDP bind, port and PSP IP allowlist settings;
- recoverable virtual-gamepad preflight without restarting the receiver;
- PSP readiness confirmation only after the virtual gamepad is available;
- no jitter buffer, keeping controller input as fresh as possible.

The physical PSP provides one analog stick, a D-pad, four face buttons, L/R,
Start and Select. A second analog stick and analog triggers cannot be emulated
because the console does not have those inputs.

## Requirements

### PSP

- a PSP-1000, PSP-2000, PSP-3000 or PSP Go with CFW and homebrew support;
- one working saved infrastructure Wi-Fi profile;
- a 2.4 GHz network compatible with the PSP;
- PSP and PC connected to the same local network.

PSP Street/E1000 is not supported because that model has no Wi-Fi hardware.

### PSP network compatibility

niwPSPtoPC uses the PSP system network APIs and does not depend on the Wi-Fi
encryption method itself. Once the PSP connects successfully, receives an IPv4
address and can reach the PC on the same local network, the program works
normally.

Standard firmware and older CFW configurations generally require a legacy
WPA-PSK-compatible 2.4 GHz network. Recent
[ARK-4](https://github.com/PSP-Archive/ARK-4) and ARK-5 CFW releases include
WPA2 support, so niwPSPtoPC can also be used on a compatible 2.4 GHz WPA2-PSK
network. Configure and test the Wi-Fi connection in the PSP network settings
before starting the program. WPA3-only networks remain unsupported by the PSP.

> [!WARNING]
> If your firmware requires legacy WPA-PSK, use a dedicated access point or
> isolated SSID with no access to sensitive devices or data. Make sure
> PSP-to-PC peer traffic is allowed: many guest networks enable client
> isolation and therefore cannot carry niwPSPtoPC traffic. Do not weaken the
> security of your primary home network solely to use this software.

### Windows

- Windows 10 or 11, x64;
- [ViGEmBus](https://github.com/nefarius/ViGEmBus/releases/tag/v1.22.0)
  installed;
- inbound UDP port 47999 allowed on private networks.

ViGEmBus was retired by its maintainers in 2023 and is no longer developed.
niwPSPtoPC uses its final signed Windows 10/11 release because it remains the
backend required by `vgamepad`.

## Installation

1. Download both release archives from the latest GitHub Release.
2. Install ViGEmBus on the Windows PC.
3. Extract the Windows archive and start `niwPSPtoPC.exe`.
4. Extract the PSP archive and copy the complete `niwPSPtoPC` directory to
   Memory Stick storage:

   ```text
   ms0:/PSP/GAME/niwPSPtoPC/
   ```

   On a PSP Go using internal storage, use
   `ef0:/PSP/GAME/niwPSPtoPC/` instead.

5. Start **niwPSPtoPC** from the PSP Game menu.
6. Select a saved Wi-Fi profile with LEFT/RIGHT and confirm with CROSS.
7. Enter the five-character code shown on the PSP into the Windows app.
8. When both screens show a connected controller, start the game.

The PSP discovers the PC automatically. `config.ini` is loaded next to the
EBOOT on either `ms0:` or `ef0:`. If it is missing, safe defaults are used.
The optional send rate is limited to 15–60 Hz and is shown accurately in both
interfaces.

Use **Use another code** in the Windows app to release the current session.
The PSP backlight turns off ten seconds after pairing to reduce battery use.
Press SCREEN or HOME to restore it. It is also restored automatically when the
connection is lost or the application closes. Press HOME to close the PSP
client.

## Windows firewall

Connection Doctor shows `port bound`, `datagram received`, `valid packet`,
`code matched`, `ACK sent`, and `gamepad created`. It also queries active IPv4
interfaces, network profiles and the matching Windows firewall rule. If it
stops at `port bound`, check the Windows Private network profile, firewall,
matching UDP port, client isolation and whether broadcast traffic can reach
the PC interface.

Windows normally asks for private-network access on first launch. If it does
not, run this command in an administrator PowerShell:

```powershell
New-NetFirewallRule -DisplayName "niwPSPtoPC UDP" `
  -Direction Inbound -Action Allow -Protocol UDP -LocalPort 47999 `
  -Profile Private
```

Do not forward this port on a router and do not expose it to the Internet.

## Building from source

### PSP

Install [PSPDEV/PSPSDK](https://pspdev.github.io/installation.html), then:

```bash
export PSPDEV=/actual/path/to/pspdev
export PATH="$PSPDEV/bin:$PATH"
./scripts/build-psp.sh
./scripts/package-psp.sh
```

The Memory Stick package is written to `dist/niwPSPtoPC/`.

The release uses non-blocking controller peeks in the sender. For physical
latency/short-press A/B measurements, build the comparison variant with
`make -C psp-client SENDER_INPUT_MODE=read`; the default is
`SENDER_INPUT_MODE=peek`.

The native XMB assets can be reproduced without third-party Python packages:

```bash
python scripts/generate-psp-assets.py
```

### Windows

Install Python 3.12 or newer and run:

```powershell
.\scripts\build-windows.ps1
```

The standalone executable is written to
`dist/windows/niwPSPtoPC.exe`. Python is not required on the target PC.

To run the GUI directly from source:

```powershell
cd pc-server
python -m pip install -e ".[windows]"
python -m pc_server.gui
```

### Release archives

The release command runs tests, rebuilds both applications with the pinned
PSPDEV revision (Docker image or matching WSL toolchain), smoke-tests the EXE,
validates versions/freshness and verifies the resulting archives:

```powershell
.\scripts\package-release.ps1
```

This creates the two public ZIP archives and `SHA256SUMS.txt` under
`dist/release/`. Tagged `vX.Y.Z` builds are independently rebuilt and
published by the Release workflow using the matching document from
`docs/releases/`; branch CI ignores tags.

## Diagnostics and tests

The GUI includes Connection Doctor 2.0 for network, pairing, packet-health and
driver failures. The command-line tools remain available for extended runs:

```powershell
cd pc-server
python -m pc_server --host 0.0.0.0 --port 47999
python -m pc_server.simulator --token ABCDE
python -m pc_server.soak --minutes 30 --pairing-token ABCDE `
  --output hardware-soak.json
```

Run the complete automated suite with:

```bash
./scripts/build-pc.sh
```

The suite covers the shared C/Python golden packet, pairing ACK, real UDP
loopback, client selection, duplicate and out-of-order filtering, controller
timeout, Xbox 360 mapping, GUI state and PSP XMB assets.

The wire format is documented in
[docs/input-protocol.md](docs/input-protocol.md).

## Security

The pairing code is designed for a trusted home LAN. Input packets are not
encrypted, and the token is visible to another device capable of capturing
traffic on that LAN. The protocol must not be exposed directly to the
Internet.

When using legacy WPA-PSK, run the PSP on a dedicated access point or isolated
SSID, allow peer-to-peer traffic between the PSP and PC, and do not place
trusted or sensitive devices on that network. WPA2 support provided by recent
ARK-4 and ARK-5 CFW releases avoids the need to enable legacy WPA solely for
niwPSPtoPC. Regardless of Wi-Fi encryption, use the application only on a
trusted local network.

See [SECURITY.md](SECURITY.md) for reporting security issues.

## License and trademarks

The project is distributed under the [MIT License](LICENSE). Third-party
components and notices are listed in
[THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt).

niwPSPtoPC is an independent homebrew project and is not affiliated with or
endorsed by Sony Interactive Entertainment, PlayStation, Microsoft or the
ViGEm project. PSP, PlayStation and Xbox are trademarks of their respective
owners.
