# Search eval harness (P5)

Measures retrieval relevance of the canonical search against a gold set.

## Pieces
- `dashboard/db/eval-metrics.ts` — pure metrics: P@k, R@k, MRR, MAP, nDCG@k, hit-rate. Unit-tested in `dashboard/tests/eval-metrics.test.ts` (part of `npm run unit`).
- `dashboard/scripts/eval-generate-gold.ts` — builds `gold-set.json` (weak labels) from the live structured data.
- `dashboard/scripts/eval-run.ts` — runs each gold query through `executeCanonicalSearch`, scores it, and writes `eval-report.{json,md}`.

## Gold set
`gold-set.json` is **weak-labelled**: for each genuine canonical concept code that is OBSERVED on
3–80 assets, the relevant set is those assets and the query is the concept's name. It is derived
from the same assertions the search indexes, so it is best for **regression tracking and channel
comparison**, not an absolute quality bar. Add human-curated cases in `gold-set.curated.json`
(same shape: `{id, query, relevantAssetIds[], note?, source}`) — they are merged in on regeneration.

## Run
From `dashboard/`:

```
# regenerate the weak gold set (read-only)
cross-env NODE_OPTIONS=--conditions=react-server tsx scripts/eval-generate-gold.ts

# score it (needs the embedding sidecar running with models + an authorising admin user)
cross-env NODE_OPTIONS=--conditions=react-server tsx scripts/eval-run.ts --user=<app_user_uuid>
```

## Caveats
- The runner needs the embedding sidecar (`EMBED_SERVICE_URL`) with e5 + OpenCLIP loaded; without it every case errors.
- Retrieval is **ACL-bounded**: until the `is_clinical` backfill runs, only ~30 assets are visible, so recall is capped. The report prints this caveat. Run as an admin who `can_view_clinical` for the widest coverage.
