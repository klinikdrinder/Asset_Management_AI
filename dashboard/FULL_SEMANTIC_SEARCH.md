# Full Semantic Search Architecture

KDI Master Google Drive remains the media source. A CPU-only OpenCLIP worker temporarily downloads one image or video, embeds an image or three representative video frames, removes the job directory, and atomically stores one normalized 512-dimensional vector in Supabase pgvector. Website queries use the same OpenCLIP text encoder over `127.0.0.1`; PostgreSQL performs cosine search and fuses visual (65%), existing Qwen (15%), structured/text (15%), and filename (5%) signals. Existing Qwen vectors and reviewed metadata remain separate and unchanged.

Run these commands in `C:\Users\Public\Asset_Management_AI\dashboard` using Windows PowerShell:

```powershell
..\.venv\Scripts\python.exe -m pip install open_clip_torch fastapi uvicorn
npm run visual:test-model
npm run visual:service
npm run visual:queue
npm run visual:one
npm run visual:run
npm run visual:status
npm run visual:retry
npm run visual:reconcile
npm run visual:benchmark
npm run dev
```

The embedding service and worker are independent of Next.js. The service binds only to loopback. After historical completion, the existing 21:00 incremental sync creates/reuses canonical assets; the database trigger queues only new model/fingerprint identities. Unchanged assets conflict on their unique identity and are not re-indexed.

Media is processed in isolated `%TEMP%\kdi_semantic_visual\<job-id>` directories. Each directory is removed on success or failure, and abandoned directories older than 24 hours are removed at startup. Source files are never changed or deleted.
