$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $Root ".runtime"
$BackendOutLog = Join-Path $RuntimeDir "backend.out.log"
$BackendErrLog = Join-Path $RuntimeDir "backend.err.log"
$FrontendOutLog = Join-Path $RuntimeDir "frontend.out.log"
$FrontendErrLog = Join-Path $RuntimeDir "frontend.err.log"
$BackendPid = Join-Path $RuntimeDir "backend.pid"
$FrontendPid = Join-Path $RuntimeDir "frontend.pid"

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

function Resolve-Python {
    $candidates = @(
        @{ File = "py"; Args = @("-3") },
        @{ File = "python"; Args = @() },
        @{ File = "python3"; Args = @() }
    )

    foreach ($candidate in $candidates) {
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $null = & where.exe $candidate.File 2>$null
        $found = $LASTEXITCODE -eq 0
        $ErrorActionPreference = $previousErrorActionPreference

        if ($found) {
            return $candidate
        }
    }

    throw "Python was not found. Install Python 3.10+ or add it to PATH."
}

function Test-PortOpen {
    param([int] $Port)
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse("127.0.0.1"), $Port)
        $listener.Start()
        $listener.Stop()
        return $false
    } catch {
        return $true
    }
}

function Start-AgentProcess {
    param(
        [string] $Name,
        [string] $PidPath,
        [string] $OutLogPath,
        [string] $ErrLogPath,
        [string] $WorkingDirectory,
        [string] $FilePath,
        [string[]] $Arguments
    )

    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $OutLogPath `
        -RedirectStandardError $ErrLogPath `
        -PassThru `
        -WindowStyle Hidden

    Set-Content -Path $PidPath -Value $process.Id
    Write-Host "$Name started with PID $($process.Id)"
}

$python = Resolve-Python
$pythonFile = $python.File
$backendArgs = @($python.Args + @("-m", "backend.server"))
$frontendArgs = @($python.Args + @("-m", "http.server", "4005", "--bind", "127.0.0.1"))

if (Test-PortOpen -Port 8005) {
    Write-Host "Backend port 8005 is already in use."
} else {
    Start-AgentProcess -Name "Backend" -PidPath $BackendPid -OutLogPath $BackendOutLog -ErrLogPath $BackendErrLog -WorkingDirectory $Root -FilePath $pythonFile -Arguments $backendArgs
}

if (Test-PortOpen -Port 4005) {
    Write-Host "Frontend port 4005 is already in use."
} else {
    Start-AgentProcess -Name "Frontend" -PidPath $FrontendPid -OutLogPath $FrontendOutLog -ErrLogPath $FrontendErrLog -WorkingDirectory (Join-Path $Root "frontend") -FilePath $pythonFile -Arguments $frontendArgs
}

Write-Host ""
Write-Host "Frontend: http://localhost:4005"
Write-Host "Backend:  http://localhost:8005"
Write-Host "Logs:     $RuntimeDir"
