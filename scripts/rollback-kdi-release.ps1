[CmdletBinding()]
param([string]$TaskName = "KDI Media Library")
$ErrorActionPreference = "Stop"
$liveRoot = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) ".."))
$runtimeRoot = Join-Path $liveRoot ".kdi-runtime"
$pointer = Join-Path $runtimeRoot "current-release.txt"
$previous = Join-Path $runtimeRoot "previous-release.txt"
$lockPath = Join-Path $runtimeRoot "deploy.lock"
$lock = $null
try {
    try { $lock=[IO.File]::Open($lockPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None) } catch { throw "Another KDI deployment is already running." }
    if(-not (Test-Path -LiteralPath $previous)){throw "No previous known-good release is recorded."}
    $current=(Get-Content -LiteralPath $pointer -Raw).Trim()
    $target=(Get-Content -LiteralPath $previous -Raw).Trim()
    if(-not (Test-Path -LiteralPath (Join-Path $target ".next\BUILD_ID"))){throw "Previous build is unavailable."}
    Set-Content -LiteralPath $pointer -Value $target -NoNewline
    Set-Content -LiteralPath $previous -Value $current -NoNewline
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Start-ScheduledTask -TaskName $TaskName
    for($i=0;$i -lt 40;$i++){try{if((Invoke-WebRequest http://127.0.0.1:3000/login -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200){Write-Output "Rollback PASS: $target";exit 0}}catch{};Start-Sleep -Seconds 1}
    throw "Rollback target did not become healthy."
} finally { if($lock){$lock.Dispose()}; Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue }
