param(
    [string]$Python
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($Python)) {
    $PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PythonLauncher) {
        foreach ($CandidateVersion in @("3.13", "3.12", "3.14")) {
            $Candidate = & $PythonLauncher.Source `
                "-$CandidateVersion" `
                -c "import sys; print(sys.executable)" `
                2>$null
            if ($LASTEXITCODE -eq 0 -and $Candidate) {
                $Python = $Candidate.Trim()
                break
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($Python)) {
        $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $PythonCommand) {
            throw "Python 3.12 or newer was not found."
        }
        $Python = $PythonCommand.Source
    }
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BuildEnvironment = Join-Path $ProjectRoot ".build-venv"
$BuilderPython = Join-Path $BuildEnvironment "Scripts\python.exe"
$EntryPoint = Join-Path $ProjectRoot "pc-server\niwpsptopc_gui.py"
$Requirements = Join-Path $ProjectRoot "pc-server\requirements-build.txt"
$VersionInfo = Join-Path $ProjectRoot "pc-server\windows-version-info.txt"
$OutputDirectory = Join-Path $ProjectRoot "dist\windows"
$WorkDirectory = Join-Path $ProjectRoot "build\pyinstaller"
$Icon = Join-Path $ProjectRoot "build\niwPSPtoPC.ico"
$Executable = Join-Path $OutputDirectory "niwPSPtoPC.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python executable not found: $Python"
}

& $Python -c @"
import sys
if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12 or newer is required.")
"@
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.12 or newer is required."
}

if (-not (Test-Path -LiteralPath $BuilderPython)) {
    & $Python -m venv $BuildEnvironment
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the Windows build environment."
    }
}

# Bundle the userspace client without launching a driver installer as a build
# side effect. The signed ViGEmBus driver is installed on the target PC.
$env:VGAMEPAD_SKIP_VIGEMBUS_INSTALL = "true"
& $BuilderPython -m pip install `
    --disable-pip-version-check `
    --requirement $Requirements
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install Windows build dependencies."
}

$VGamepadRoot = & $BuilderPython -c @"
import importlib.util
from pathlib import Path
spec = importlib.util.find_spec("vgamepad")
if spec is None or spec.origin is None:
    raise SystemExit("vgamepad package not found")
print(Path(spec.origin).parent)
"@
if ($LASTEXITCODE -ne 0) {
    throw "Could not locate the vgamepad package."
}
$VigemClient = Join-Path `
    $VGamepadRoot.Trim() `
    "win\vigem\client\x64\ViGEmClient.dll"
if (-not (Test-Path -LiteralPath $VigemClient)) {
    throw "ViGEmClient.dll was not found: $VigemClient"
}

& $BuilderPython (Join-Path $ProjectRoot "scripts\generate-windows-icon.py") $Icon
if ($LASTEXITCODE -ne 0) {
    throw "Failed to generate the Windows application icon."
}

$RunningExecutable = Get-Process -Name "niwPSPtoPC" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq $Executable }
if ($RunningExecutable) {
    throw "Close the running niwPSPtoPC application before rebuilding it."
}

& $BuilderPython -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name niwPSPtoPC `
    --icon $Icon `
    --version-file $VersionInfo `
    --distpath $OutputDirectory `
    --workpath $WorkDirectory `
    --specpath $WorkDirectory `
    --paths (Join-Path $ProjectRoot "pc-server") `
    --hidden-import vgamepad `
    --collect-submodules vgamepad.win `
    --exclude-module vgamepad.lin `
    --add-binary "$VigemClient;vgamepad/win/vigem/client/x64" `
    $EntryPoint
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed to build niwPSPtoPC.exe."
}

if (-not (Test-Path -LiteralPath $Executable)) {
    throw "Build completed without the expected executable: $Executable"
}

Write-Output "Windows application ready: $Executable"
