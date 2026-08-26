param(
    [string]$Ffmpeg = "",
    [string]$Ffprobe = "",
    [string]$YtDlp = "",
    [string]$Deno = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$destination = Join-Path $root "desktop\src-tauri\resources\tools"
New-Item -ItemType Directory -Force -Path $destination | Out-Null

function Resolve-Tool {
    param([string]$ExplicitPath, [string]$CommandName, [string[]]$Fallbacks)
    if ($ExplicitPath) {
        if (-not (Test-Path -LiteralPath $ExplicitPath -PathType Leaf)) {
            throw "$CommandName was not found: $ExplicitPath"
        }
        return (Resolve-Path -LiteralPath $ExplicitPath).Path
    }
    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($command -and $command.Source -and (Test-Path -LiteralPath $command.Source -PathType Leaf)) {
        return $command.Source
    }
    foreach ($candidate in $Fallbacks) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "$CommandName is required for the desktop installer"
}

$resolvedFfmpeg = Resolve-Tool $Ffmpeg "ffmpeg" @(
    (Join-Path $root "ffmpeg\ffmpeg.exe"),
    "D:\soft\bin\ffmpeg.exe"
)
$resolvedFfprobe = Resolve-Tool $Ffprobe "ffprobe" @(
    (Join-Path $root "ffmpeg\ffprobe.exe"),
    "D:\soft\bin\ffprobe.exe"
)
$resolvedYtDlp = Resolve-Tool $YtDlp "yt-dlp" @(
    (Join-Path $root "ytdlp\yt-dlp.exe"),
    "F:\youtube\yt-dlp.exe"
)
$resolvedDeno = Resolve-Tool $Deno "deno" @(
    (Join-Path $env:USERPROFILE ".deno\bin\deno.exe"),
    (Join-Path $env:USERPROFILE "anaconda3\Scripts\deno.exe")
)

Copy-Item -LiteralPath $resolvedFfmpeg -Destination (Join-Path $destination "ffmpeg.exe") -Force
Copy-Item -LiteralPath $resolvedFfprobe -Destination (Join-Path $destination "ffprobe.exe") -Force
Copy-Item -LiteralPath $resolvedYtDlp -Destination (Join-Path $destination "yt-dlp.exe") -Force
Copy-Item -LiteralPath $resolvedDeno -Destination (Join-Path $destination "deno.exe") -Force

foreach ($name in "ffmpeg.exe", "ffprobe.exe", "yt-dlp.exe", "deno.exe") {
    $path = Join-Path $destination $name
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Output "tool=$path"
    Write-Output "sha256=$hash"
}
