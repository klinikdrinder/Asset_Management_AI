[CmdletBinding()]
param([switch]$DryRun)
$ErrorActionPreference = 'Stop'
# Portable project root: derived from this script's own location (scripts\ ->
# repository root) so the task works for any clone location on any machine.
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$root = Split-Path -Parent $scriptDir
$python = Join-Path $root '.venv\Scripts\python.exe'
$logRoot = Join-Path $root 'reports\semantic-search\rollout\phase-04\scheduler-logs'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$log = Join-Path $logRoot "repository-maintenance-$stamp.log"
$started = [DateTime]::UtcNow.ToString('o')
try {
  if (-not (Test-Path -LiteralPath $python)) { throw "Python runtime missing: $python" }
  Set-Location -LiteralPath $root
  Add-Content -LiteralPath $log -Value "run_started=$started dry_run=$($DryRun.IsPresent) working_directory=$root"
  $syncArgs = @('scripts\run_incremental_sync.py','sync','--incremental','--trigger','scheduled')
  if ($DryRun) { $syncArgs += '--dry-run' }
  & $python @syncArgs *>> $log
  $syncExit = $LASTEXITCODE
  if ($syncExit -ne 0) { throw "source_sync_failed exit=$syncExit" }
  Push-Location (Join-Path $root 'dashboard')
  try { & (Join-Path $root 'dashboard\node_modules\.bin\tsx.cmd') 'scripts\library-reconciliation.ts' *>> $log } finally { Pop-Location }
  $masterExit = $LASTEXITCODE
  if ($masterExit -ne 0) { throw "master_reconciliation_failed exit=$masterExit" }
  Add-Content -LiteralPath $log -Value "source_sync=PASS master_reconciliation=PASS completed_at=$([DateTime]::UtcNow.ToString('o')) exit_status=0"
  exit 0
} catch {
  $message = $_.Exception.Message
  $category = if ($message -match 'OAuth|token|refresh|invalid_grant') { 'SOURCE_SYNC_AUTH_FAILURE' } elseif ($message -match 'Connection|network|DNS|443') { 'SOURCE_SYNC_NETWORK_FAILURE' } elseif ($message -match 'master_reconciliation') { 'MASTER_RECONCILIATION_FAILURE' } elseif ($message -match 'lock') { 'LOCK_FAILURE' } else { 'CONFIGURATION_FAILURE' }
  Add-Content -LiteralPath $log -Value "status=FAILED category=$category error=$message completed_at=$([DateTime]::UtcNow.ToString('o')) exit_status=1"
  exit 1
}
