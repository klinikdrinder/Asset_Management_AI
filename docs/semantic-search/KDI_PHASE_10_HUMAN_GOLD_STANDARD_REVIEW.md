# KDI Phase 10 Human Gold-Standard Review

## Current status

`AWAITING_HUMAN_REVIEW`. Ten review packets exist, but no layer decision, P1 resolution, asset sign-off, gold package, or gold manifest has been created. Automated preparation is not human approval.

## Open the reviewer

From `dashboard`, start the internal application with both the existing local media preview gate and the dedicated gold-review gate enabled:

```powershell
$env:KDI_LIBRARY_DEV_BYPASS='true'
$env:KDI_LOCAL_SEMANTIC_REVIEW='true'
npm run dev
```

Open `/dev/gold-review`. The route and API return 404 in production or when the dedicated flag is absent.

## Review procedure

1. Confirm the displayed filename, asset ID, media type, and source fingerprint.
2. Inspect the actual image or play and scrub the entire video. Scene markers jump to proposed boundaries; they do not constitute approval.
3. Review each of the 18 layers. Choose `APPROVE_AS_IS`, `CORRECT`, `REJECT`, `CONFIRM_UNKNOWN`, or `NOT_APPLICABLE`. Corrections and rejections require reasons; corrections require a human value.
4. Review video temporal structure, transcript/audio, OCR, and narrative/search-summary sections separately. Images have transcript/audio marked not applicable.
5. Resolve every displayed P0/P1 item explicitly. IMG_1238 requires a one-scene versus multi-scene decision after full playback. Both images require action and treatment decisions based on the actual image.
6. Use `CONFIRM_UNKNOWN` when the media genuinely cannot establish a value. Do not force treatment, anatomy, role, transcript, or OCR certainty.
7. Click `SIGN OFF AS GOLD` only after the reviewer has completed the asset. Sign-off is blocked until 18 decisions, all applicable section reviews, and every P0/P1 resolution exist.

## Evidence and corrections

Draft packets retain the Phase 5 AI original, evidence, Phase 8 narrative, Phase 9 results, transcript/OCR evidence, scenes, events, and source fingerprint. Each saved human revision appends the previous decision to history. It does not modify Phase 3–9 artifacts.

Gold correction precedence is locked as:

```text
HUMAN GOLD OVERRIDE
> APPROVED AI SEMANTIC FACT
> UNVERIFIED AI FACT
> LEGACY SEARCH DOCUMENT
```

Future AI suggestions must be stored separately and cannot replace signed-off gold values automatically.

## Gold output and change control

Explicit asset sign-off creates `reports/semantic-search/phase10/gold/<asset_id>_gold_standard.json` with its SHA-256 fingerprint. Signed-off data is immutable by default. Later corrections require a new review revision and reason; benchmark-wide material changes require a new gold-standard version rather than silent mutation.

The combined `kdi_gold_pilot_v1_manifest.json` must not be created until all ten assets have genuine human sign-off. Phase 11 remains blocked until then.
