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
function Restart-Production {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    for($i=0;$i -lt 6;$i++){ if(-not (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)){break}; Start-Sleep -Milliseconds 500 }
    $listeners = @(Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)
    foreach($listener in $listeners){
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
        if($process.Name -ne "node.exe" -or $process.CommandLine -notmatch 'next.*start'){
            throw "Port 3000 is occupied by a process that is not the KDI production server."
        }
        Stop-Process -Id $listener.OwningProcess -Force
    }
    for($i=0;$i -lt 20;$i++){ if(-not (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)){break}; Start-Sleep -Milliseconds 250 }
    if(Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue){throw "Production port 3000 did not stop cleanly."}
    Start-ScheduledTask -TaskName $TaskName
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

    Set-Pointer $pointer $releaseDashboard
    try {
        Restart-Production
        if (-not (Wait-Http "http://127.0.0.1:3000/api/health" @(200) 40)) { throw "Production health endpoint failed." }
        if (-not (Wait-Http "http://127.0.0.1:3000/login" @(200) 10)) { throw "Production login failed." }
        if (-not (Wait-Http "http://127.0.0.1:3000/library" @(200,302,303,307,308) 10)) { throw "Production library failed." }
        Log "deployment_passed" @{ previous=$previousDashboard; candidate=$releaseDashboard; restart="PASS"; health="PASS"; rollback="NOT_REQUIRED" }
    } catch {
        Log "deployment_failed" @{ candidate=$releaseDashboard; reason="health_or_restart_failed"; rollback="STARTED" }
        Set-Pointer $pointer $previousDashboard
        Restart-Production
        if (-not (Wait-Http "http://127.0.0.1:3000/login" @(200) 40)) { throw "Deployment and automatic rollback both failed." }
        Log "rollback_passed" @{ restored=$previousDashboard; health="PASS" }
        throw "Candidate deployment failed; previous known-good release was restored."
    }
} finally {
    if($lock){$lock.Dispose()}
    Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
}
