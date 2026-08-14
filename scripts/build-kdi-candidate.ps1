[CmdletBinding()]
param(
    [string]$WorkspaceRoot,
    [int]$StagingPort = 3001
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [IO.Path]::GetFullPath((Join-Path $scriptRoot ".."))
if (-not $WorkspaceRoot) { $WorkspaceRoot = $repoRoot }
$WorkspaceRoot = [IO.Path]::GetFullPath($WorkspaceRoot)
$dashboard = Join-Path $WorkspaceRoot "dashboard"
$liveRoot = $repoRoot
if ($repoRoot -match '^(.*)[\\/]\.worktrees[\\/][^\\/]+$') { $liveRoot = $Matches[1] }
$runtimeRoot = Join-Path $liveRoot ".kdi-runtime"
$logRoot = Join-Path $runtimeRoot "logs"
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $logRoot "candidate-$timestamp.log"

function Write-DeploymentLog([string]$message) {
    $line = "[$(Get-Date -Format o)] $message"
    $line | Tee-Object -FilePath $logFile -Append
}

function Invoke-Checked([string]$label, [scriptblock]$command) {
    Write-DeploymentLog "$label START"
    & $command 2>&1 | Tee-Object -FilePath $logFile -Append
    if ($LASTEXITCODE -ne 0) { throw "$label failed with exit code $LASTEXITCODE" }
    Write-DeploymentLog "$label PASS"
}

$liveStatus = (Invoke-WebRequest -Uri "http://127.0.0.1:3000/login" -UseBasicParsing -TimeoutSec 10).StatusCode
if ($liveStatus -ne 200) { throw "Live /login is not healthy before candidate work." }
Write-DeploymentLog "LIVE_PRESERVED port=3000 status=$liveStatus"

$liveEnv = Join-Path $liveRoot "dashboard\.env.local"
$candidateEnv = Join-Path $dashboard ".env.local"
if (-not (Test-Path -LiteralPath $candidateEnv)) {
    if (-not (Test-Path -LiteralPath $liveEnv)) { throw "Candidate environment is unavailable." }
    Copy-Item -LiteralPath $liveEnv -Destination $candidateEnv
}

Push-Location $dashboard
try {
    Invoke-Checked "NPM_CI" { npm.cmd ci }
    Invoke-Checked "TYPECHECK" { npm.cmd run typecheck }
    Invoke-Checked "DASHBOARD_TESTS" { npm.cmd run unit }

    $python = Join-Path $liveRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) { throw "Python virtual environment is unavailable." }
    $oldPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = Join-Path $WorkspaceRoot "src"
    try { Invoke-Checked "PYTHON_TESTS" { & $python -m pytest (Join-Path $WorkspaceRoot "tests") -q } }
    finally { $env:PYTHONPATH = $oldPythonPath }

    Invoke-Checked "NEXT_BUILD" { npm.cmd run build }
    $commit = (git -C $WorkspaceRoot rev-parse HEAD).Trim()
    $releaseId = "candidate-$($commit.Substring(0,7))-$timestamp"
    $env:KDI_RELEASE_ID = $releaseId
    $stdout = Join-Path $logRoot "staging-$timestamp.out.log"
    $stderr = Join-Path $logRoot "staging-$timestamp.err.log"
    $process = Start-Process -FilePath "npm.cmd" -ArgumentList @("run","start:staging") -WorkingDirectory $dashboard -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Set-Content -LiteralPath (Join-Path $runtimeRoot "staging.pid") -Value $process.Id

    $healthy = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$StagingPort/api/health" -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) { $healthy = $true; break }
        } catch {}
    }
    if (-not $healthy) { throw "Candidate did not become healthy on staging port $StagingPort." }
    foreach ($route in @("/login", "/library", "/admin")) {
        $status = [int](curl.exe -s -o NUL -w "%{http_code}" --max-redirs 0 --connect-timeout 10 "http://127.0.0.1:$StagingPort$route")
        if ($status -notin @(200, 302, 303, 307, 308)) { throw "Staging smoke test failed for $route (HTTP $status)." }
    }
    Write-DeploymentLog "STAGING_SMOKE PASS port=$StagingPort"

    $env:KDI_BASE_URL = "http://127.0.0.1:$StagingPort"
    $acceptance = (& npm.cmd exec -- tsx scripts/runtime-acceptance.ts 2>&1 | Tee-Object -FilePath $logFile -Append) -join "`n"
    if ($LASTEXITCODE -ne 0 -or $acceptance -match '"FAIL"') { throw "Runtime acceptance failed." }
    Write-DeploymentLog "RUNTIME_ACCEPTANCE PASS"

    $manifest = [ordered]@{
        verifiedAt = (Get-Date).ToUniversalTime().ToString("o")
        commit = $commit
        releaseId = $releaseId
        build = "PASS"
        typecheck = "PASS"
        dashboardTests = "PASS"
        pythonTests = "PASS"
        runtimeAcceptance = "PASS"
        stagingPort = $StagingPort
    }
    $manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dashboard ".kdi-candidate-verified.json")
    Write-DeploymentLog "CANDIDATE_VERIFIED release=$releaseId commit=$commit"
    Write-Output "Candidate dashboard: $dashboard"
    Write-Output "Staging URL: http://127.0.0.1:$StagingPort"
} finally {
    Pop-Location
}
