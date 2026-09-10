# C: to D: runtime migration

- Scheduled Task `KDI Media Library`: Running.
- Executable: `C:\WINDOWS\System32\wscript.exe` (system executable).
- Arguments: `//B //Nologo "D:\Asset_Management_AI\scripts\start-kdi-media-library-hidden.vbs"`.
- Working directory: `D:\Asset_Management_AI\scripts`.
- Trigger: user logon for `DESKTOP-LE6PL64\Acer`.
- Principal: Acer, Interactive, Limited.
- Reliability settings retained: hidden, IgnoreNew, StartWhenAvailable, restart 10 times at one-minute intervals, long execution limit.
- Production supervisor PID 14012 and Node child PID 13668 run D:-based commands.
- Active release: `D:\Asset_Management_AI\.worktrees\storage_migration_candidate\dashboard`.
- Runtime health record phase: `healthy`.
- `.kdi-runtime`, releases, logs, pointers and rollback release set remain on D:.
- `.worktrees/staging` and all other retained worktrees resolve under D:.
- No D: release-retention cleanup was performed.
