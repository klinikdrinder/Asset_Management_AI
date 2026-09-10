$ErrorActionPreference = 'Stop'
$taskName = 'KDI Repository Maintenance'
$root = 'D:\Asset_Management_AI'
$script = Join-Path $root 'scripts\run-repository-maintenance.ps1'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw "Entrypoint missing: $script" }
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$script`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At 9:00PM
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10) -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'KDI source synchronization and Master Repository reconciliation' -Force | Out-Null
Write-Output "installed=$taskName"
