# Job 3 provenance standard

The following constrained terms are shared by the new intelligence tables:

| Value | Meaning |
|---|---|
| `AI_VISUAL` | Model inference from pixels/frames |
| `AI_MULTIMODAL` | Model inference combining media modalities |
| `AI_AUDIO` | Model inference from audio other than a stored transcript |
| `TRANSCRIPT` | Derived from spoken-language transcript |
| `OCR` | Derived from detected on-frame text |
| `SOURCE_METADATA` | Supplied by source-system metadata |
| `VERIFIED_FILENAME` | Human-verified filename evidence |
| `VERIFIED_FOLDER` | Human-verified folder evidence |
| `HUMAN_REVIEW` | Reviewed or entered by an authorized person |
| `CLINICIAN_VERIFIED` | Verified by an authorized clinician |

Provenance states evidence origin, not truth. `clinical_observations.source_type` uses the same vocabulary and independently records `verification_status`. AI-visible observations may remain `AI_SUGGESTED`; only authorized review can mark clinical claims verified. Emotional, premium, and marketing interpretations remain interpretations with provenance, never literal facts.

Every AI-capable Job 3 table has a nullable FK to `ai_analysis_runs`; nullable supports manual/verified records. No patient identity inference, biometric reference, diagnosis seed, or media inference was added.
