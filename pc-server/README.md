# niwPSPtoPC Windows application

The Ultimate Wireless and Wired Gamepad Windows application receives PSP input
over USB or Wi-Fi and exposes it as one Xbox 360 controller. Its GUI contains
large transport selectors, transport-specific setup, a live pixel-art input
view, editable bind/port/allowlist settings, recoverable gamepad preflight and
Connection Doctor with native Windows network checks and live UDP metrics.

## Requirements

- Python 3.12 or newer when running from source;
- Windows 10 or 11 for the virtual gamepad;
- [ViGEmBus 1.22.0](https://github.com/nefarius/ViGEmBus/releases/tag/v1.22.0).

Install the Python package from source with:

```powershell
python -m pip install -e ".[windows]"
```

## GUI

```powershell
python -m pc_server.gui
```

The USB receiver and Wi-Fi receiver run together. USB uses the physical cable
as authorization and requires no code. The Wi-Fi receiver listens on
`0.0.0.0:47999` by default. The PSP broadcasts only while discovering the
receiver; after the correct five-character code is entered, the pairing ACK
identifies the PC and the PSP switches to unicast.

Windows 10/11 uses its Microsoft-signed inbox WinUSB driver for the cable
transport. Do not install Zadig. See [`../docs/usb.md`](../docs/usb.md) for
driver setup and troubleshooting.

Build the standalone executable with:

```powershell
..\scripts\build-windows.ps1
```

The result is `dist/windows/niwPSPtoPC.exe`.

## CLI

Diagnostic receiver:

```powershell
python -m pc_server --host 0.0.0.0 --port 47999
```

Virtual gamepad with mandatory pairing:

```powershell
python -m pc_server --virtual-gamepad --pairing-token ABCDE
```

Only FIRST, IN_ORDER and GAP states update the controller. DUPLICATE and
OUT_OF_ORDER packets remain diagnostic events. After 0.5 seconds without a
fresh accepted state, the backend releases all controls. After 1.75 seconds it
releases the PSP session while keeping the virtual XInput device connected
independently of the GUI.

## Test tools

```powershell
python -m unittest discover -s tests -v
python -m pc_server.simulator --token ABCDE
python -m pc_server.simulator --token ABCDE `
  --scenario sequence-errors --count 150
python -m pc_server.soak --minutes 30 --pairing-token ABCDE `
  --output hardware-soak.json
```
