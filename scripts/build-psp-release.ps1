$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PspdevImage = (
    Get-Content `
        -LiteralPath (Join-Path $PSScriptRoot "pspdev-image.txt") `
        -Raw
).Trim()
$Docker = Get-Command docker -ErrorAction SilentlyContinue
if ($Docker) {
    & $Docker.Source run --rm `
        --volume "${ProjectRoot}:/workspace" `
        --workdir /workspace `
        $PspdevImage `
        bash -lc "./scripts/test-c-protocol.sh && ./scripts/build-psp.sh"
    if ($LASTEXITCODE -ne 0) {
        throw "Pinned PSPDEV container build failed."
    }
} else {
    $Wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if (-not $Wsl) {
        throw "Docker or WSL with the v20260701 PSPDEV toolchain is required."
    }
    & $Wsl.Source --cd $ProjectRoot bash ./scripts/build-psp-wsl.sh
    if ($LASTEXITCODE -ne 0) {
        throw (
            "WSL PSP build failed or its toolchain is not the pinned " +
            "v20260701 revision."
        )
    }
}

$Eboot = Join-Path $ProjectRoot "psp-client\EBOOT.PBP"
if (-not (Test-Path -LiteralPath $Eboot -PathType Leaf)) {
    throw "PSP build completed without EBOOT.PBP."
}
Write-Output "PSP build ready: $Eboot"
