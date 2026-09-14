# Search eval report

Cases: 35 · k=20 · user 3938c364-0250-40a1-8db6-9ef704ca0122 · mode PRE_AUTH_RETRIEVAL

> mode=AUTHORIZED is ACL-bounded (is_clinical=NULL hidden from everyone incl. super-admin) — recall is capped until the backfill runs. mode=PRE_AUTH_RETRIEVAL scores the engine before the ACL gate.
> Structured channel contributed to 25/35 queries.

| Metric | Value |
|---|---|
| Mean P@5 | 74.3% |
| Mean R@10 | 85.5% |
| MRR | 0.872 |
| MAP | 0.806 |
| Mean nDCG@10 | 0.835 |
| Hit-rate@10 | 97.1% |

## Per-channel attribution (relevant hits touched)

- STRUCTURED_CANONICAL: 365
- FULL_TEXT: 294
- TEXT_EVENT: 198
- EXPANDED_STRUCTURED: 56
- TEXT_TRANSCRIPT: 10
- TEXT_OCR: 4

## Per-channel query contribution (queries where the channel appeared at all)

- FULL_TEXT: 35
- TEXT_EVENT: 32
- STRUCTURED_CANONICAL: 25
- TEXT_TRANSCRIPT: 7
- TEXT_OCR: 7
- EXPANDED_STRUCTURED: 7

## Per-query

| Query | Rel | Ret | P@5 | R@10 | RR | nDCG@10 | Hit |
|---|--:|--:|--:|--:|--:|--:|:--:|
| audio stream present | 17 | 48 | 60.0% | 47.1% | 1.00 | 0.75 | ✓ |
| person or body part visible | 16 | 44 | 80.0% | 50.0% | 0.50 | 0.71 | ✓ |
| exposed body region visible | 11 | 44 | 80.0% | 45.5% | 0.50 | 0.49 | ✓ |
| adult presentation | 10 | 42 | 100.0% | 100.0% | 1.00 | 1.00 | ✓ |
| asset identity | 10 | 48 | 60.0% | 70.0% | 1.00 | 0.69 | ✓ |
| current search representation | 10 | 19 | 100.0% | 100.0% | 1.00 | 1.00 | ✓ |
| media summary | 10 | 14 | 100.0% | 90.0% | 1.00 | 0.93 | ✓ |
| provisional asset narrative | 10 | 42 | 100.0% | 100.0% | 1.00 | 1.00 | ✓ |
| handheld instrument and protective gloves visible | 9 | 50 | 20.0% | 55.6% | 0.20 | 0.39 | ✓ |
| physical contact holding or manipulation visible | 8 | 27 | 100.0% | 100.0% | 1.00 | 1.00 | ✓ |
| timeline structure | 8 | 8 | 100.0% | 100.0% | 1.00 | 1.00 | ✓ |
| vertical | 8 | 40 | 80.0% | 50.0% | 1.00 | 0.59 | ✓ |
| clinician treats patient | 7 | 42 | 100.0% | 100.0% | 1.00 | 1.00 | ✓ |
| clinician | 7 | 45 | 100.0% | 100.0% | 1.00 | 1.00 | ✓ |
| patient | 7 | 47 | 100.0% | 100.0% | 1.00 | 1.00 | ✓ |
| patient reclining | 7 | 47 | 100.0% | 100.0% | 1.00 | 1.00 | ✓ |
| clinical reference | 7 | 35 | 100.0% | 100.0% | 1.00 | 1.00 | ✓ |
| clinician works on anatomy | 7 | 35 | 100.0% | 100.0% | 1.00 | 1.00 | ✓ |
| handheld | 6 | 46 | 0.0% | 0.0% | 0.00 | 0.00 | · |
| Treatment Room | 6 | 35 | 100.0% | 100.0% | 1.00 | 1.00 | ✓ |
| patient positioned in treatment chair | 6 | 35 | 100.0% | 100.0% | 1.00 | 1.00 | ✓ |
| procedure content | 5 | 36 | 80.0% | 100.0% | 1.00 | 0.95 | ✓ |
| Face | 5 | 40 | 60.0% | 100.0% | 1.00 | 0.85 | ✓ |
| Touching | 4 | 26 | 80.0% | 100.0% | 1.00 | 0.90 | ✓ |
| clinician gloved | 4 | 47 | 60.0% | 100.0% | 0.50 | 0.75 | ✓ |
| Frontal Scalp | 4 | 52 | 80.0% | 100.0% | 1.00 | 0.98 | ✓ |
| medium closeup | 4 | 38 | 60.0% | 100.0% | 0.33 | 0.65 | ✓ |
| static | 4 | 40 | 40.0% | 50.0% | 1.00 | 0.56 | ✓ |
| Lower Face | 3 | 21 | 60.0% | 100.0% | 1.00 | 1.00 | ✓ |
| clinician masked | 3 | 47 | 40.0% | 100.0% | 1.00 | 0.82 | ✓ |
| person looks at camera | 3 | 39 | 20.0% | 33.3% | 1.00 | 0.47 | ✓ |
| front facing | 3 | 40 | 60.0% | 100.0% | 1.00 | 1.00 | ✓ |
| portrait content | 3 | 52 | 60.0% | 100.0% | 1.00 | 1.00 | ✓ |
| Scalp | 3 | 48 | 60.0% | 100.0% | 1.00 | 1.00 | ✓ |
| subject | 3 | 53 | 60.0% | 100.0% | 0.50 | 0.73 | ✓ |
