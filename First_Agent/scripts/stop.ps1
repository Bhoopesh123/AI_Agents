$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $Root ".runtime"
$PidFiles = @(
    (Join-Path $RuntimeDir "backend.pid")
    (Join-Path $RuntimeDir "frontend.pid")
)

foreach ($PidFile in $PidFiles) {
    if (-not (Test-Path $PidFile)) {
        continue
    }

    $ProcessId = Get-Content $PidFile | Select-Object -First 1
    if ($ProcessId) {
        $Process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($Process) {
            Stop-Process -Id $ProcessId -Force
            Write-Host "Stopped process $ProcessId"
        }
    }
    Remove-Item $PidFile -Force
}

Write-Host "Grafana Monitoring Agent stopped."
