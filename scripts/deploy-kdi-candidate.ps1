[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$CandidateRoot,
    [string]$TaskName = "KDI Media Library"
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$liveRoot = [IO.Path]::GetFullPath((Join-Path $scriptRoot ".."))
if ($liveRoot -match '^(.*)[\\/]\.worktrees[\\/][^\\/]+$') { $liveRoot = $Matches[1] }
$runtimeRoot = Join-Path $liveRoot ".kdi-runtime"
$releaseRoot = Join-Path $runtimeRoot "releases"
$logRoot = Join-Path $runtimeRoot "logs"
New-Item -ItemType Directory -Force -Path $releaseRoot,$logRoot | Out-Null
$lockPath = Join-Path $runtimeRoot "deploy.lock"
$lock = $null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $logRoot "deployment-$timestamp.log"

function Log([string]$eventName, [hashtable]$fields = @{}) {
    $record = [ordered]@{ timestamp=(Get-Date).ToUniversalTime().ToString("o"); event=$eventName }
    foreach($key in $fields.Keys){ $record[$key]=$fields[$key] }
    ($record | ConvertTo-Json -Compress) | Tee-Object -FilePath $logFile -Append
}
function Set-Pointer([string]$path, [string]$value) {
    $temp = "$path.$PID.tmp"
    Set-Content -LiteralPath $temp -Value $value -NoNewline
    Move-Item -LiteralPath $temp -Destination $path -Force
}
function Wait-Http([string]$uri, [int[]]$accepted, [int]$seconds = 30) {
    for($i=0;$i -lt $seconds;$i++){
        try { $status=[int](curl.exe -s -o NUL -w "%{http_code}" --max-redirs 0 --connect-timeout 5 $uri); if($status -in $accepted){return $true} } catch {}
        Start-Sleep -Seconds 1
    }
    return $false
}
function Test-MutexFree {
    $probe=[Threading.Mutex]::new($false,"Local\KDI.MediaLibrary.Production.3000")
    try { $free=$probe.WaitOne(0); if($free){$probe.ReleaseMutex()}; return $free } finally {$probe.Dispose()}
}
function Get-VerifiedRuntimeProcesses {
    $statePath=Join-Path $runtimeRoot "production-runtime.json"
    $verified=@()
    if(Test-Path -LiteralPath $statePath){
        $state=Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $supervisor=Get-CimInstance Win32_Process -Filter "ProcessId=$($state.supervisorPid)" -ErrorAction SilentlyContinue
        if($supervisor){
            if($supervisor.Name -ne "powershell.exe" -or $supervisor.CommandLine -notmatch [regex]::Escape((Join-Path $liveRoot "scripts\start-kdi-media-library-background.ps1"))){throw "Runtime state points to an unverified supervisor PID."}
            $verified += $supervisor
        }
        $child=$null
        if ([int]$state.childPid -gt 0) {
            $child=Get-CimInstance Win32_Process -Filter "ProcessId=$($state.childPid)" -ErrorAction SilentlyContinue
        }
        if($child){
            if($child.Name -ne "node.exe" -or [int]$child.ParentProcessId -ne [int]$state.supervisorPid){throw "Runtime state points to an unverified production child PID."}
            $expectedCli=Join-Path $state.release "node_modules\next\dist\bin\next"
            if($child.CommandLine -and ($child.CommandLine -notmatch [regex]::Escape($expectedCli) -or $child.CommandLine -notmatch 'start.*127\.0\.0\.1.*3000')){throw "Runtime child command line does not match the recorded KDI release."}
            if($child.CommandLine){$verified += $child}
        }
    }
    return @($verified)
}
function Stop-ProductionCleanly([string]$reason) {
    $initial=@(Get-VerifiedRuntimeProcesses)
    Log "runtime_stop_started" @{ reason=$reason; pids=($initial.ProcessId -join ',') }
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    $deadline=(Get-Date).AddSeconds(30)
    do {
        $remaining=@(Get-VerifiedRuntimeProcesses)
        $listeners=@(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)
        $mutexFree=Test-MutexFree
        if($remaining.Count -eq 0 -and $listeners.Count -eq 0 -and $mutexFree){Log "runtime_stop_passed" @{ reason=$reason; fallback="NO" }; return}
        Start-Sleep -Milliseconds 500
    } while((Get-Date) -lt $deadline)
    $remaining=@(Get-VerifiedRuntimeProcesses)
    foreach($process in $remaining | Sort-Object ProcessId -Unique){ Log "runtime_process_terminate" @{ pid=$process.ProcessId; name=$process.Name; parent=$process.ParentProcessId; reason=$reason } }
    $supervisor=@($remaining | Where-Object Name -eq "powershell.exe" | Select-Object -First 1)
    if($supervisor){taskkill.exe /PID $supervisor.ProcessId /T /F | Out-Null}
    $deadline=(Get-Date).AddSeconds(15)
    do {
        $remaining=@(Get-VerifiedRuntimeProcesses); $listeners=@(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue); $mutexFree=Test-MutexFree
        if($remaining.Count -eq 0 -and $listeners.Count -eq 0 -and $mutexFree){Log "runtime_stop_passed" @{ reason=$reason; fallback="YES" }; return}
        Start-Sleep -Milliseconds 250
    } while((Get-Date) -lt $deadline)
    throw "KDI runtime did not completely stop; deployment cannot continue."
}
function Start-ProductionAndWait([string]$reason) {
    if(-not (Test-MutexFree)){throw "KDI runtime mutex is still owned before startup."}
    if(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue){throw "Port 3000 is still listening before startup."}
    Start-ScheduledTask -TaskName $TaskName
    $deadline=(Get-Date).AddSeconds(120); $lastStage=""; $seenRuntime=$false; $missingRuntimePolls=0
    do {
        $runtime=@(Get-VerifiedRuntimeProcesses); $child=@($runtime|Where-Object Name -eq 'node.exe'|Select-Object -First 1); $listener=@(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)
        $health=if($listener){try{[int](curl.exe -s -o NUL -w "%{http_code}" --max-redirs 0 --connect-timeout 2 http://127.0.0.1:3000/api/health)}catch{0}}else{0}
        if($runtime){$seenRuntime=$true;$missingRuntimePolls=0}elseif($seenRuntime){$missingRuntimePolls++;if($missingRuntimePolls -ge 6){throw "Production runtime exited during startup; inspect production stdout/stderr logs."}}
        $stage=if(-not $runtime){"no_process"}elseif(-not $child){"supervisor_no_child"}elseif(-not $listener){"child_alive_port_wait"}elseif($health -ne 200){"port_listening_health_wait"}else{"healthy"}
        $childPid=if($child){$child.ProcessId}else{0}
        if($stage -ne $lastStage){Log "runtime_start_progress" @{ reason=$reason; stage=$stage; childPid=$childPid; health=$health };$lastStage=$stage}
        if($stage -eq "healthy"){return}
        if($child -and -not (Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue)){throw "Production child exited during startup; inspect production stdout/stderr logs."}
        Start-Sleep -Milliseconds 500
    } while((Get-Date) -lt $deadline)
    throw "Production startup exceeded the bounded cold-start window at stage $lastStage."
}

try {
    try { $lock=[IO.File]::Open($lockPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None) }
    catch { throw "Another KDI deployment is already running: $lockPath" }
    $writer=[IO.StreamWriter]::new($lock); $writer.WriteLine("pid=$PID timestamp=$(Get-Date -Format o)"); $writer.Flush()

    $candidateDashboard = Join-Path ([IO.Path]::GetFullPath($CandidateRoot)) "dashboard"
    $manifestPath = Join-Path $candidateDashboard ".kdi-candidate-verified.json"
    if (-not (Test-Path -LiteralPath $manifestPath)) { throw "Candidate has no verification manifest." }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $commit = (git -C $CandidateRoot rev-parse HEAD).Trim()
    if ($manifest.commit -ne $commit -or $manifest.build -ne "PASS") { throw "Candidate verification does not match its Git commit." }
    if (git -C $CandidateRoot status --porcelain) { throw "Candidate worktree must be clean before deployment." }
    if (-not (Wait-Http "http://127.0.0.1:$($manifest.stagingPort)/api/health" @(200) 5)) { throw "Candidate staging server is not healthy." }

    $releaseId = "$($commit.Substring(0,7))-$timestamp"
    $release = Join-Path $releaseRoot $releaseId
    Log "deployment_started" @{ commit=$commit; candidate=$manifest.releaseId; previous="pending" }
    git -C $liveRoot worktree add --detach $release $commit
    if ($LASTEXITCODE -ne 0) { throw "Unable to create immutable release worktree." }
    $releaseDashboard = Join-Path $release "dashboard"
    Copy-Item -LiteralPath (Join-Path $liveRoot "dashboard\.env.local") -Destination (Join-Path $releaseDashboard ".env.local")
    Push-Location $releaseDashboard
    try {
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw "Release dependency installation failed." }
    } finally { Pop-Location }
    Copy-Item -LiteralPath (Join-Path $candidateDashboard ".next") -Destination (Join-Path $releaseDashboard ".next") -Recurse
    Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $releaseDashboard ".kdi-candidate-verified.json")

    $pointer = Join-Path $runtimeRoot "current-release.txt"
    $previousPointer = Join-Path $runtimeRoot "previous-release.txt"
    $previousDashboard = Join-Path $liveRoot "dashboard"
    if (Test-Path -LiteralPath $pointer) { $previousDashboard = (Get-Content -LiteralPath $pointer -Raw).Trim() }
    Set-Pointer $previousPointer $previousDashboard
    Log "release_prepared" @{ previous=$previousDashboard; candidate=$releaseDashboard; commit=$commit }

    Stop-ProductionCleanly "candidate_swap"
    Set-Pointer $pointer $releaseDashboard
    try {
        Start-ProductionAndWait "candidate_swap"
        if (-not (Wait-Http "http://127.0.0.1:3000/login" @(200) 10)) { throw "Production login failed." }
        if (-not (Wait-Http "http://127.0.0.1:3000/library" @(200,302,303,307,308) 10)) { throw "Production library failed." }
        if (-not (Wait-Http "http://127.0.0.1:3000/admin/users" @(200,302,303,307,308) 10)) { throw "Production admin/users failed." }
        Log "deployment_passed" @{ previous=$previousDashboard; candidate=$releaseDashboard; restart="PASS"; health="PASS"; rollback="NOT_REQUIRED" }
    } catch {
        Log "deployment_failed" @{ candidate=$releaseDashboard; reason="health_or_restart_failed"; rollback="STARTED" }
        Stop-ProductionCleanly "candidate_failed_before_rollback"
        Set-Pointer $pointer $previousDashboard
        Start-ProductionAndWait "automatic_rollback"
        if (-not (Wait-Http "http://127.0.0.1:3000/login" @(200) 40)) { throw "Deployment and automatic rollback both failed." }
        Log "rollback_passed" @{ restored=$previousDashboard; health="PASS" }
        throw "Candidate deployment failed; previous known-good release was restored."
    }
} finally {
    if($lock){$lock.Dispose()}
    Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
}
