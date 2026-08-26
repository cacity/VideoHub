param(
    [string]$TargetTriple = "x86_64-pc-windows-msvc",
    [string]$Python = "",
    [switch]$SkipPythonInstall,
    [switch]$SkipNpmInstall,
    [switch]$SkipSidecarBuild,
    [switch]$SkipMsiIceValidation
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$desktop = Join-Path $root "desktop"
$buildPython = Join-Path $root ".venv-desktop-build\Scripts\python.exe"
if (-not $Python) {
    $Python = if (Test-Path -LiteralPath $buildPython) { $buildPython } else { "python" }
}

function Invoke-MsiIceValidationFallback {
    param([string]$DesktopPath)

    $wixRoot = Join-Path $env:LOCALAPPDATA "tauri\WixTools314"
    $light = Join-Path $wixRoot "light.exe"
    $wixDir = Join-Path $DesktopPath "src-tauri\target\release\wix\x64"
    $wixObject = Join-Path $wixDir "main.wixobj"
    $localization = Join-Path $wixDir "locale.wxl"
    $output = Join-Path $wixDir "output.msi"
    $bundleDir = Join-Path $DesktopPath "src-tauri\target\release\bundle\msi"
    $bundle = Join-Path $bundleDir "VideoHub_0.1.0_x64_en-US.msi"

    foreach ($required in @($light, $wixObject, $localization)) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Cannot create the MSI ICE fallback because '$required' does not exist."
        }
    }
    New-Item -ItemType Directory -Force -Path $bundleDir | Out-Null

    # WiX ICE validation invokes Windows Installer custom actions. This fallback
    # is only for hosts where that system validation layer is unavailable; it
    # still links the exact candle output used by Tauri into an MSI package.
    & $light -sval `
        -ext (Join-Path $wixRoot "WixUtilExtension.dll") `
        -ext (Join-Path $wixRoot "WixUIExtension.dll") `
        -o $output `
        -cultures:en-us `
        -loc $localization `
        $wixObject
    if ($LASTEXITCODE -ne 0) {
        throw "WiX light.exe fallback failed"
    }
    Copy-Item -LiteralPath $output -Destination $bundle -Force
    Write-Warning "MSI was created with WiX ICE validation disabled for this build host. Verify installation on a clean Windows machine before release."
}

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    throw "Rust/Cargo is required. Install rustup and the stable MSVC toolchain first."
}

Push-Location $root
try {
    if (-not $SkipPythonInstall) {
        & $Python -m pip install -r "requirements-desktop.txt"
        if ($LASTEXITCODE -ne 0) { throw "Python desktop dependencies failed" }
    }
    if (-not $SkipSidecarBuild) {
        & (Join-Path $PSScriptRoot "build_desktop_sidecar.ps1") `
            -TargetTriple $TargetTriple `
            -Python $Python `
            -SkipFrontendBuild
        if (-not $?) { throw "Sidecar build failed" }
    }
    & (Join-Path $PSScriptRoot "stage_desktop_tools.ps1")
    if (-not $?) { throw "Desktop tool staging failed" }

    Push-Location $desktop
    try {
        if (-not $SkipNpmInstall) {
            & npm.cmd install --cache (Join-Path $root ".npm-cache")
            if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
        }
        # Build NSIS first so an MSI-only WiX validation failure never suppresses
        # the otherwise valid installer artifact.
        & npm.cmd run tauri build -- --bundles nsis
        if ($LASTEXITCODE -ne 0) {
            throw "Tauri NSIS build failed"
        }
        & npm.cmd run tauri build -- --bundles msi
        if ($LASTEXITCODE -ne 0) {
            if (-not $SkipMsiIceValidation) {
                throw "Tauri MSI build failed"
            }
            Invoke-MsiIceValidationFallback -DesktopPath $desktop
        }
    }
    finally {
        Pop-Location
    }

    $bundleRoot = Join-Path $desktop "src-tauri\target\release\bundle"
    Get-ChildItem -LiteralPath $bundleRoot -Recurse -File |
        Where-Object { $_.Extension -in ".exe", ".msi" } |
        ForEach-Object {
            $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            Write-Output "artifact=$($_.FullName)"
            Write-Output "sha256=$hash"
        }
}
finally {
    Pop-Location
}
