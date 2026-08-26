param(
    [string]$TargetTriple = "x86_64-pc-windows-msvc",
    [string]$Python = "",
    [switch]$Clean,
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$buildPython = Join-Path $root ".venv-desktop-build\Scripts\python.exe"
if (-not $Python) {
    $Python = if (Test-Path -LiteralPath $buildPython) { $buildPython } else { "python" }
}
$destinationDir = Join-Path $root "desktop\src-tauri\binaries"
$destination = Join-Path $destinationDir "videohub-sidecar-$TargetTriple.exe"
$source = Join-Path $root "dist\videohub-sidecar.exe"

Push-Location $root
try {
    if (-not $SkipFrontendBuild) {
        Push-Location (Join-Path $root "frontend")
        try {
            & npm.cmd install --cache (Join-Path $root ".npm-cache")
            if ($LASTEXITCODE -ne 0) { throw "Story editor npm install failed" }
            & npm.cmd run build
            if ($LASTEXITCODE -ne 0) { throw "Story editor frontend build failed" }
        }
        finally {
            Pop-Location
        }
    }
    $arguments = @("-m", "PyInstaller", "--noconfirm")
    if ($Clean) { $arguments += "--clean" }
    $arguments += "videohub-sidecar.spec"
    & $Python @arguments
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
    if (-not (Test-Path -LiteralPath $source)) { throw "Sidecar output not found: $source" }
    New-Item -ItemType Directory -Force -Path $destinationDir | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
    $hash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Output "sidecar=$destination"
    Write-Output "sha256=$hash"
}
finally {
    Pop-Location
}
