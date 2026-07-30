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

$VersionSource = Join-Path $ProjectRoot "pc-server\pc_server\_version.py"
$VersionMatch = Select-String `
    -LiteralPath $VersionSource `
    -Pattern '^__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"$'
if (-not $VersionMatch) {
    throw "Could not read the source product version."
}
$ExpectedVersion = $VersionMatch.Matches[0].Groups[1].Value
$ProductVersion = (Get-Item -LiteralPath $Executable).VersionInfo.ProductVersion
if ($ProductVersion -ne $ExpectedVersion) {
    throw (
        "Windows product version $ProductVersion does not match " +
        "$ExpectedVersion."
    )
}

$MtCommand = Get-Command mt.exe -ErrorAction SilentlyContinue
if (-not $MtCommand) {
    $WindowsKits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (Test-Path -LiteralPath $WindowsKits) {
        $MtCommand = Get-ChildItem `
            -LiteralPath $WindowsKits `
            -Filter mt.exe `
            -Recurse `
            -File |
            Where-Object { $_.DirectoryName -match '\\x64$' } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
    }
}
if (-not $MtCommand) {
    throw "Windows SDK mt.exe is required to verify the embedded manifest."
}
$ExtractedManifest = Join-Path `
    $ProjectRoot `
    "build\verified-niwPSPtoPC.exe.manifest"
New-Item -ItemType Directory -Path (Split-Path -Parent $ExtractedManifest) -Force |
    Out-Null
& $MtCommand.FullName `
    -nologo `
    "-inputresource:$Executable;#1" `
    "-out:$ExtractedManifest"
if ($LASTEXITCODE -ne 0) {
    throw "Could not extract the embedded Windows application manifest."
}
$ManifestText = Get-Content -LiteralPath $ExtractedManifest -Raw
if ($ManifestText -notmatch '(?i)PerMonitorV2') {
    throw "The executable manifest does not declare PerMonitorV2 DPI awareness."
}
if ($ManifestText -notmatch '(?i)requestedExecutionLevel.+asInvoker') {
    throw "The executable manifest does not declare asInvoker execution."
}

Write-Output "Windows package verification passed."
