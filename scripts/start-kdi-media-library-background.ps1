[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$runtimeRoot = Join-Path $repoRoot ".kdi-runtime"
$pointer = Join-Path $runtimeRoot "current-release.txt"
$logRoot = Join-Path $runtimeRoot "logs"
$eventLog = Join-Path $logRoot "kdi-background-runtime.log"
$stdoutLog = Join-Path $logRoot "kdi-media-library.stdout.log"
$stderrLog = Join-Path $logRoot "kdi-media-library.stderr.log"
$mutex = [Threading.Mutex]::new($false, "Local\KDI.MediaLibrary.Production.3000")
$ownsMutex = $false

function Write-RuntimeLog([string]$message) {
    $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString("o"), $message
    Add-Content -LiteralPath $eventLog -Value $line -Encoding UTF8
}

function Rotate-Log([string]$path, [long]$maximumBytes = 10MB) {
    if ((Test-Path -LiteralPath $path) -and (Get-Item -LiteralPath $path).Length -ge $maximumBytes) {
        for ($index = 4; $index -ge 1; $index--) {
            $source = "$path.$index"
            $destination = "$path." + ($index + 1)
            if (Test-Path -LiteralPath $source) { Move-Item -LiteralPath $source -Destination $destination -Force }
        }
        Move-Item -LiteralPath $path -Destination "$path.1" -Force
    }
}

function Test-KdiHealth {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:3000/api/health" -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -eq 200
    } catch { return $false }
}

try {
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    foreach ($path in @($eventLog, $stdoutLog, $stderrLog)) { Rotate-Log $path }

    $ownsMutex = $mutex.WaitOne(0)
    if (-not $ownsMutex) {
        if (Test-KdiHealth) { Write-RuntimeLog "already_healthy action=skip"; exit 0 }
        Write-RuntimeLog "startup_failed reason=duplicate_runtime_mutex_unhealthy"
        exit 20
    }

    if (Test-KdiHealth) { Write-RuntimeLog "already_healthy action=skip"; exit 0 }
    $occupied = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
    if ($occupied) { Write-RuntimeLog "startup_failed reason=port_3000_occupied_unhealthy"; exit 21 }

    $appDirectory = Join-Path $repoRoot "dashboard"
    if (Test-Path -LiteralPath $pointer) { $appDirectory = (Get-Content -LiteralPath $pointer -Raw).Trim() }
    foreach ($required in @("package.json", ".env.local", ".next\BUILD_ID")) {
        if (-not (Test-Path -LiteralPath (Join-Path $appDirectory $required))) {
            Write-RuntimeLog "startup_failed reason=missing_required_file file=$required app=$appDirectory"
            exit 22
        }
    }
    if ((Test-Path -LiteralPath $pointer) -and -not (Test-Path -LiteralPath (Join-Path $appDirectory ".kdi-candidate-verified.json"))) {
        Write-RuntimeLog "startup_failed reason=missing_release_verification app=$appDirectory"
        exit 23
    }

    $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
    if (-not $npm) { Write-RuntimeLog "startup_failed reason=npm_not_found"; exit 24 }

    Write-RuntimeLog "startup release=$appDirectory bind=127.0.0.1 port=3000"
    $arguments = "/d /s /c `"`"$npm`" start`""
    $process = Start-Process -FilePath "$env:SystemRoot\System32\cmd.exe" -ArgumentList $arguments -WorkingDirectory $appDirectory -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru

    $healthy = $false
    for ($attempt = 1; $attempt -le 40 -and -not $process.HasExited; $attempt++) {
        if (Test-KdiHealth) { $healthy = $true; break }
        if ($attempt -in @(1, 10, 20, 30, 40)) { Write-RuntimeLog "health_wait attempt=$attempt" }
        Start-Sleep -Seconds 1
        $process.Refresh()
    }
    if (-not $healthy) {
        Write-RuntimeLog "health_failed action=terminate_child"
        if (-not $process.HasExited) { taskkill.exe /PID $process.Id /T /F | Out-Null }
        exit 25
    }

    Write-RuntimeLog "healthy pid=$($process.Id) url=http://127.0.0.1:3000/api/health"
    $consecutiveHealthFailures = 0
    while (-not $process.HasExited) {
        Start-Sleep -Seconds 10
        $process.Refresh()
        if ($process.HasExited) { break }
        if (Test-KdiHealth) {
            $consecutiveHealthFailures = 0
        } else {
            $consecutiveHealthFailures++
            Write-RuntimeLog "health_check_failed consecutive=$consecutiveHealthFailures"
            if ($consecutiveHealthFailures -ge 3) {
                Write-RuntimeLog "runtime_failed reason=repeated_health_failure action=terminate_child"
                taskkill.exe /PID $process.Id /T /F | Out-Null
                exit 27
            }
        }
    }
    $process.WaitForExit()
    $process.Refresh()
    Write-RuntimeLog "runtime_failed reason=child_exited exit_code=$($process.ExitCode)"
    exit 28
} catch {
    Write-RuntimeLog ("startup_exception type={0} message={1}" -f $_.Exception.GetType().Name, ($_.Exception.Message -replace '[\r\n]+',' '))
    exit 26
} finally {
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
