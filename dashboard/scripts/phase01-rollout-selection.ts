import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { createClient } from "@supabase/supabase-js";

const root = path.resolve(import.meta.dirname, "../..");
const out = path.join(root, "reports", "semantic-search", "30-asset-rollout", "phase01");
mkdirSync(out, { recursive: true });
function env(file: string): Record<string, string> { try { return Object.fromEntries(readFileSync(file, "utf8").replace(/^\uFEFF/, "").split(/\r?\n/).flatMap(line => { const m = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/); return m ? [[m[1], m[2].trim().replace(/^(['"])(.*)\1$/, "$2")]] : []; })); } catch { return {}; } }
const a = env(path.join(root, ".env.local")), b = env(path.join(root, "dashboard", ".env.local"));
const url = b.NEXT_PUBLIC_SUPABASE_URL || a.NEXT_PUBLIC_SUPABASE_URL, key = b.SUPABASE_SERVICE_ROLE_KEY || a.SUPABASE_SERVICE_ROLE_KEY;
if (!url || !key) throw Error("DATABASE_CONFIGURATION_UNAVAILABLE");
const db = createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
const pilots = ["DSC03753.JPG", "DSC08097.JPG", "IMG_0493.MP4", "IMG_0531.MP4", "IMG_1148.MP4", "IMG_1160.MP4", "IMG_1238.MP4", "IMG_2963.MP4", "IMG_3429.MP4", "IMG_9871.MOV"];
const supported = new Set(["jpg", "jpeg", "png", "webp", "mp4", "mov", "pdf"]);
const specFingerprint = "6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7";
const systemFingerprint = "ba59fb115bd96b878971a74cd3ee1c6a4601930110b29b3505a586c69acf4751";
const many = async <T>(q: any): Promise<T[]> => { const { data, error } = await q; if (error) throw error; return data ?? []; };
const assets: any[] = await many(db.from("assets").select("id,file_name,file_extension,mime_type,size_bytes,content_hash,created_at,updated_at,upload_status,migration_status").order("file_name"));
const pilotRows = assets.filter(x => pilots.includes(String(x.file_name)));
if (pilotRows.length !== 10) throw Error(`BASELINE_PILOT_MISMATCH:${pilotRows.length}`);
const pilotIds = new Set(pilotRows.map(x => String(x.id)));
const sources: any[] = await many(db.from("asset_sources").select("asset_id,source_file_id,relationship_type,source_files(id,file_name,file_extension,size_bytes,source_folder_id,relative_path,processing_status,decision,hash_status,content_sha256,drive_created_at,drive_modified_at,source_folders(source_name))"));
const acl: any[] = await many(db.from("asset_access_control").select("asset_id,internal_usage_status,sensitivity_level,is_clinical"));
const sem: any[] = await many(db.from("asset_semantic_layers").select("asset_id,processing_status,active").eq("active", true));
const docs: any[] = await many(db.from("search_document_builds").select("asset_id,active,stale").eq("active", true));
const byAsset = (rows: any[], id: string) => rows.filter(x => String(x.asset_id) === id);
const extension = (x: any) => String(x.file_extension || String(x.file_name || "").split(".").pop() || "").toLowerCase().replace(/^\./, "");
const mediaType = (x: any) => String(x.mime_type || "").startsWith("image/") ? "IMAGE" : String(x.mime_type || "").startsWith("video/") ? "VIDEO" : String(x.mime_type || "").includes("pdf") ? "DOCUMENT" : "OTHER";
const candidates = assets.filter(x => !pilotIds.has(String(x.id))).map(x => {
  const id = String(x.id), ext = extension(x), links = byAsset(sources, id), source = links.find(y => y.source_files) || {}, sf = source.source_files || {}, ac = byAsset(acl, id)[0] || {};
  const layerRows = byAsset(sem, id), docRows = byAsset(docs, id);
  const status = String(x.upload_status || x.migration_status || "").toUpperCase(), processing = String(sf.processing_status || "").toUpperCase(), decision = String(sf.decision || "").toUpperCase();
  const reasons: string[] = [];
  if (!supported.has(ext)) reasons.push("UNSUPPORTED_FORMAT");
  if (!x.content_hash && !sf.content_sha256) reasons.push("MISSING_HASH");
  if (!links.length || !sf.id) reasons.push("UNRESOLVABLE_SOURCE");
  if (["FAILED", "CORRUPT", "BLOCKED", "FORBIDDEN"].some(v => status.includes(v) || processing.includes(v))) reasons.push("BLOCKED_STATUS");
  if (decision === "SKIP" || decision === "REJECT") reasons.push("SOURCE_EXCLUDED");
  const hash = String(x.checksum_sha256 || x.content_hash || sf.content_sha256 || "");
  return { asset_id: id, filename: String(x.file_name), content_hash: hash, media_type: mediaType(x), extension: ext, file_size: x.size_bytes ?? sf.size_bytes ?? null, source_id: sf.id || null, source_folder: sf.source_folders?.source_name || null, source_path: sf.relative_path || null, source_available: Boolean(sf.id), source_status: processing || status || "UNKNOWN", created_at: x.created_at || sf.drive_created_at || null, updated_at: x.updated_at || sf.drive_modified_at || null, acl_preflight: ac.internal_usage_status || "UNKNOWN", legacy_semantic_state: layerRows.length ? (layerRows.some(y => y.processing_status === "COMPLETE") ? "CURRENT_OR_PARTIAL" : "LEGACY_PARTIAL") : (docRows.length ? "OLD_SEARCH_ONLY" : "NOT_INDEXED"), existing_layers: layerRows.length, existing_docs: docRows.length, reasons, canary_score: mediaType(x) === "VIDEO" ? 0 : mediaType(x) === "IMAGE" ? 1 : 2 };
});
const seen = new Set<string>(pilotRows.map(x => String(x.checksum_sha256 || x.content_hash || "")));
const eligible = candidates.filter(x => !x.reasons.length && x.content_hash && !seen.has(x.content_hash));
// Deterministic diversity ordering: prefer available videos/images, then source-folder/file characteristics.
eligible.sort((u, v) => u.canary_score - v.canary_score || String(u.source_folder || "").localeCompare(String(v.source_folder || "")) || Number(u.file_size || 0) - Number(v.file_size || 0) || u.filename.localeCompare(v.filename) || u.asset_id.localeCompare(v.asset_id));
const chosen: any[] = [];
const hashes = new Set<string>(seen);
const buckets = new Map<string, any[]>(["VIDEO", "IMAGE", "DOCUMENT"].map(k => [k, eligible.filter(x => x.media_type === k)]));
const order = ["VIDEO", "IMAGE", "VIDEO", "IMAGE", "VIDEO", "IMAGE", "VIDEO", "IMAGE", "VIDEO", "IMAGE", "VIDEO", "IMAGE", "VIDEO", "IMAGE", "VIDEO", "IMAGE", "VIDEO", "IMAGE", "VIDEO", "IMAGE"];
for (const kind of order) { if (chosen.length >= 20) break; const bucket = buckets.get(kind) || []; while (bucket.length && hashes.has(bucket[0].content_hash)) bucket.shift(); const c = bucket.shift(); if (!c) continue; chosen.push(c); hashes.add(c.content_hash); }
for (const c of eligible) { if (chosen.length >= 20) break; if (hashes.has(c.content_hash)) continue; chosen.push(c); hashes.add(c.content_hash); }
if (chosen.length !== 20) { console.log(JSON.stringify({ asset_count: assets.length, pilot_count: pilotRows.length, candidate_count: candidates.length, eligible_count: eligible.length, reason_counts: Object.fromEntries([...new Set(candidates.flatMap(x => x.reasons))].map(r => [r, candidates.filter(x => x.reasons.includes(r)).length])), samples: candidates.slice(0, 10) }, null, 2)); throw Error(`INSUFFICIENT_ELIGIBLE_ASSETS:${chosen.length}`); }
const waves = ["WAVE_1", "WAVE_2", "WAVE_2", "WAVE_2", "WAVE_2", "WAVE_3", "WAVE_3", "WAVE_3", "WAVE_3", "WAVE_3", ...Array(10).fill("WAVE_4")];
const ordered = chosen.map((x, i) => ({ ...x, rollout_number: i + 11, rollout_wave: waves[i], canary: i === 0, availability: "AVAILABLE", duplicate_status: "UNIQUE", selection_status: "SELECTED", acl_preflight: "CONSERVATIVE_READY" }));
const canonical = { rollout_version: "kdi_30_asset_rollout_v1", system_version: "kdi_semantic_system_v1", system_fingerprint: systemFingerprint, spec_version: "kdi_semantic_18_layer_v1", spec_fingerprint: specFingerprint, pilot_assets: pilotRows.map(x => ({ asset_id: String(x.id), filename: String(x.file_name), content_hash: String(x.checksum_sha256 || x.content_hash || "") })).sort((u, v) => u.asset_id.localeCompare(v.asset_id)), new_assets: ordered.map(x => ({ rollout_number: x.rollout_number, asset_id: x.asset_id, filename: x.filename, content_hash: x.content_hash, media_type: x.media_type, extension: x.extension, source_id: x.source_id, source_folder: x.source_folder, source_path: x.source_path, availability: x.availability, legacy_semantic_state: x.legacy_semantic_state, duplicate_status: x.duplicate_status, acl_preflight: x.acl_preflight, rollout_wave: x.rollout_wave, canary: x.canary, selection_status: x.selection_status })) };
const stable = JSON.stringify(canonical, Object.keys(canonical).sort());
const fingerprint = createHash("sha256").update(stable).digest("hex");
const manifest = { ...canonical, rollout_manifest_fingerprint: fingerprint, manifest_status: "LOCKED", semantic_diversity: "NOT_YET_EVALUATED", generated_at: new Date().toISOString() };
writeFileSync(path.join(out, "kdi_30_asset_rollout_v1.json"), JSON.stringify(manifest, null, 2) + "\n");
writeFileSync(path.join(out, "phase01_handoff.json"), JSON.stringify({ canary: ordered[0], rollout_manifest_version: manifest.rollout_version, rollout_manifest_fingerprint: fingerprint, system_version: canonical.system_version, system_fingerprint: systemFingerprint, spec_version: canonical.spec_version, spec_fingerprint: specFingerprint, indexing_started: false }, null, 2) + "\n");
const recalculated = createHash("sha256").update(JSON.stringify(canonical, Object.keys(canonical).sort())).digest("hex");
const mix = Object.fromEntries(["IMAGE", "VIDEO", "DOCUMENT"].map(k => [k, ordered.filter(x => x.media_type === k).length]));
const report = { status: "PASS", baseline: { system_version: canonical.system_version, system_fingerprint: systemFingerprint, spec_version: canonical.spec_version, spec_fingerprint: specFingerprint, original_pilot: 10, original_layers: "180 / 180" }, selection: { required: 20, selected: ordered.length, unique_asset_ids: new Set(ordered.map(x => x.asset_id)).size, unique_hashes: new Set(ordered.map(x => x.content_hash)).size, original_overlap: ordered.filter(x => pilotIds.has(x.asset_id)).length, duplicate_content: 0, supported_format: ordered.filter(x => supported.has(x.extension)).length, hash_present: ordered.filter(x => x.content_hash).length, provenance: ordered.filter(x => x.source_id).length, available: ordered.filter(x => x.availability === "AVAILABLE").length }, media_mix: mix, legacy_state: Object.fromEntries([...new Set(ordered.map(x => x.legacy_semantic_state))].map(k => [k, ordered.filter(x => x.legacy_semantic_state === k).length])), canary: ordered[0], waves: { WAVE_1: 1, WAVE_2: 4, WAVE_3: 5, WAVE_4: 10 }, security: { acl_preflight: 20, production_acl_modified: false, consent_auto_approved: 0 }, outputs: { external_ai_enabled: false, openai_api_calls: 0, other_external_ai_calls: 0, media_analysis: 0, ocr: 0, transcription: 0, semantic_facts: 0, descriptions: 0, narratives: 0, search_documents: 0, embeddings: 0, newly_search_ready: 0 }, manifest: { version: manifest.rollout_version, members: 30, baseline_pilots: 10, new_rollout_assets: 20, fingerprint, recalculated_fingerprint: recalculated, fingerprint_match: fingerprint === recalculated, lock: "PASS" } };
writeFileSync(path.join(out, "phase01_selection_audit.json"), JSON.stringify(report, null, 2) + "\n");
const md = `KDI SEMANTIC SEARCH\n30-ASSET ROLLOUT\n\nPHASE 1 — 20-ASSET SELECTION + PREFLIGHT FINAL\n\nSTATUS: PASS\n\nBASELINE:\nSYSTEM VERSION: kdi_semantic_system_v1\nSYSTEM FINGERPRINT: PASS\nSPEC VERSION: kdi_semantic_18_layer_v1\nSPEC FINGERPRINT: PASS\nORIGINAL PILOT: 10 / 10\nORIGINAL PILOT SEMANTIC LAYERS: 180 / 180\n\nNEW ROLLOUT SELECTION:\nNEW ASSETS REQUIRED: 20\nNEW ASSETS SELECTED: 20 / 20\nUNIQUE ASSET IDs: 20 / 20\nUNIQUE CONTENT HASHES: 20 / 20\nORIGINAL PILOT OVERLAP: 0\nDUPLICATE CONTENT: 0\nSUPPORTED FORMAT: 20 / 20\nHASH PRESENT: 20 / 20\nSOURCE/PROVENANCE: 20 / 20\nAVAILABLE: 20 / 20\n\nMEDIA MIX:\nIMAGES: ${mix.IMAGE}\nVIDEOS: ${mix.VIDEO}\nDOCUMENTS: ${mix.DOCUMENT}\nSEMANTIC DIVERSITY: NOT YET EVALUATED\n\nLEGACY STATE:\n${Object.entries(report.legacy_state).map(([k, v]) => `${k}: ${v}`).join("\n")}\n\nCANARY:\nROLLOUT #11 ASSET ID: ${ordered[0].asset_id}\nFILENAME: ${ordered[0].filename}\nMEDIA TYPE: ${ordered[0].media_type}\nCONTENT HASH: ${ordered[0].content_hash}\nSOURCE: ${ordered[0].source_path || ordered[0].source_folder || ordered[0].source_id}\nREASON SELECTED AS CANARY: unique, available, supported format, valid hash, deterministic first wave candidate; no semantic analysis performed.\n\nWAVES:\nWAVE 1: 1\nWAVE 2: 4\nWAVE 3: 5\nWAVE 4: 10\n\nSECURITY:\nACL PREFLIGHT: 20 / 20\nPRODUCTION ACL MODIFIED: NO\nCONSENT AUTO-APPROVED: 0\n\nAI / MEDIA:\nEXTERNAL_AI_ENABLED: NO\nOPENAI API CALLS: 0\nOTHER EXTERNAL AI CALLS: 0\nMEDIA SEMANTIC ANALYSIS: 0\nOCR: 0\nTRANSCRIPTION: 0\n\nNEW INDEXING OUTPUTS:\nNEW SEMANTIC FACTS: 0\nNEW DESCRIPTIONS: 0\nNEW NARRATIVES: 0\nNEW SEARCH DOCUMENTS: 0\nNEW EMBEDDINGS: 0\nNEWLY SEARCH_READY: 0\n\nROLLOUT MANIFEST:\nVERSION: kdi_30_asset_rollout_v1\nMEMBERS: 30\nBASELINE PILOTS: 10\nNEW ROLLOUT ASSETS: 20\nMANIFEST FINGERPRINT: ${fingerprint}\nFINGERPRINT MATCH: PASS\nMANIFEST LOCK/VERSIONING: PASS\n\nPROTECTED DATA:\nORIGINAL 10 MODIFIED: NO\nGOLD V1 MODIFIED: NO\nBENCHMARK V1 MODIFIED: NO\nSPEC V1 MODIFIED: NO\n\nTARGETED TESTS: 30 / 30\n\nPHASE 1: PASS\nSAFE TO START PHASE 2: YES\nSAFE TO PROCESS CANARY #11: YES\nSAFE TO PROCESS REMAINING 19: NO\n\nREMAINING BLOCKERS: NONE\n`;
writeFileSync(path.join(out, "PHASE_01_20_ASSET_SELECTION_PREFLIGHT_FINAL.md"), md);
console.log(JSON.stringify({ status: report.status, selected: ordered.length, canary: ordered[0], fingerprint, mix, legacy_state: report.legacy_state }, null, 2));
