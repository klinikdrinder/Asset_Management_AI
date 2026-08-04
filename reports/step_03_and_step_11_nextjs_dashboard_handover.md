# Step 3 and Step 11 Handover

The repository now contains one integrated application in `dashboard/`. Step 3 was newly created because no existing Next.js app was present; Step 11 is implemented inside that same application.

## Commands

From `dashboard/`:

- Install: `npm install`
- Develop: `npm run dev`
- Test: `npm run unit`
- Type-check: `npm run typecheck`
- Lint: `npm run lint`
- Build: `npm run build`

## Environment variable names

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `SUPABASE_DASHBOARD_ACCESS_TOKEN`

The access token must belong to an authenticated Supabase user with the existing KDI reader/access claims. Never substitute the service-role key.

## Routes

- `/`
- `/source-folders`
- `/migration-results`
- `/exceptions`
- `/duplicates`
- `/system-status`

## Security

All routes require platform authentication. Supabase queries are centralized server-side and read-only. The UI never receives raw filenames, source paths, full hashes, Drive links, Google credentials, or privileged database credentials.

## Verification

Repository evidence confirms 886 source files, 878 canonical assets, 878 verified destinations, eight exclusions, and zero failures. Live RLS-backed dashboard verification is pending because a dashboard-safe anon key and authorized reader JWT are not configured.

Recommended Step 12 starting point: provision the restricted Supabase reader identity and runtime variables, verify live pagination and aggregates, then publish behind workspace-restricted access.

## Reader provisioning required

The sanitized Supabase Auth directory check found no existing users. Live verification therefore stopped without creating an ad hoc identity.

An approved administrator must:

1. Approve the dashboard reader email/identity and secure credential-delivery method.
2. Create the user through the approved Supabase Auth administration workflow.
3. Assign existing `app_metadata` claims `kdi_media_reader: "true"` and `kdi_media_access: true`.
4. Configure `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and a temporary server-only `SUPABASE_DASHBOARD_ACCESS_TOKEN`.

The token is suitable only for temporary server-side verification. Permanent production operation should exchange an authenticated user session rather than rely on a static JWT. No reader was created, no RLS policy changed, no production query was issued by the dashboard, and no secret entered source, reports, HTML, or client bundles.

### Prepared provisioning utility

`scripts/provision_dashboard_reader.py` is an administrative utility, not dashboard runtime code. It requires explicit authorization, accepts the password and anon key through hidden prompts, reuses an existing matching user, rejects duplicates, assigns only the two KDI claims, verifies their exact types, and prints no credentials or tokens.

From the repository root, an authorized operator may run:

```powershell
$env:PYTHONPATH='src;.'
.\.venv\Scripts\python.exe scripts\provision_dashboard_reader.py `
  --email kdimediaautomation@gmail.com `
  --authorize-administration `
  --email-confirmed `
  --configure-dashboard-env
```

Use `--email-confirmed` only after explicitly approving administrative confirmation for this mailbox. The command securely prompts for the reader password and public anon/publishable key. It uses the already-secured administrative environment credential without printing it, obtains a short-lived reader session, and writes only to ignored `dashboard/.env.local`.
