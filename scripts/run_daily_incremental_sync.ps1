$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$LogRoot = Join-Path $ProjectRoot 'reports\step-14\logs'
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
if (-not (Test-Path -LiteralPath $Python)) { Write-Error 'Project Python environment not found'; exit 2 }
Set-Location -LiteralPath $ProjectRoot
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
& $Python -m scripts.run_incremental_sync sync --incremental --trigger scheduled *>> (Join-Path $LogRoot "scheduled-$Stamp.log")
exit $LASTEXITCODE
