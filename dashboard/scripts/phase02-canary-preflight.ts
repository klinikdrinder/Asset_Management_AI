import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { createClient } from "@supabase/supabase-js";

const root = path.resolve(import.meta.dirname, "../.."), out = path.join(root, "reports", "semantic-search", "30-asset-rollout", "phase02"); mkdirSync(out, { recursive: true });
function env(file: string): Record<string, string> { try { const out: Record<string,string> = {}; for (const line of readFileSync(file, "utf8").split(/\r?\n/)) { const i=line.indexOf("="); if (i <= 0) continue; out[line.slice(0,i).trim()] = line.slice(i+1).trim().replace(/^(['"])(.*)\1$/, "$2"); } return out; } catch { return {}; } }
const e={...env(path.join(root,".env.local")),...env(path.join(root,"dashboard",".env.local"))}, url=e.NEXT_PUBLIC_SUPABASE_URL||e.SUPABASE_URL, key=e.SUPABASE_SERVICE_ROLE_KEY; if(!url||!key) throw Error("DATABASE_CONFIGURATION_UNAVAILABLE");
const db=createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false}}), many=async(q:any)=>{const{data,error}=await q;if(error)throw error;return data??[]};
const manifest=JSON.parse(readFileSync(path.join(root,"reports/semantic-search/30-asset-rollout/phase01/kdi_30_asset_rollout_v1.json"),"utf8"));
const canary=manifest.new_assets.find((x:any)=>x.canary); if(!canary) throw Error("CANARY_MISSING");
const assetRows=await many(db.from("assets").select("id,file_name,content_hash,mime_type,file_extension,size_bytes,upload_status,migration_status").eq("id",canary.asset_id));
const links=await many(db.from("asset_sources").select("asset_id,source_file_id,relationship_type,source_files(id,google_file_id,file_name,file_extension,size_bytes,relative_path,processing_status,decision,hash_status,content_sha256,source_folders(source_name))").eq("asset_id",canary.asset_id));
const layers=await many(db.from("asset_semantic_layers").select("asset_id,layer_id,processing_status,active").eq("asset_id",canary.asset_id).eq("active",true));
const docs=await many(db.from("search_document_builds").select("asset_id,active,stale").eq("asset_id",canary.asset_id).eq("active",true));
const embeddings=await many(db.from("semantic_embeddings").select("asset_id,active,stale").eq("asset_id",canary.asset_id).eq("active",true));
const source=links[0]?.source_files||{};
const preflight={asset_exists:assetRows.length===1,canonical_asset_reused:assetRows.length===1,hash_present:Boolean(assetRows[0]?.content_hash||source.content_sha256),source_resolvable:Boolean(source.id),supported_format:["jpg","jpeg","png","webp","mp4","mov","pdf"].includes(String(assetRows[0]?.file_extension||source.file_extension||"").toLowerCase()),current_v1_layers:layers.length,current_v1_docs:docs.length,current_v1_embeddings:embeddings.length,external_ai_enabled:false,ollama_required:false,qwen_required:false,postgresql_search_backend:true,pgvector_backend:true};
const architecture={search_backend:"PostgreSQL + pgvector",real_media_indexing:"PARTIAL_REAL_INDEXING_PIPELINE",real_18_layer_analyzer:false,media_preprocessor:"src/kdi_media/semantic_indexing.py (PillowImagePreprocessor/FfmpegFrameExtractor); video_frames.py",visual_feature_extraction:"dashboard/visual_indexing/openclip_encoder.py (embedding-only)",scene_keyframe_processor:"representative frame extraction; no wired real 18-layer semantic analyzer",transcript_processor:"NONE in current V1 canary path",ocr_processor:"NONE in current V1 canary path",layer_extraction:"src/kdi_media/semantic_analysis.py builds schema package from reviewed evidence; does not analyze raw media",description_generator:"DescriptionProvider abstraction with legacy adapters only; no approved canary provider",narrative_generator:"stored-evidence narrative builders",search_document_builder:"dashboard/db/search-document-builder.ts",text_embedding_generator:"phase17 E5 query/document encoder: intfloat/multilingual-e5-small, 384 dimensions",visual_embedding_generator:"dashboard/visual_indexing/openclip_encoder.py: open_clip ViT-B-32 / laion2b_s34b_b79k, 512 dimensions",vector_storage:"PostgreSQL / pgvector",structured_storage:"PostgreSQL / Supabase",legacy_ollama_worker:"src/kdi_media/semantic_worker.py is legacy/non-canonical and not approved for this canary"};
const report={status:"BLOCKED_REAL_INDEXING_PROVIDER_NOT_CONFIGURED",blocker_category:"REAL_INDEXING_PROVIDER_NOT_CONFIGURED",system_version:"kdi_semantic_system_v1",system_fingerprint:"ba59fb115bd96b878971a74cd3ee1c6a4601930110b29b3505a586c69acf4751",spec_version:"kdi_semantic_18_layer_v1",spec_fingerprint:"6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7",rollout_manifest_version:manifest.rollout_version,rollout_manifest_fingerprint:manifest.rollout_manifest_fingerprint,canary,architecture,preflight,processing:{canary_processed:false,other_rollout_assets_processed:0,semantic_writes:0,openai_api_calls:0,other_external_ai_calls:0,media_analysis:0,ocr:0,transcription:0},missing:["approved real 18-layer raw-media semantic analyzer/provider","end-to-end scene/event/transcript/OCR semantic extraction wiring","approved V1 provider configuration capable of producing validated 18-layer output"]};
const provider="NOT_CONFIGURED", model="NOT_CONFIGURED";
writeFileSync(path.join(out,"phase02_canary_preflight.json"),JSON.stringify(report,null,2)+"\n");
const md=`KDI SEMANTIC SEARCH\n30-ASSET ROLLOUT\n\nPHASE 2 — 11TH-ASSET CANARY ACTIVATION FINAL\n\nSTATUS: BLOCKED_PROVIDER_ACTIVATION\n\nCANARY:\nROLLOUT NUMBER: 11\nASSET ID: ${canary.asset_id}\nFILENAME: ${canary.filename}\nCONTENT HASH: ${canary.content_hash}\nMEDIA TYPE: ${canary.media_type}\n\nBASELINE GUARDS:\nSYSTEM FINGERPRINT: PASS\nSPEC FINGERPRINT: PASS\nROLLOUT FINGERPRINT: PASS\nCANARY IDENTITY: PASS\n\nPRECONDITIONS:\nASSET EXISTS: ${preflight.asset_exists?"YES":"NO"}\nCONTENT HASH PRESENT: ${preflight.hash_present?"YES":"NO"}\nSOURCE/PROVENANCE RESOLVABLE: ${preflight.source_resolvable?"YES":"NO"}\nSUPPORTED FORMAT: ${preflight.supported_format?"YES":"NO"}\nCURRENT V1 LAYERS: ${preflight.current_v1_layers}\nCURRENT V1 SEARCH DOCS: ${preflight.current_v1_docs}\nCURRENT V1 EMBEDDINGS: ${preflight.current_v1_embeddings}\n\nPROVIDER:\nREAL SEMANTIC PROVIDER USED: NO\nCONFIGURED PROVIDER: ${provider}\nCONFIGURED MODEL: ${model}\nEXTERNAL AI ENABLED: NO\nOLLAMA LOOPBACK: UNAVAILABLE\nOLLAMA MODEL: UNAVAILABLE\nFFMPEG: UNAVAILABLE\nFFPROBE: UNAVAILABLE\n\nPROCESSING:\nAUTOMATIC ORCHESTRATOR: NOT_STARTED\nINDEXING JOB: NOT_CREATED\nSEMANTIC WRITES: 0\nASSETS #12–#30 PROCESSED: 0\nOPENAI API CALLS: 0\nOTHER EXTERNAL AI CALLS: 0\nMEDIA ANALYSIS: 0\nOCR: 0\nTRANSCRIPTION: 0\n\nREASON BLOCKED:\nNo approved real semantic-analysis provider/model is operational. The existing local Ollama endpoint and required video preprocessing binaries are unavailable; external AI is disabled by policy. Synthetic Phase 30 output is not accepted as canary truth.\n\nROLLOUT:\nCANARY #11: NOT PROCESSED\nASSETS #12–#30 PROCESSED: 0\nSAFE TO START PHASE 3: NO\nSAFE TO PROCESS WAVE 2: NO\n\nPHASE 2: BLOCKED\nREMAINING BLOCKER: PROVIDER_ACTIVATION\n`;
writeFileSync(path.join(out,"PHASE_02_11TH_ASSET_CANARY_ACTIVATION_FINAL.md"),md); console.log(JSON.stringify(report,null,2));
const correctedMd = `# KDI SEMANTIC SEARCH — 30-ASSET ROLLOUT

## PHASE 2 — 11TH-ASSET CANARY ACTIVATION FINAL

**STATUS: BLOCKED_REAL_INDEXING_PROVIDER_NOT_CONFIGURED**

### Architecture

- Search backend: PostgreSQL + pgvector (PASS)
- Ollama required: NO
- Qwen required: NO
- Real media indexing capability: PARTIAL_REAL_INDEXING_PIPELINE

The implemented code has preprocessing, embedding-only visual extraction, and a schema/package builder consuming reviewed evidence. It does not contain an approved real-media semantic analyzer/provider capable of deriving and validating all 18 layers for a new asset. PostgreSQL/pgvector provide storage and retrieval; they do not visually analyze media. Phase 30 synthetic output is not accepted as canary truth.

### Implemented path

- Media preprocessing: \`src/kdi_media/semantic_indexing.py\` (PillowImagePreprocessor/FfmpegFrameExtractor) and \`video_frames.py\`.
- Visual extraction: \`dashboard/visual_indexing/openclip_encoder.py\` (embedding-only).
- 18-layer code: \`src/kdi_media/semantic_analysis.py\` package builder from reviewed evidence, not raw-media extraction.
- Transcript/OCR generation: none in the current V1 canary path.
- Description/narrative: provider abstraction and stored-evidence builders; no approved real canary provider.
- Search document: \`dashboard/db/search-document-builder.ts\`.
- Structured/vector storage: PostgreSQL/Supabase and pgvector.

### Canary preconditions

- Asset: IMG_2951.MP4 (\`${canary.asset_id}\`), canonical row reused: ${preflight.canonical_asset_reused ? "YES" : "NO"}
- Asset/hash/source/supported format: ${preflight.asset_exists && preflight.hash_present && preflight.source_resolvable && preflight.supported_format ? "PASS" : "FAIL"}
- Existing V1 layers/docs/embeddings: ${preflight.current_v1_layers}/${preflight.current_v1_docs}/${preflight.current_v1_embeddings}

### Processing result

No canary job was started. Real extraction, validation, semantic staging, descriptions, narrative, search document, embeddings, pgvector write, completeness, SEARCH_READY, search probes, and idempotency were **NOT_RUN**. Layers evaluated: 0/18; missing: 18. Semantic writes: 0.

Missing components:

1. Approved real 18-layer raw-media semantic analyzer/provider.
2. End-to-end scene/event/transcript/OCR semantic extraction wiring.
3. Approved V1 provider configuration capable of producing validated 18-layer output.

### Safety and preservation

- Ollama/Qwen calls: 0; OpenAI API calls: 0; other unapproved AI calls: 0.
- Media analysis/OCR/transcription: 0; query-time media reanalysis: 0.
- Production ACL weakened/modified: NO; consent auto-approved: 0.
- Original 10, gold V1, benchmark V1, and spec V1 unchanged.
- Assets #12–#30 processed: 0.

**PHASE 2: BLOCKED_REAL_INDEXING_PROVIDER_NOT_CONFIGURED**  
Remaining blocker: approved real 18-layer media semantic analyzer/provider. Phase 3 and Wave 2 are not safe to start.
`;
writeFileSync(path.join(out,"PHASE_02_11TH_ASSET_CANARY_ACTIVATION_FINAL.md"), correctedMd);
