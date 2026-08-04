# Step 11 Migration Dashboard

Built a secure, read-only operational dashboard in `dashboard/`.

## Start

From `dashboard`, install dependencies and run `npm run dev`.

Required environment names:

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `SUPABASE_DASHBOARD_ACCESS_TOKEN`

The access token must represent an authenticated Supabase user carrying the existing KDI reader/access claims. Service-role credentials are unsupported.

## Routes

- `/`
- `/source-folders`
- `/migration-results`
- `/exceptions`
- `/duplicates`
- `/system-status`

All routes require platform authentication. Queries are centralized server-side and expose no mutation operations, Drive credentials, hashes, raw paths, or raw filenames.

## Step 11 completion update (2026-08-03)

The authentication failure was an expired reader JWT. The configured public key is a legacy anon JWT for project `wcqqjpndlwsvatjuqnol`, not a publishable key. A fresh short-lived reader session was obtained through a supported server-side passwordless exchange and stored only in ignored `dashboard/.env.local`.

Restricted live reads reconcile 886 source files, 878 assets, 878 asset-source links, 878 verified destinations, eight exclusions, and zero failures, duplicate groups, duplicate destination identities, claims, or leases. All six built routes returned HTTP 200 with live data. Reader insert, update, and delete requests were denied; privileged mutation RPC access was unavailable. No RLS policy or production migration record was changed.

The production build, TypeScript, lint, 19 dashboard unit tests, 10 provisioning tests, route smoke tests, secret scan, and `git diff --check` passed. See `step_11_dashboard_completion_report.json`. The server-only access token remains intentionally short-lived and must be renewed or replaced by managed server-side session rotation before expiry.

Final verdict: `STEP_11_COMPLETE_READY_FOR_STEP_12`.
