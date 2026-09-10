Option Explicit
Dim shell, fileSystem, scriptPath, command, exitCode, logPath, logFile, launcherPid
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")
scriptPath = Replace(WScript.ScriptFullName, "start-kdi-media-library-hidden.vbs", "start-kdi-media-library-background.ps1")
logPath = fileSystem.BuildPath(fileSystem.GetParentFolderName(fileSystem.GetParentFolderName(WScript.ScriptFullName)), ".kdi-runtime\logs\kdi-background-runtime.log")
launcherPid = GetCurrentProcessId()
command = Chr(34) & shell.ExpandEnvironmentStrings("%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe") & Chr(34) & _
          " -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & scriptPath & Chr(34) & " -LauncherPid " & launcherPid
Do
    exitCode = shell.Run(command, 0, True)
    If exitCode = 0 Then WScript.Quit 0
    Set logFile = fileSystem.OpenTextFile(logPath, 8, True)
    logFile.WriteLine Year(Now) & "-" & Right("0" & Month(Now), 2) & "-" & Right("0" & Day(Now), 2) & _
        "T" & Right("0" & Hour(Now), 2) & ":" & Right("0" & Minute(Now), 2) & ":" & Right("0" & Second(Now), 2) & _
        " restart_attempt previous_exit_code=" & exitCode & " interval_seconds=60"
    logFile.Close
    WScript.Sleep 60000
Loop

Function GetCurrentProcessId()
    Dim processes, process
    Set processes = CreateObject("WbemScripting.SWbemLocator").ConnectServer(".", "root\cimv2").ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name='wscript.exe'")
    For Each process In processes
        If InStr(1, process.CommandLine, WScript.ScriptFullName, vbTextCompare) > 0 Then GetCurrentProcessId = process.ProcessId : Exit Function
    Next
    GetCurrentProcessId = 0
End Function
