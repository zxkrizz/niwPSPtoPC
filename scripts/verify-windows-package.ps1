$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Executable = Join-Path $ProjectRoot "dist\windows\niwPSPtoPC.exe"
$ArchiveViewer = Join-Path `
    $ProjectRoot `
    ".build-venv\Scripts\pyi-archive_viewer.exe"

if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
    throw "Windows executable not found: $Executable"
}
if (-not (Test-Path -LiteralPath $ArchiveViewer -PathType Leaf)) {
    throw "PyInstaller archive viewer not found: $ArchiveViewer"
}

$ArchiveListing = (& $ArchiveViewer -l $Executable) -join "`n"
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect the Windows executable."
}
if ($ArchiveListing -match '(?i)\.msi') {
    throw "The Windows executable unexpectedly contains an MSI installer."
}
if ($ArchiveListing -match '(?i)vigem\\\\client\\\\x86') {
    throw "The Windows executable unexpectedly contains the x86 ViGEm client."
}
if (
    $ArchiveListing -notmatch
        '(?i)vgamepad\\\\win\\\\vigem\\\\client\\\\x64\\\\ViGEmClient\.dll'
) {
    throw "The Windows executable does not contain the x64 ViGEm client."
}

$Version = (Get-Item -LiteralPath $Executable).VersionInfo.ProductVersion
if ($Version -ne "1.0.0") {
    throw "Unexpected Windows product version: $Version"
}

Write-Output "Windows package verification passed."
