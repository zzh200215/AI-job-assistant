param(
    [switch]$Stop,
    [switch]$SkipSeed,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$python = Join-Path $backendDir ".venv\Scripts\python.exe"
$logDir = Join-Path $backendDir "reports\local-demo"
$backendPort = 8001
$frontendPort = 5173
$backendHealth = "http://127.0.0.1:$backendPort/api/system/health"
$frontendUrl = "http://127.0.0.1:$frontendPort/"

function Test-TcpPort {
    param([string]$HostName, [int]$Port, [int]$TimeoutMs = 1000)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne($TimeoutMs)) { return $false }
        $client.EndConnect($iar)
        return $true
    }
    catch { return $false }
    finally { $client.Close() }
}

function Get-ListeningPids {
    param([int]$Port)
    return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
}

function Stop-PortListeners {
    param([int]$Port)
    $pids = Get-ListeningPids -Port $Port
    if (-not $pids) {
        Write-Host "Port $Port is free."
        return
    }
    $allowed = @("python", "pythonw", "node", "npm", "cmd")
    foreach ($processId in $pids) {
        $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if (-not $proc) { continue }
        if ($allowed -notcontains $proc.ProcessName) {
            Write-Warning "Port $Port is held by $($proc.ProcessName) (PID $processId); not stopping it."
            continue
        }
        Write-Host "Stopping $($proc.ProcessName) (PID $processId) on port $Port..."
        Stop-Process -Id $processId -Force
    }
}

function Wait-HttpOk {
    param([string]$Url, [int]$TimeoutSeconds = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) { return }
        }
        catch { }
        Start-Sleep -Milliseconds 500
    }
    throw "Timed out waiting for $Url"
}

if ($Stop) {
    foreach ($port in @($frontendPort, $backendPort)) {
        Stop-PortListeners -Port $port
    }
    $pidFile = Join-Path $logDir "pids.json"
    if (Test-Path -LiteralPath $pidFile) {
        Remove-Item -LiteralPath $pidFile -Force
    }
    Write-Host "Local demo stopped."
    exit 0
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing backend virtualenv: $python. See README for setup."
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendDir "node_modules"))) {
    throw "Missing frontend/node_modules. Run npm install in frontend first."
}
if (-not (Test-TcpPort -HostName "127.0.0.1" -Port 3306)) {
    throw "MySQL 127.0.0.1:3306 is not reachable. Start MySQL first."
}
if (-not (Test-TcpPort -HostName "127.0.0.1" -Port 6379)) {
    Write-Host "Warning: Redis 127.0.0.1:6379 is not reachable; the thread backend does not need it."
}

$backendUp = $false
$frontendUp = $false
try {
    $response = Invoke-WebRequest -Uri $backendHealth -UseBasicParsing -TimeoutSec 2
    $backendUp = $response.StatusCode -eq 200
}
catch { }
try {
    $response = Invoke-WebRequest -Uri $frontendUrl -UseBasicParsing -TimeoutSec 2
    $frontendUp = $response.StatusCode -eq 200
}
catch { }

if ($backendUp -and $frontendUp) {
    Write-Host "Local demo is already running."
    Write-Host "  Frontend: $frontendUrl"
    Write-Host "  Backend : $backendHealth"
    Write-Host "  Demo    : demo / Demo@12345"
    if ($OpenBrowser) { Start-Process $frontendUrl }
    exit 0
}
if ($backendUp -or $frontendUp) {
    throw "One of the ports is already in use. Run this script with -Stop first."
}
if ((Get-ListeningPids -Port $backendPort) -or (Get-ListeningPids -Port $frontendPort)) {
    throw "Port $backendPort or $frontendPort is already in use. Run this script with -Stop first."
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$previousEnv = @{}
foreach ($name in @("LLM_PROVIDER", "EMBEDDING_PROVIDER", "ORCHESTRATION_BACKEND", "LLM_ALLOW_MOCK_FALLBACK", "PYTHONUTF8")) {
    $previousEnv[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}
$env:LLM_PROVIDER = "mock"
$env:EMBEDDING_PROVIDER = "mock"
$env:ORCHESTRATION_BACKEND = "thread"
$env:LLM_ALLOW_MOCK_FALLBACK = "true"
$env:PYTHONUTF8 = "1"

$started = @()
try {
    if (-not $SkipSeed) {
        Write-Host "Seeding demo account and data..."
        Push-Location $backendDir
        try {
            & $python "scripts/create_demo_user.py" --force *> (Join-Path $logDir "seed.log")
            if ($LASTEXITCODE -ne 0) {
                throw "create_demo_user.py failed; see $logDir\seed.log"
            }
        }
        finally {
            Pop-Location
        }
    }

    Write-Host "Starting backend on port $backendPort..."
    $backendOut = Join-Path $logDir "backend.out.log"
    $backendErr = Join-Path $logDir "backend.err.log"
    $backendProc = Start-Process -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$backendPort") `
        -WorkingDirectory $backendDir -WindowStyle Hidden `
        -RedirectStandardOutput $backendOut -RedirectStandardError $backendErr -PassThru
    $started += $backendProc
    Wait-HttpOk -Url $backendHealth -TimeoutSeconds 90

    $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    Write-Host "Starting frontend on port $frontendPort..."
    $frontendOut = Join-Path $logDir "frontend.out.log"
    $frontendErr = Join-Path $logDir "frontend.err.log"
    $frontendProc = Start-Process -FilePath $npm `
        -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$frontendPort", "--strictPort") `
        -WorkingDirectory $frontendDir -WindowStyle Hidden `
        -RedirectStandardOutput $frontendOut -RedirectStandardError $frontendErr -PassThru
    $started += $frontendProc
    Wait-HttpOk -Url $frontendUrl -TimeoutSeconds 60

    $backendListener = @(Get-ListeningPids -Port $backendPort) | Select-Object -First 1
    $frontendListener = @(Get-ListeningPids -Port $frontendPort) | Select-Object -First 1
    $backendPidForState = $backendProc.Id
    if ($backendListener) { $backendPidForState = $backendListener }
    $frontendPidForState = $frontendProc.Id
    if ($frontendListener) { $frontendPidForState = $frontendListener }
    $state = [ordered]@{
        backend_pid = $backendPidForState
        frontend_pid = $frontendPidForState
        backend_start_pid = $backendProc.Id
        frontend_start_pid = $frontendProc.Id
        backend_port = $backendPort
        frontend_port = $frontendPort
        started_at = (Get-Date).ToString("s")
    }
    $state | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logDir "pids.json") -Encoding UTF8

    Write-Host ""
    Write-Host "Local demo is ready."
    Write-Host "  Frontend: $frontendUrl"
    Write-Host "  Backend : $backendHealth"
    Write-Host "  Demo    : demo / Demo@12345"
    Write-Host "  Logs    : $logDir"
    Write-Host "  Stop    : .\scripts\local-demo.ps1 -Stop"
    if ($OpenBrowser) { Start-Process $frontendUrl }
}
catch {
    Write-Host "Startup failed: $($_.Exception.Message)"
    foreach ($proc in $started) {
        if ($proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
    foreach ($port in @($frontendPort, $backendPort)) {
        Stop-PortListeners -Port $port
    }
    throw
}
finally {
    foreach ($name in $previousEnv.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnv[$name], "Process")
    }
}
