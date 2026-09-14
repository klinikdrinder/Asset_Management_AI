[CmdletBinding()]
param([int]$LauncherPid = 0)

$ErrorActionPreference = "Stop"
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$runtimeRoot = Join-Path $repoRoot ".kdi-runtime"
$pointer = Join-Path $runtimeRoot "current-release.txt"
$logRoot = Join-Path $runtimeRoot "logs"
$eventLog = Join-Path $logRoot "kdi-background-runtime.log"
$stdoutLog = Join-Path $logRoot "kdi-media-library.stdout.log"
$stderrLog = Join-Path $logRoot "kdi-media-library.stderr.log"
$visualStdoutLog = Join-Path $logRoot "kdi-openclip-query.stdout.log"
$visualStderrLog = Join-Path $logRoot "kdi-openclip-query.stderr.log"
$statePath = Join-Path $runtimeRoot "production-runtime.json"
$mutexName = "Local\KDI.MediaLibrary.Production.3000"
$mutex = [Threading.Mutex]::new($false, $mutexName)
$ownsMutex = $false
$process = $null
$visualProcess = $null

function Write-RuntimeLog([string]$message) {
    Add-Content -LiteralPath $eventLog -Value ("{0} {1}" -f (Get-Date).ToUniversalTime().ToString("o"), $message) -Encoding UTF8
}
function Rotate-Log([string]$path, [long]$maximumBytes = 10MB) {
    if ((Test-Path -LiteralPath $path) -and (Get-Item -LiteralPath $path).Length -ge $maximumBytes) {
        for ($index = 4; $index -ge 1; $index--) {
            if (Test-Path -LiteralPath "$path.$index") { Move-Item -LiteralPath "$path.$index" -Destination "$path.$($index + 1)" -Force }
        }
        Move-Item -LiteralPath $path -Destination "$path.1" -Force
    }
}
function Test-LauncherAlive { return $LauncherPid -gt 0 -and [bool](Get-Process -Id $LauncherPid -ErrorAction SilentlyContinue) }
function Get-HealthStatus {
    try { return [int](curl.exe -s -o NUL -w "%{http_code}" --max-redirs 0 --connect-timeout 2 http://127.0.0.1:3000/api/health) } catch { return 0 }
}
function Write-State([string]$phase, [string]$release, [int]$childPid = 0) {
    $state = [ordered]@{ supervisorPid=$PID; launcherPid=$LauncherPid; childPid=$childPid; release=$release; phase=$phase; updated=(Get-Date).ToUniversalTime().ToString("o") }
    $temp = "$statePath.$PID.tmp"
    $state | ConvertTo-Json -Compress | Set-Content -LiteralPath $temp -Encoding UTF8
    Move-Item -LiteralPath $temp -Destination $statePath -Force
}
function Stop-VerifiedChild {
    if ($process -and -not $process.HasExited) {
        Write-RuntimeLog "child_stop pid=$($process.Id) reason=launcher_exit"
        taskkill.exe /PID $process.Id /T | Out-Null
        if (-not $process.WaitForExit(10000)) {
            Write-RuntimeLog "child_force_stop pid=$($process.Id)"
            taskkill.exe /PID $process.Id /T /F | Out-Null
            $process.WaitForExit(5000) | Out-Null
        }
    }
    if ($visualProcess -and -not $visualProcess.HasExited) {
        Write-RuntimeLog "visual_child_stop pid=$($visualProcess.Id)"
        Stop-Process -Id $visualProcess.Id -Force -ErrorAction SilentlyContinue
        $visualProcess.WaitForExit(5000) | Out-Null
    }
}

try {
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    foreach ($path in @($eventLog, $stdoutLog, $stderrLog, $visualStdoutLog, $visualStderrLog)) { Rotate-Log $path }
    if (-not (Test-LauncherAlive)) { Write-RuntimeLog "startup_failed reason=launcher_missing launcher_pid=$LauncherPid"; exit 19 }
    $ownsMutex = $mutex.WaitOne(0)
    if (-not $ownsMutex) {
        Write-RuntimeLog "startup_failed reason=duplicate_runtime_mutex_unhealthy"
        exit 20
    }
    if (Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue) {
        Write-RuntimeLog "startup_failed reason=port_3000_occupied"
        exit 21
    }
    $appDirectory = if (Test-Path -LiteralPath $pointer) { (Get-Content -LiteralPath $pointer -Raw).Trim() } else { Join-Path $repoRoot "dashboard" }
    foreach ($required in @("package.json", ".env.local", ".next\BUILD_ID", "node_modules\next\dist\bin\next")) {
        if (-not (Test-Path -LiteralPath (Join-Path $appDirectory $required))) { Write-RuntimeLog "startup_failed reason=missing_required_file file=$required app=$appDirectory"; exit 22 }
    }
    if ((Test-Path -LiteralPath $pointer) -and -not (Test-Path -LiteralPath (Join-Path $appDirectory ".kdi-candidate-verified.json"))) { Write-RuntimeLog "startup_failed reason=missing_release_verification app=$appDirectory"; exit 23 }
    $node = (Get-Command node.exe -ErrorAction SilentlyContinue).Source
    if (-not $node) { Write-RuntimeLog "startup_failed reason=node_not_found"; exit 24 }
    $nextCli = Join-Path $appDirectory "node_modules\next\dist\bin\next"
    $python = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) { Write-RuntimeLog "startup_failed reason=python_not_found"; exit 29 }
    if (Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
        Write-RuntimeLog "startup_failed reason=port_8765_occupied"; exit 30
    }
    Write-RuntimeLog "startup release=$appDirectory bind=127.0.0.1 port=3000 supervisor_pid=$PID launcher_pid=$LauncherPid"
    Write-State "starting" $appDirectory
    $visualProcess = Start-Process -FilePath $python -ArgumentList @("-m","uvicorn","visual_indexing.service:app","--host","127.0.0.1","--port","8765") -WorkingDirectory $appDirectory -WindowStyle Hidden -RedirectStandardOutput $visualStdoutLog -RedirectStandardError $visualStderrLog -PassThru
    $visualDeadline=(Get-Date).AddSeconds(30); $visualHealthy=$false
    while((Get-Date)-lt $visualDeadline){
        $visualProcess.Refresh(); if($visualProcess.HasExited){break}
        try{$visualStatus=[int](curl.exe -s -o NUL -w "%{http_code}" --connect-timeout 2 http://127.0.0.1:8765/health);if($visualStatus-eq 200){$visualHealthy=$true;break}}catch{}
        Start-Sleep -Milliseconds 500
    }
    if(-not $visualHealthy){Write-RuntimeLog "startup_failed reason=visual_query_service_unhealthy";Stop-VerifiedChild;exit 31}
    Write-RuntimeLog "visual_query_healthy pid=$($visualProcess.Id) port=8765"
    $process = Start-Process -FilePath $node -ArgumentList @("`"$nextCli`"", "start", "-H", "127.0.0.1", "-p", "3000") -WorkingDirectory $appDirectory -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru
    Write-State "starting" $appDirectory $process.Id
    $deadline = (Get-Date).AddSeconds(120)
    $lastStage = ""
    while ((Get-Date) -lt $deadline) {
        $process.Refresh()
        $visualProcess.Refresh()
        if (-not (Test-LauncherAlive)) { Stop-VerifiedChild; exit 0 }
        if ($visualProcess.HasExited) { Write-RuntimeLog "runtime_failed reason=visual_query_child_exited exit_code=$($visualProcess.ExitCode)"; Stop-VerifiedChild; exit 32 }
        if ($process.HasExited) { Write-RuntimeLog "startup_failed reason=child_exited pid=$($process.Id) exit_code=$($process.ExitCode) stdout=$stdoutLog stderr=$stderrLog"; exit 25 }
        $listener = @(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)
        $health = if ($listener) { Get-HealthStatus } else { 0 }
        $stage = if (-not $listener) { "process_alive_port_wait" } elseif ($health -eq 200) { "healthy" } else { "port_listening_health_wait" }
        if ($stage -ne $lastStage) { Write-RuntimeLog "startup_progress stage=$stage child_pid=$($process.Id) health=$health"; $lastStage=$stage }
        if ($health -eq 200) { break }
        Start-Sleep -Milliseconds 500
    }
    if ($lastStage -ne "healthy") { Write-RuntimeLog "startup_failed reason=cold_start_timeout stage=$lastStage child_pid=$($process.Id) stdout=$stdoutLog stderr=$stderrLog"; Stop-VerifiedChild; exit 25 }
    Write-State "healthy" $appDirectory $process.Id
    Write-RuntimeLog "healthy supervisor_pid=$PID child_pid=$($process.Id) url=http://127.0.0.1:3000/api/health"
    $nextHealth = Get-Date
    $failures = 0
    while ($true) {
        $process.Refresh()
        if (-not (Test-LauncherAlive)) { Stop-VerifiedChild; exit 0 }
        if ($process.HasExited) { Write-RuntimeLog "runtime_failed reason=child_exited exit_code=$($process.ExitCode) stdout=$stdoutLog stderr=$stderrLog"; exit 28 }
        if ((Get-Date) -ge $nextHealth) {
            if ((Get-HealthStatus) -eq 200) { $failures=0 } else { $failures++; Write-RuntimeLog "health_check_failed consecutive=$failures" }
            if ($failures -ge 3) { Write-RuntimeLog "runtime_failed reason=repeated_health_failure action=terminate_child"; taskkill.exe /PID $process.Id /T /F | Out-Null; exit 27 }
            $nextHealth=(Get-Date).AddSeconds(10)
        }
        Start-Sleep -Milliseconds 500
    }
} catch {
    Write-RuntimeLog ("runtime_exception type={0} message={1}" -f $_.Exception.GetType().Name, ($_.Exception.Message -replace '[\r\n]+',' '))
    exit 26
} finally {
    if ($process -and -not $process.HasExited) { Stop-VerifiedChild }
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
    if (Test-Path -LiteralPath $statePath) {
        try { $state=Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json; if ($state.supervisorPid -eq $PID) { Remove-Item -LiteralPath $statePath -Force } } catch {}
    }
    Write-RuntimeLog "shutdown supervisor_pid=$PID mutex_released=$ownsMutex"
}
