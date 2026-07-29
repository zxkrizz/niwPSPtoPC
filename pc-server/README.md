# niwPSPtoPC Windows application

The Windows application receives paired PSP input over UDP and exposes it as
an Xbox 360 controller. Its public GUI contains pairing state, a live
pixel-art input view and virtual-controller status. Detailed diagnostics stay
in separate command-line tools.

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

The receiver listens on `0.0.0.0:47999` by default. The PSP broadcasts only
while discovering the receiver; after the correct five-character code is
entered, the pairing ACK identifies the PC and the PSP switches to unicast.

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
OUT_OF_ORDER packets remain diagnostic events. After 1.5 seconds without a
fresh accepted state, the backend releases all controls and disconnects the
virtual device independently of the GUI.

## Test tools

```powershell
python -m unittest discover -s tests -v
python -m pc_server.simulator --token ABCDE
python -m pc_server.simulator --token ABCDE `
  --scenario sequence-errors --count 150
python -m pc_server.soak --minutes 30 --pairing-token ABCDE `
  --output hardware-soak.json
```
