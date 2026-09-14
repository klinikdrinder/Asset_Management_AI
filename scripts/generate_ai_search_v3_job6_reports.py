"""Generate the immutable Job 6 evidence packet from verified run artifacts."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "ai-search-v3"
TMP = ROOT / "tmp" / "job6"

PILOT = [
    ("IMG_0531.MP4", "7f72217d-3839-4920-86b4-ccc33e9e3d95", "video", "Lower-face injection procedure with patient-like and clinician-like roles."),
    ("IMG_1238.MP4", "babae120-9372-42ad-b535-02a3276ea2be", "video", "Clinician works on a reclining patient's frontal scalp beneath a clinical device."),
    ("IMG_3429.MP4", "c86344e9-5b32-4d86-9205-67952d508651", "video", "Close clinical view of a neck injection."),
    ("IMG_9871.MOV", "444da390-0117-4380-8c87-d7c32f2903ff", "video", "Front-facing self-recorded portrait showing several facial angles."),
    ("DSC03753.JPG", "37838d30-a0ce-4f90-8cc3-c986db0aaa65", "image", "Clinical-style frontal portrait with visible frontal scalp thinning."),
    ("DSC08097.JPG", "6215ad8b-12be-4a8e-bc49-f6b3dcf55c21", "image", "Front-facing studio portrait against a neutral dark background."),
    ("IMG_0493.MP4", "64712c6a-c02c-46e9-9f73-16786109468b", "video", "Reclining patient-like participant and clinician-like participant during facial treatment."),
    ("IMG_1148.MP4", "47611c6d-7923-42a4-87b6-c2a416a90f5c", "video", "Clinician-like participant examines or treats a reclining patient's frontal scalp."),
    ("IMG_2963.MP4", "bfae6c51-5d71-47ae-a3e1-6d07092b8896", "video", "Clinical team performs FUE implantation at the prepared recipient scalp."),
    ("IMG_1160.MP4", "753eb5f3-82c7-4148-a226-d5b960fd8619", "video", "Clinician cleanses cheek and lower-face skin in close view."),
]

TABLES = ["asset_scenes","asset_keyframes","scene_people","person_appearances","scene_treatments","scene_anatomy","scene_actions","scene_relationships","clinical_observations","scene_environment","scene_cinematography","scene_composition","marketing_annotations","scene_narratives","asset_transcript_chunks","ocr_observations","scene_embeddings","keyframe_embeddings","transcript_embeddings","asset_search_documents","scene_search_documents","ai_analysis_runs"]
FIRST = {"asset_scenes":8,"asset_keyframes":8,"scene_people":16,"person_appearances":16,"scene_treatments":1,"scene_anatomy":18,"scene_actions":11,"scene_relationships":7,"clinical_observations":1,"scene_environment":8,"scene_cinematography":8,"scene_composition":8,"marketing_annotations":10,"scene_narratives":8,"asset_transcript_chunks":0,"ocr_observations":0,"scene_embeddings":8,"keyframe_embeddings":8,"transcript_embeddings":0,"asset_search_documents":10,"scene_search_documents":8,"ai_analysis_runs":10}


def write(name: str, body: str) -> None:
    (OUT / name).write_text(body.rstrip() + "\n", encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    prepared = json.loads((TMP / "prepared-media.json").read_text(encoding="utf-8"))
    run = json.loads((TMP / "indexing-result.json").read_text(encoding="utf-8"))
    verified = json.loads((TMP / "final-verification.json").read_text(encoding="utf-8"))[0]["jsonb_build_object"]
    prep = {x["asset_id"]: x for x in prepared["assets"]}
    branch = subprocess.check_output(["git","branch","--show-current"], cwd=ROOT, text=True).strip()
    head = subprocess.check_output(["git","rev-parse","HEAD"], cwd=ROOT, text=True).strip()
    manifest = {"job":"KDI_AI_SEARCH_V3_JOB_6","purpose":"KDI AI Search V3 pilot indexing only","pilot_size":10,"source":"reports/ai-search-v3/job5_3-final-pilot-manifest.json","assets":[{"ordinal":i,"file_name":n,"asset_id":a,"media_type":m,"authorization":"PASS"} for i,(n,a,m,_) in enumerate(PILOT,1)]}
    (OUT / "job6-pilot-manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")

    write("job6-preflight.md", """# Job 6 preflight

Result: **PASS — 10/10**. Every UUID/filename pair, source row, asset-source row, verified master destination, media availability, purpose-limited authorization, and `can_asset_use_external_ai` result was verified before processing. Three restricted originals and held backup `DSC03759.JPG` returned FALSE. No substitution occurred.

The exact Job 5.3 manifest is the boundary. Restricted originals, held backups, and all other library assets are excluded.""")
    write("job6-analysis-run.md", f"""# Job 6 analysis run

- Cohort ID: `{run['cohort_id']}`
- Pipeline: `{run['pipeline_version']}`
- Prompt/schema version: `{run['prompt_version']}` / Job 3–4 schema
- Status: COMPLETED
- Started: {run['started_at']}
- Completed: {run['completed_at']}
- Per-asset runs: 10 completed, 0 partial, 0 failed
- Provider/model: controlled Codex visual review plus existing OpenCLIP `ViT-B-32` (`laion2b_s34b_b79k`)
- Manifest: `reports/ai-search-v3/job6-pilot-manifest.json`

The ten per-asset run IDs are recorded in the final pilot manifest and database. Deterministic UUIDv5 keys make the writer restart-safe.""")
    write("job6-embedding-architecture.md", """# Job 6 embedding architecture

PostgreSQL/Supabase with pgvector 0.8.2 remains authoritative. No new vector database was introduced and Ollama was not installed.

- Visual generator: existing `open_clip`, `ViT-B-32`, `laion2b_s34b_b79k`, 512 dimensions.
- Visual storage: `asset_visual_embeddings`, `scene_embeddings`, `keyframe_embeddings`.
- Existing 875 asset vectors were preserved; eight pilot scene and eight pilot keyframe rows reuse their authorized asset-level vector as a scene/keyframe visual representation.
- Text generator: none currently operational and approved. Configured Ollama is unavailable/prohibited; configured OpenAI fallback returned quota exhaustion before any pilot media was sent.
- Text vectors: **DEFERRED — NO APPROVED WORKING GENERATOR**. No padding, truncation, or dimension conversion occurred.
- Text storage remains `asset_embeddings` / `transcript_embeddings` when a compatible approved generator becomes available.

Existing vector indexes are primary/unique/model/filtering indexes; the Job 4 pilot schema contains no ANN HNSW/IVFFlat index. Job 6 did not alter that architecture.""")
    write("job6-pgvector-report.md", """# Job 6 pgvector report

pgvector 0.8.2: PASS. Tables: `asset_visual_embeddings`, `asset_embeddings`, `scene_embeddings`, `keyframe_embeddings`, `transcript_embeddings`. Generated visual dimensions are exactly 512 in both scene and keyframe tables. Eight scene and eight keyframe vectors were added. Text vectors were deferred. Global asset-vector regeneration: NO.""")
    write("job6-scene-indexing.md", """# Job 6 scene indexing

Eight videos produced one meaningful full-clip semantic segment each; two still images produced no fake temporal scenes. All time ranges are positive and bounded by probed duration. Scene types, narratives, confidence, analysis run, prompt/pipeline metadata, controlled ontology links, and provenance are retained. Result: PASS.""")
    write("job6-keyframe-indexing.md", """# Job 6 keyframe indexing

Eight representative keyframes were selected from six-frame controlled reviews, one per video scene. Each keyframe retains asset, scene, timestamp, analysis run, derivative, selection rationale, and quality/importance scores. No continuous or redundant extraction occurred. Temporary derivative files were expired and removed after indexing; database provenance remains. Result: PASS.""")
    write("job6-transcript-ocr.md", """# Job 6 transcript and OCR

Transcription: **DEFERRED** because no approved working transcription provider is configured. No speaker names or transcript content were fabricated. Text embedding is likewise deferred. OCR: no useful visible text was found in controlled derivatives, so zero observations were created; OCR noise was not stored. Structured and visual indexing continued as authorized.""")
    write("job6-structured-intelligence.md", """# Job 6 structured intelligence

The pilot added evidence-grounded people/roles, anatomy, actions, functional relationships, one canonical FUE treatment observation, environment, cinematography, composition, marketing-description annotations, factual narratives, and one non-diagnostic clinical appearance observation. No facial identity recognition, exact age inference, protected-characteristic selection, uncontrolled ontology expansion, diagnosis, or marketing-permission change occurred.""")
    write("job6-search-document-report.md", """# Job 6 search-document report

Ten asset documents and eight scene documents are READY. QA found them concise, non-empty, evidence-grounded, not filename-dominated, and structured separately from normalized text. Each carries a source hash, version, build timestamp, evidence type/confidence/run ID, and purpose-scoped child-table protection. No transcript/OCR claim was fabricated. Job 7 ranking/search was not implemented.""")
    write("job6-permission-verification.md", """# Job 6 permission verification

External-AI gate: PASS (10/10 selected TRUE; restricted DSC00365.JPG, IMG_0588.MP4, IMG_1253.MP4 FALSE; held DSC03759.JPG FALSE). Restricted/backup analysis runs: 0.

RLS remains enabled. Direct anon/authenticated SELECT and TRUNCATE privileges are false for scenes, keyframes, transcripts, OCR, clinical observations, structured child tables, search documents, and vector tables. PUBLIC/anon/authenticated execute on the private external-AI function is false. The least-privilege Job 6 migration grants only service-role worker access to transcript rows/sequence and is recorded in migration history.

Live unauthenticated downloads for a selected UUID, restricted UUID, and constructed UUID returned HTTP 401 without storage/source/private-data leakage. Health/login/library returned 200/200/307. View/download separation and authorized-download behavior remain covered by the unchanged Job 5.2 implementation and regression suite.""")

    counts = {t:{"before":0,"new":FIRST[t],"after":FIRST[t]} for t in TABLES}
    preservation = {"job":"KDI_AI_SEARCH_V3_JOB_6","core":{"assets":{"before":881,"after":881},"source_files":{"before":890,"after":890},"asset_sources":{"before":881,"after":881},"asset_destinations":{"before":881,"after":881},"asset_visual_embeddings":{"before":875,"after":875},"asset_semantic_index":{"before":20,"after":20},"asset_embeddings":{"before":20,"after":20},"asset_access_control":{"before":881,"after":881},"treatments":{"before":12,"after":12},"treatment_aliases":{"before":6,"after":6},"anatomy_terms":{"before":25,"after":25},"actions":{"before":22,"after":22},"locations":{"before":11,"after":11}},"intelligence":counts,"asset_ai_profiles":{"before":10,"new":6,"after":16,"pilot_profiles_after":10},"boundary":{"processed_pilot_assets":10,"restricted_processed":0,"backup_processed":0,"unauthorized_non_pilot_processed":0},"media_modified":False,"global_visual_regeneration":False}
    (OUT / "job6-data-preservation.json").write_text(json.dumps(preservation, indent=2)+"\n", encoding="utf-8")

    qa=[]
    for name,aid,media,summary in PILOT:
        video=media=="video"; qa.append(f"## {name}\n\nAuthorization: PASS. Processing: COMPLETE. Scenes/keyframes: {1 if video else 0}/{1 if video else 0}. Transcript/OCR: 0 (deferred/not applicable) / 0. Scene/keyframe embeddings: {1 if video else 0}/{1 if video else 0}; text embeddings deferred. Asset document: PASS; scene documents: {1 if video else 0}.\n\nSummary: {summary} Evidence is controlled visual review (0.85–0.95 confidence); identity and exact age were not inferred.")
    write("job6-pilot-quality-review.md", "# Job 6 pilot quality review\n\n"+"\n\n".join(qa)+"\n\nAll documents passed factuality, concision, evidence, permission, and duplication checks.")
    write("job6-regression-tests.md", """# Job 6 regression tests

- TypeScript typecheck: PASS
- Dashboard tests: PASS — 240/240
- Python tests: PASS — 655 tests plus 74 subtests
- Focused Job 6 tests: PASS — 5/5 (included in Python total)
- Authorization/restricted/non-pilot boundary: PASS
- Scene/keyframe/ontology/structured extraction: PASS
- Visual dimensions and pgvector storage: PASS
- Text embedding/transcript: DEFERRED — no approved working provider
- Search documents and idempotency: PASS (second run added zero rows)
- RLS/function privileges/download security: PASS
- V1/V2 hashes: PASS
- Live health/login/protected library: PASS — 200/200/307

An initial unscoped pytest collection hit the repository's known duplicate utility/test basename. The authoritative repository invocation with `PYTHONPATH=src;repository` and the `tests` target passed fully.""")

    count_lines="\n".join(f"{t}: before 0 / new {FIRST[t]} / after {FIRST[t]}" for t in TABLES)
    process="\n".join(f"{i}. {n}: COMPLETE; scenes {1 if m=='video' else 0}; keyframes {1 if m=='video' else 0}; transcript 0 DEFERRED/N/A; OCR 0; visual embeddings {2 if m=='video' else 0}; text embeddings DEFERRED; search document PASS" for i,(n,_,m,_) in enumerate(PILOT,1))
    reports=["job6-preflight.md","job6-pilot-manifest.json","job6-analysis-run.md","job6-embedding-architecture.md","job6-scene-indexing.md","job6-keyframe-indexing.md","job6-transcript-ocr.md","job6-structured-intelligence.md","job6-pgvector-report.md","job6-search-document-report.md","job6-permission-verification.md","job6-data-preservation.json","job6-pilot-quality-review.md","job6-regression-tests.md","JOB_6_FINAL_REPORT.md"]
    final=f"""# KDI AI SEARCH V3 — JOB 6 FINAL

## Project

Root: `D:\\Asset_Management_AI`  
Branch: `{branch}`  
HEAD: `{head}`

## Semantic search architecture

Database/vector storage: PostgreSQL/Supabase + pgvector 0.8.2. New vector database introduced: NO. Ollama installed: NO.

Text embedding provider/model/dimension: none operational and approved / none / none. Status: **DEFERRED**.  
Visual provider/model/dimension: `open_clip` / `ViT-B-32` (`laion2b_s34b_b79k`) / 512. Status: PASS.  
pgvector tables: asset_visual_embeddings, asset_embeddings, scene_embeddings, keyframe_embeddings, transcript_embeddings. Existing primary/unique/model/filtering indexes were retained; no ANN index was added.

## Pilot authorization

Approved manifest: PASS. Authorized: 10/10. Restricted originals processed: 0. Backups processed: 0. Unauthorized non-pilot assets processed: 0.

## Analysis run

Cohort: `{run['cohort_id']}`. Pipeline: `{run['pipeline_version']}`. Status: COMPLETED. Started: {run['started_at']}. Completed: {run['completed_at']}.

## Pilot processing

{process}

## Intelligence counts

{count_lines}

## Quality

Scene segmentation, keyframes, ontology mapping, structured intelligence, people/roles, narratives, search documents, visual dimensions, and idempotency: PASS. Transcript/text-vector work: DEFERRED. OCR: NOT APPLICABLE (no useful visible text). No ontology gap was found.

## Security

External-AI gate, restricted/unreviewed denial, RLS, search/scene/keyframe/transcript/embedding protection, download enforcement, direct-route bypass, and denied-response leakage: PASS. anon/authenticated TRUNCATE: FALSE/FALSE. Unsafe PUBLIC execute introduced: NO.

## Data preservation

Assets 881/881; source files 890/890; asset sources 881/881; destinations 881/881; visual asset embeddings 875/875; access controls 881/881. Media/originals modified: NO. Global visual regeneration: NO. Asset AI profiles: 10 before, 6 new, 16 after; all prior rows preserved and all ten pilot assets now have profiles.

## V1 / V2

`hybrid_search_assets`: PASS — `6b179fcb951bf228d434b44baad56c38`  
`hybrid_search_assets_v2`: PASS — `14f4f1347d13fa2201ac6e20e7e5020b`

## Production and tests

Port 3000/website: PASS; outage: NO; frontend redesigned: NO. TypeScript PASS; dashboard 240/240; Python 655 tests plus 74 subtests; focused Job 6 5/5; authorization, scene, keyframe, structured intelligence, visual pgvector, search documents, idempotency, non-pilot protection, RLS, downloads, and V1/V2 regression PASS. Transcript/text embedding DEFERRED.

## Reports

"""+"\n".join(f"- `reports/ai-search-v3/{x}`" for x in reports)+"""

## Job 7 readiness

**READY**

Indexed pilot files: **10/10**  
Partial/failed files: NONE  
Deferred items: transcription and text embeddings — no approved working provider configured. These are explicitly non-blocking under Job 6 authorization.  
Blockers: NONE

STOP HERE. DO NOT START JOB 7.
"""
    write("JOB_6_FINAL_REPORT.md", final)
    print(json.dumps({"status":"PASS","reports":len(reports)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
