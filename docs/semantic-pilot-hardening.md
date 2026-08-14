# KDI semantic pilot technical hardening

## Execution tiers

- **Tier A — synthetic:** `scripts/test_ai_provider_connectivity.py`; no KDI media,
  catalogue read, or semantic write. Both live-confirmation switches are required.
- **Tier B — low-risk KDI:** `data/semantic_pilot_low_risk_manifest.json`; 17 locally
  screened clinic-interior/equipment videos. All remain unapproved. Execute requires
  `--manifest --approved-only --tier low-risk`.
- **Tier C — clinical/patient:** `data/semantic_pilot_manifest.json`; unchanged
  clinical-review manifest. Execute requires its own approved rows, `--tier clinical`,
  and `--confirm-clinical-external-processing`. A Tier B command cannot select it.

No tier falls through to another, and no missing-manifest bulk mode exists.

## Local media boundary

Original still images are decoded locally with Pillow, EXIF-oriented, converted to
RGB, bounded within 1600×1600 without upscaling, and encoded as quality-88 JPEG.
Input above 64 megapixels, corrupt data, and decompression-bomb warnings/errors are
rejected. Processing uses memory buffers; the original Drive object is untouched.

Video remains capped at six evenly spaced frames between 5% and 95% of duration.
Derived frames are at most 1600×1600 with preserved aspect ratio; temporary media
is removed by `TemporaryDirectory`.

## Local production runtime and retry policy

Production uses local Ollama on loopback only: `qwen3-vl:2b` for vision and
`qwen3-embedding:0.6b` for exactly 1024-dimensional embeddings. Models live at
`E:\KDI_Local_AI\models`. AI concurrency is one; vision and embedding execute
sequentially with `keep_alive: 0` so both models are never resident together.
Retryable timeouts/connections are mapped to `ProviderRetryableError`; permanent
request/dimension errors are not retried. The worker owns the single retry schedule:
1, 2, 4, 8, and 16 seconds, with jitter, then leaves the asset `FAILED_RETRYABLE`
and resumable. Completion is claim-owner guarded and unchanged indexed fingerprints
are skipped before media or provider access. The optional OpenAI adapter retains its
10-second connect and 30-second request timeout with SDK retries disabled.

## FFmpeg status

The stable Gyan.dev `ffmpeg-release-essentials.zip` was downloaded over HTTPS and
verified against its separately published SHA-256 before extraction. Expected and
actual SHA-256 were both
`e6b54767a6065919048f1a098eb27211ca4e12b4348a05d88777a5855d0b6e71`.
FFmpeg 9.0 is installed only in ignored project tooling at
`.tools/ffmpeg/bin`; no global install or PATH mutation is required.

Executable resolution is deterministic: an explicit `KDI_FFMPEG_PATH` or
`KDI_FFPROBE_PATH`, then the project-local runtime, then system PATH. A configured
but missing path fails closed rather than falling through. All 13 clinical-manifest
videos were read from their verified canonical destinations and locally decoded:
13 succeeded, 0 failed, and 78 JPEG frames were produced within 1600 x 1600. The
189.267-second video remained capped at six frames. Temporary cleanup passed and
the verification made no provider calls or database writes.

## Low-risk evaluation set

The expectations below reflect only visually screened assets in the Tier B manifest:

1. empty clinic interior
2. modern clinic waiting area
3. clinic corridor video
4. clinic reception area
5. treatment room without a patient
6. clinic furnishings and interior design
7. standalone treatment machine
8. close-up of treatment equipment controls
9. clinic machine screen and handpiece
10. equipment used in an aesthetics clinic
11. videos of the clinic interior
12. only videos
13. show the newest ones
14. equipment, not clinic rooms
15. clinic rooms, not treatment procedures
16. treatment machine (synonym test)
17. clinic device (short query)
18. clinik interior (intentional typo)
19. something similar but no patients
20. purple spaceship cooking noodles (nonsense control)

No doctor, patient, treatment name, or medical claim is assumed from a face or
filename. `doctor_name` remains null unless spoken/textual/trusted structured evidence
supports it.
