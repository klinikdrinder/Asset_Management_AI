$ErrorActionPreference = "Stop"

$taskName = "KDI Media Library"
$launcher = Join-Path $PSScriptRoot "start-kdi-media-library.cmd"
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "Startup launcher is missing: $launcher"
}

$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\cmd.exe" -Argument "/d /c `"$launcher`"" -WorkingDirectory (Split-Path $launcher -Parent)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Days 3650) -Hidden
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Starts the KDI Media Library production server at user logon without VS Code." -Force | Out-Null
Write-Output "Scheduled task '$taskName' installed for $env:USERNAME."
Write-Output "Launcher: $launcher"
