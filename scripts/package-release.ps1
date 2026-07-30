param(
    [string]$Version,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($SkipBuild -and $env:GITHUB_ACTIONS -ne "true") {
    throw (
        "-SkipBuild is reserved for the tag workflow after its build jobs; " +
        "local releases must rebuild."
    )
}

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VersionSource = Join-Path $ProjectRoot "pc-server\pc_server\_version.py"
$VersionMatch = Select-String `
    -LiteralPath $VersionSource `
    -Pattern '^__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"$'
if (-not $VersionMatch) {
    throw "Could not read the product version from $VersionSource"
}
$ExpectedVersion = $VersionMatch.Matches[0].Groups[1].Value
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = $ExpectedVersion
}
if ($Version -ne $ExpectedVersion) {
    throw (
        "Release version $Version does not match the source version " +
        "$ExpectedVersion."
    )
}

$Changelog = Get-Content `
    -LiteralPath (Join-Path $ProjectRoot "CHANGELOG.md") `
    -Raw
if ($Changelog -notmatch "(?m)^## $([regex]::Escape($Version))\b") {
    throw "CHANGELOG.md has no section for version $Version."
}
foreach ($Readme in @(
    "packaging\README-WINDOWS.txt",
    "packaging\README-PSP.txt"
)) {
    $ReadmePath = Join-Path $ProjectRoot $Readme
    if ((Get-Content -LiteralPath $ReadmePath -Raw) -notmatch
        "\b$([regex]::Escape($Version))\b") {
        throw "$Readme does not mention version $Version."
    }
}

if (-not $SkipBuild) {
    $PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PythonLauncher) {
        $PythonArgs = @("-3.13")
        & $PythonLauncher.Source @PythonArgs -c "import sys; print(sys.version)"
        if ($LASTEXITCODE -ne 0) {
            $PythonArgs = @("-3.12")
        }
        $PythonCommand = $PythonLauncher.Source
    } else {
        $Python = Get-Command python -ErrorAction SilentlyContinue
        if (-not $Python) {
            throw "Python 3.12 or newer is required to build a release."
        }
        $PythonCommand = $Python.Source
        $PythonArgs = @()
    }

    Push-Location (Join-Path $ProjectRoot "pc-server")
    try {
        & $PythonCommand @PythonArgs -m compileall -q pc_server
        if ($LASTEXITCODE -ne 0) {
            throw "Python compile check failed."
        }
        & $PythonCommand @PythonArgs -m unittest discover -s tests -v
        if ($LASTEXITCODE -ne 0) {
            throw "Python unit tests failed."
        }
    } finally {
        Pop-Location
    }

    $BuildWindowsArgs = @{}
    if ($PythonLauncher) {
        $ResolvedPython = & $PythonCommand @PythonArgs -c `
            "import sys; print(sys.executable)"
        if ($LASTEXITCODE -ne 0) {
            throw "Could not resolve the selected Python interpreter."
        }
        $BuildWindowsArgs.Python = $ResolvedPython.Trim()
    } else {
        $BuildWindowsArgs.Python = $PythonCommand
    }
    & (Join-Path $PSScriptRoot "build-windows.ps1") @BuildWindowsArgs
    & (Join-Path $PSScriptRoot "build-psp-release.ps1")
}

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
$PspEboot = Join-Path $ProjectRoot "psp-client\EBOOT.PBP"
$PspConfig = Join-Path $ProjectRoot "psp-client\config.ini"
$License = Join-Path $ProjectRoot "LICENSE"
$Notices = Join-Path $ProjectRoot "THIRD_PARTY_NOTICES.txt"
$WindowsReadme = Join-Path $ProjectRoot "packaging\README-WINDOWS.txt"
$PspReadme = Join-Path $ProjectRoot "packaging\README-PSP.txt"
$ReleaseNotes = Join-Path $ProjectRoot "docs\releases\$Version.md"

foreach ($RequiredFile in @(
    $WindowsExecutable,
    $PspEboot,
    $PspConfig,
    $License,
    $Notices,
    $WindowsReadme,
    $PspReadme,
    $ReleaseNotes
)) {
    if (-not (Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
        throw "Required release file is missing: $RequiredFile"
    }
}

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot "verify-windows-package.ps1")
} else {
    $ProductVersion = (
        Get-Item -LiteralPath $WindowsExecutable
    ).VersionInfo.ProductVersion
    if ($ProductVersion -ne $ExpectedVersion) {
        throw (
            "Windows product version $ProductVersion does not match " +
            "$ExpectedVersion."
        )
    }
}

$SmokeProcess = Start-Process `
    -FilePath $WindowsExecutable `
    -ArgumentList "--smoke-test" `
    -WindowStyle Hidden `
    -PassThru `
    -Wait
if ($SmokeProcess.ExitCode -ne 0) {
    throw "GUI smoke test failed with exit code $($SmokeProcess.ExitCode)."
}

if (-not $SkipBuild) {
    $WindowsSources = Get-ChildItem `
        -LiteralPath (Join-Path $ProjectRoot "pc-server") `
        -Recurse `
        -File |
        Where-Object {
            $_.Extension -in @(".py", ".toml", ".txt")
        }
    if ($WindowsSources |
        Where-Object { $_.LastWriteTimeUtc -gt
            (Get-Item -LiteralPath $WindowsExecutable).LastWriteTimeUtc }) {
        throw "Windows executable is stale relative to its sources."
    }
    $PspSources = @(
        Get-ChildItem `
            -LiteralPath (Join-Path $ProjectRoot "psp-client\src") `
            -Recurse `
            -File
        Get-ChildItem `
            -LiteralPath (Join-Path $ProjectRoot "psp-client\include") `
            -Recurse `
            -File
        Get-ChildItem `
            -LiteralPath (Join-Path $ProjectRoot "psp-client\assets") `
            -Recurse `
            -File
        Get-Item -LiteralPath (Join-Path $ProjectRoot "psp-client\Makefile")
    )
    if ($PspSources |
        Where-Object { $_.LastWriteTimeUtc -gt
            (Get-Item -LiteralPath $PspEboot).LastWriteTimeUtc }) {
        throw "PSP EBOOT.PBP is stale relative to its sources."
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
Copy-Item -LiteralPath $ReleaseNotes `
    -Destination (Join-Path $WindowsStage "RELEASE-NOTES.md")

Copy-Item -LiteralPath $PspEboot -Destination $PspStage
Copy-Item -LiteralPath $PspConfig -Destination $PspStage
Copy-Item -LiteralPath $PspReadme `
    -Destination (Join-Path $PspStage "README.txt")
Copy-Item -LiteralPath $License -Destination $PspStage
Copy-Item -LiteralPath $ReleaseNotes `
    -Destination (Join-Path $PspStage "RELEASE-NOTES.md")

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

Add-Type -AssemblyName System.IO.Compression.FileSystem
foreach ($Archive in @($WindowsArchive, $PspArchive)) {
    $Zip = [System.IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        if ($Zip.Entries.Count -eq 0) {
            throw "Release archive is empty: $Archive"
        }
        foreach ($Entry in $Zip.Entries) {
            if ($Entry.FullName -match '(^|/)\.\.(/|$)' -or
                $Entry.FullName.StartsWith("/")) {
                throw "Unsafe path in release archive: $($Entry.FullName)"
            }
            if (-not $Entry.FullName.EndsWith("/") -and $Entry.Length -eq 0) {
                throw "Empty release file in archive: $($Entry.FullName)"
            }
        }
    } finally {
        $Zip.Dispose()
    }
}

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
