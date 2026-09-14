[CmdletBinding()]
param([string]$TaskName = "KDI Media Library")
$ErrorActionPreference = "Stop"
$liveRoot = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) ".."))
$runtimeRoot = Join-Path $liveRoot ".kdi-runtime"
$pointer = Join-Path $runtimeRoot "current-release.txt"
$previous = Join-Path $runtimeRoot "previous-release.txt"
$statePath = Join-Path $runtimeRoot "production-runtime.json"
$lockPath = Join-Path $runtimeRoot "deploy.lock"
$lock = $null
function Test-MutexFree { $m=[Threading.Mutex]::new($false,'Local\KDI.MediaLibrary.Production.3000');try{$free=$m.WaitOne(0);if($free){$m.ReleaseMutex()};return $free}finally{$m.Dispose()} }
function Get-VerifiedRuntime {
    if(-not (Test-Path -LiteralPath $statePath)){return @()}
    $state=Get-Content -LiteralPath $statePath -Raw|ConvertFrom-Json; $result=@()
    $supervisor=Get-CimInstance Win32_Process -Filter "ProcessId=$($state.supervisorPid)" -ErrorAction SilentlyContinue
    if($supervisor){if($supervisor.Name -ne 'powershell.exe' -or $supervisor.CommandLine -notmatch [regex]::Escape((Join-Path $liveRoot 'scripts\start-kdi-media-library-background.ps1'))){throw 'Unverified runtime supervisor.'};$result+=$supervisor}
    $child=$null
    if ([int]$state.childPid -gt 0) {
        $child=Get-CimInstance Win32_Process -Filter "ProcessId=$($state.childPid)" -ErrorAction SilentlyContinue
    }
    if($child){if($child.Name -ne 'node.exe' -or [int]$child.ParentProcessId -ne [int]$state.supervisorPid){throw 'Unverified runtime child.'};$expectedCli=Join-Path $state.release 'node_modules\next\dist\bin\next';if($child.CommandLine -and ($child.CommandLine -notmatch [regex]::Escape($expectedCli) -or $child.CommandLine -notmatch 'start.*127\.0\.0\.1.*3000')){throw 'Runtime child command line does not match the recorded KDI release.'};if($child.CommandLine){$result+=$child}}
    return @($result)
}
function Stop-Cleanly {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    $deadline=(Get-Date).AddSeconds(30)
    do{$runtime=@(Get-VerifiedRuntime);$port=@(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue);$free=Test-MutexFree;if(-not $runtime -and -not $port -and $free){return};Start-Sleep -Milliseconds 500}while((Get-Date)-lt $deadline)
    $supervisor=@($runtime|Where-Object Name -eq 'powershell.exe'|Select-Object -First 1)
    if($supervisor){Write-Output "Rollback terminating verified KDI supervisor PID $($supervisor.ProcessId) and descendants.";taskkill.exe /PID $supervisor.ProcessId /T /F|Out-Null}
    $deadline=(Get-Date).AddSeconds(15)
    do{$runtime=@(Get-VerifiedRuntime);$port=@(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue);$free=Test-MutexFree;if(-not $runtime -and -not $port -and $free){return};Start-Sleep -Milliseconds 250}while((Get-Date)-lt $deadline)
    throw 'Rollback blocked: KDI process tree, port, or mutex did not release.'
}
function Start-And-Wait {
    if(-not (Test-MutexFree)){throw 'Rollback blocked: mutex is owned.'};if(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue){throw 'Rollback blocked: port 3000 is occupied.'}
    Start-ScheduledTask -TaskName $TaskName
    for($i=0;$i -lt 240;$i++){try{$code=[int](curl.exe -s -o NUL -w '%{http_code}' --max-redirs 0 --connect-timeout 2 http://127.0.0.1:3000/api/health)}catch{$code=0};if($code -eq 200){return};Start-Sleep -Milliseconds 500}
    throw 'Rollback target did not become healthy within 120 seconds.'
}
function Set-Atomic([string]$path,[string]$value){$temp="$path.$PID.tmp";Set-Content -LiteralPath $temp -Value $value -NoNewline;Move-Item -LiteralPath $temp -Destination $path -Force}
try {
    try{$lock=[IO.File]::Open($lockPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)}catch{throw 'Another KDI deployment is already running.'}
    if(-not(Test-Path -LiteralPath $previous)){throw 'No previous known-good release is recorded.'}
    $current=(Get-Content -LiteralPath $pointer -Raw).Trim();$target=(Get-Content -LiteralPath $previous -Raw).Trim()
    if(-not(Test-Path -LiteralPath (Join-Path $target '.next\BUILD_ID'))){throw 'Previous build is unavailable.'}
    Stop-Cleanly
    Set-Atomic $pointer $target;Set-Atomic $previous $current
    Start-And-Wait
    foreach($check in @(@('login',200),@('library',307),@('admin/users',307))){$status=[int](curl.exe -s -o NUL -w '%{http_code}' --max-redirs 0 "http://127.0.0.1:3000/$($check[0])");if($status -ne $check[1] -and $status -ne 200){throw "Rollback route check failed: $($check[0]) status=$status"}}
    Write-Output "Rollback PASS: $target"
} finally {if($lock){$lock.Dispose()};Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue}
