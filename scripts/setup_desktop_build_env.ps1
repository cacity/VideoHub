param(
    [string]$BootstrapPython = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$environment = Join-Path $root ".venv-desktop-build"
$python = Join-Path $environment "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    & $BootstrapPython -m venv $environment
    if ($LASTEXITCODE -ne 0) { throw "Unable to create desktop build environment" }
}

& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Unable to upgrade pip" }
& $python -m pip install -r (Join-Path $root "requirements-desktop.txt")
if ($LASTEXITCODE -ne 0) { throw "Unable to install desktop build dependencies" }

Write-Output "python=$python"
