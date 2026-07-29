param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DistRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot "dist"))
$ReleaseRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $DistRoot "release")
)
$StagingRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $DistRoot "release-staging")
)
$ExpectedPrefix = $DistRoot.TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar
) + [System.IO.Path]::DirectorySeparatorChar

foreach ($Path in @($ReleaseRoot, $StagingRoot)) {
    if (-not $Path.StartsWith(
        $ExpectedPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Release path is outside the dist directory: $Path"
    }
}

$WindowsExecutable = Join-Path $DistRoot "windows\niwPSPtoPC.exe"
$PspEboot = Join-Path $DistRoot "niwPSPtoPC\EBOOT.PBP"
$PspConfig = Join-Path $DistRoot "niwPSPtoPC\config.ini"
$License = Join-Path $ProjectRoot "LICENSE"
$Notices = Join-Path $ProjectRoot "THIRD_PARTY_NOTICES.txt"
$WindowsReadme = Join-Path $ProjectRoot "packaging\README-WINDOWS.txt"
$PspReadme = Join-Path $ProjectRoot "packaging\README-PSP.txt"

foreach ($RequiredFile in @(
    $WindowsExecutable,
    $PspEboot,
    $PspConfig,
    $License,
    $Notices,
    $WindowsReadme,
    $PspReadme
)) {
    if (-not (Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
        throw "Required release file is missing: $RequiredFile"
    }
}

if (Test-Path -LiteralPath $ReleaseRoot) {
    Remove-Item -LiteralPath $ReleaseRoot -Recurse -Force
}
if (Test-Path -LiteralPath $StagingRoot) {
    Remove-Item -LiteralPath $StagingRoot -Recurse -Force
}

$WindowsStage = Join-Path $StagingRoot "windows"
$PspStage = Join-Path $StagingRoot "psp\niwPSPtoPC"
New-Item -ItemType Directory -Path $WindowsStage, $PspStage -Force |
    Out-Null
New-Item -ItemType Directory -Path $ReleaseRoot -Force | Out-Null

Copy-Item -LiteralPath $WindowsExecutable -Destination $WindowsStage
Copy-Item -LiteralPath $WindowsReadme `
    -Destination (Join-Path $WindowsStage "README.txt")
Copy-Item -LiteralPath $License -Destination $WindowsStage
Copy-Item -LiteralPath $Notices -Destination $WindowsStage

Copy-Item -LiteralPath $PspEboot -Destination $PspStage
Copy-Item -LiteralPath $PspConfig -Destination $PspStage
Copy-Item -LiteralPath $PspReadme `
    -Destination (Join-Path $PspStage "README.txt")
Copy-Item -LiteralPath $License -Destination $PspStage

$WindowsArchive = Join-Path `
    $ReleaseRoot `
    "niwPSPtoPC-v$Version-Windows-x64.zip"
$PspArchive = Join-Path `
    $ReleaseRoot `
    "niwPSPtoPC-v$Version-PSP.zip"

Compress-Archive `
    -Path (Join-Path $WindowsStage "*") `
    -DestinationPath $WindowsArchive `
    -CompressionLevel Optimal
Compress-Archive `
    -Path (Join-Path (Split-Path -Parent $PspStage) "niwPSPtoPC") `
    -DestinationPath $PspArchive `
    -CompressionLevel Optimal

$ChecksumFiles = @($WindowsArchive, $PspArchive)
$ChecksumLines = foreach ($File in $ChecksumFiles) {
    $Hash = (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLower()
    "$Hash  $(Split-Path -Leaf $File)"
}
$ChecksumPath = Join-Path $ReleaseRoot "SHA256SUMS.txt"
Set-Content -LiteralPath $ChecksumPath -Value $ChecksumLines -Encoding ascii

Remove-Item -LiteralPath $StagingRoot -Recurse -Force

Write-Output "Release package ready: $ReleaseRoot"
Get-ChildItem -LiteralPath $ReleaseRoot |
    Select-Object Name, Length
