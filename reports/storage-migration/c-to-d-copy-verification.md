# C: to D: copy verification

The initial resilient copy was performed 2026-08-19 with Robocopy, preserving data, attributes, timestamps, hidden files, `.git`, private environment files, directory structure, and using `/XJ` to avoid junction loops.

- Initial total: 863,172 files; 18.144 GiB.
- Initial files copied: 863,172.
- Initial failed files: 0.
- Initial failed directories: 12, limited to inaccessible pytest-cache directories.
- Follow-up sync: 5 newer controlled files copied; 0 failed files.
- Resumed dry run excluding stale Git/runtime/worktrees, dependencies/build output, bytecode and caches: one C:-only controlled file, `reports/step-14/logs/scheduled-20260819-214012.log` (664 bytes).
- That historical log was preserved on D: before source deletion.
- Critical files verified: `.git`, `.gitignore`, `.env`, `.env.local`, `dashboard/package.json`, `dashboard/package-lock.json`, `supabase/migrations`, `scripts`, `tests`, `reports`, `.kdi-runtime`, and `.worktrees`.
- `.env`, `.env.local`, package manifests, and launcher scripts compared equal between C: and D: at resumed audit.

Robocopy success codes were interpreted according to Robocopy semantics. The initial directory-cache failures did not omit required project files.
