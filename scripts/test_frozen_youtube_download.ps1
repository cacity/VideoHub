param(
    [string]$Url = "https://www.youtube.com/watch?v=COpWTc7BFro",
    [string]$Proxy = "",
    [string]$Format = "best[height<=144]/best"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$sidecar = Join-Path $root "desktop\src-tauri\binaries\videohub-sidecar-x86_64-pc-windows-msvc.exe"
$toolsDir = Join-Path $root "desktop\src-tauri\resources\tools"
$smokeRoot = Join-Path $root "workspace\_frozen_youtube_download_smoke"
$token = [guid]::NewGuid().ToString("N")
$dataDir = Join-Path $smokeRoot "data"
$workspaceDir = Join-Path $smokeRoot "workspace"
$outputDir = Join-Path $smokeRoot "output-$token"
New-Item -ItemType Directory -Force -Path $dataDir, $workspaceDir, $outputDir | Out-Null

$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = $listener.LocalEndpoint.Port
$listener.Stop()
$originalPath = $env:PATH
$env:PATH = "$toolsDir;$originalPath"
$env:VIDEOHUB_SESSION_TOKEN = $token
$process = Start-Process -FilePath $sidecar -ArgumentList @(
    "serve", "--host", "127.0.0.1", "--port", $port,
    "--data-dir", $dataDir, "--workspace-dir", $workspaceDir,
    "--no-extension-bridge"
) -WindowStyle Hidden -PassThru

try {
    $baseUrl = "http://127.0.0.1:$port"
    $healthy = $false
    for ($attempt = 0; $attempt -lt 80; $attempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-RestMethod "$baseUrl/v1/health" -TimeoutSec 2
            if ($health.status -eq "ok") {
                $healthy = $true
                break
            }
        } catch {
            # The one-file sidecar has a measurable cold-start extraction delay.
        }
    }
    if (-not $healthy) {
        $process.Refresh()
        Write-Host "Sidecar exited: $($process.HasExited)"
        if ($process.HasExited) {
            Write-Host "Sidecar exit code: $($process.ExitCode)"
        }
        throw "Frozen sidecar did not become healthy"
    }

    $parameters = @{
        url = $Url
        platform = "youtube"
        output_dir = $outputDir
        format = $Format
    }
    if ($Proxy) {
        $parameters.proxy = $Proxy
    }
    $headers = @{ Authorization = "Bearer $token" }
    $body = @{
        operation = "platform.download"
        parameters = $parameters
    } | ConvertTo-Json -Depth 6
    $job = Invoke-RestMethod "$baseUrl/v1/jobs" -Method Post -Headers $headers `
        -ContentType "application/json" -Body $body

    $timeout = [System.Diagnostics.Stopwatch]::StartNew()
    $lastPollError = ""
    do {
        Start-Sleep -Seconds 1
        try {
            $job = Invoke-RestMethod "$baseUrl/v1/jobs/$($job.id)" -Headers $headers -TimeoutSec 5
            $lastPollError = ""
        } catch {
            # The one-file sidecar may be busy receiving a long worker update.
            # A transient poll failure must not terminate the underlying download.
            $lastPollError = $_.Exception.Message
            continue
        }
    } while ($job.status -notin @("succeeded", "failed", "cancelled") -and $timeout.Elapsed.TotalSeconds -lt 300)

    if ($job.status -ne "succeeded") {
        $job | ConvertTo-Json -Depth 8
        if ($lastPollError) {
            Write-Host "Last polling error: $lastPollError"
        }
        throw "Frozen download job ended with $($job.status)"
    }
    $files = @($job.result.files)
    $valid = $files.Count -gt 0 -and (Test-Path -LiteralPath $files[0])
    $logs = @($job.logs) -join "`n"
    $result = [pscustomobject]@{
        health = $health.status
        status = $job.status
        files = $files
        valid = $valid
        saw_initial_client_error = $logs -match "Requested format is not available|HTTP Error 403"
        saw_web_embedded_retry = $logs -match "web_embedded|web embedded"
        progress = $job.progress
        message = $job.message
        log_tail = @($job.logs | Select-Object -Last 12)
        port = $port
    }
    $result | ConvertTo-Json -Depth 6
    if (-not $valid) {
        throw "Frozen job did not produce a valid media file"
    }
} finally {
    # The sidecar starts a child worker per job.  Stop its direct worker first
    # so an interrupted network download cannot outlive this smoke test.
    if ($process) {
        $childProcesses = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($process.Id)" `
            -ErrorAction SilentlyContinue
        foreach ($child in $childProcesses) {
            Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    $env:PATH = $originalPath
    Remove-Item Env:VIDEOHUB_SESSION_TOKEN -ErrorAction SilentlyContinue
}
