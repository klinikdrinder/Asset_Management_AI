# Dedicated local AI worker deployment

The worker uses Google Drive / KDI Master as permanent media authority and
Supabase as permanent job, metadata, and vector authority. Source media is
streamed into a disposable per-job directory and deleted after every outcome.
Do not configure a local KDI Master mirror.

## Readiness

From the repository with the worker environment loaded:

```text
python -m kdi_media.semantic_worker --preflight --benchmark-manifest data/semantic_local_automatic_pilot_20.json
```

The command performs no media retrieval and no AI inference. It prints `READY`
or `BLOCKED` with exact credential-free reasons. Apply
`supabase/migrations/202608130001_atomic_semantic_completion.sql` through the
approved Supabase SQL Editor workflow before expecting `READY`.

Copy `config/semantic-worker.env.example` to a protected location outside Git.
Restrict it to the service identity. Keep Ollama bound to `127.0.0.1:11434`.
The service account JSON must have read-only access to KDI Master. The Supabase
service-role key and Drive JSON must never be committed or placed in logs.

## Hardware

Minimum workable: 16 GB RAM, modern 6-core CPU, GPU optional, and at least
50 GB free processing disk. Recommended: 32 GB RAM, modern 8–12 core CPU,
NVIDIA GPU with approximately 12 GB VRAM, and at least 100 GB free processing
disk. Hardware procurement and provisioning remain manual owner decisions.

## Windows

Create a local non-interactive account such as `KDI_AI_Worker`; deny interactive
logon and grant only “Log on as a service”. Grant read/execute to the application,
read to its protected credential directory and Ollama models, and modify only
the worker temp/state directories. Install WinSW separately, place the supplied
XML beside the renamed WinSW executable, load the protected environment through
the service wrapper or machine-scoped service configuration, then install/start
only after preflight returns `READY`. Configure Ollama itself as loopback-only.
The wrapper starts automatically, restarts failures, and sends a graceful stop.
Startup invokes the worker's marked-directory orphan reconciliation.
Code-sign the supplied PowerShell launcher before using its `AllSigned` policy.

Do not install this service on the current workstation.

## Linux/systemd

Create system user/group `kdi-ai-worker` with no shell. Install the application
read-only under `/opt/kdi-asset-management`, credentials under
`/etc/kdi-semantic-worker` (`0750`, environment/JSON `0640`), state under
`/var/lib/kdi-semantic-worker`, and temporary media under `/var/tmp/kdi-local-ai`.
Copy the supplied unit to `/etc/systemd/system`, adjust paths, run `systemctl
daemon-reload`, enable it, and start only after its preflight succeeds. The unit
uses a restricted account, filesystem hardening, automatic restart, SIGTERM,
and a bounded graceful-stop interval. Bind Ollama only to loopback.

## Exact-20 staging pilot (prepare only)

Do not run until migration verification, dedicated-machine preflight, service
account permissions, and an operator review are complete:

```text
python -m kdi_media.semantic_worker --poll --benchmark-manifest data/semantic_local_automatic_pilot_20.json --staging-only --confirm-clinical-local-processing --concurrency 1
```

The nightly 9 PM sync remains disconnected. Full-library queue processing must
remain disabled until a later separately approved milestone.
