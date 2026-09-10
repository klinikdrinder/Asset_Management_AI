import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { EVIDENCE_TYPES, ORIGINS, SEMANTIC_STATES } from "../db/semantic-repository";

const migration = readFileSync(path.resolve(process.cwd(), "..", "supabase/migrations/20260824064838_phase10_semantic_database_v1.sql"), "utf8");
const layers = migration.split(/\r?\n/).flatMap((line) => {
  const match = line.match(/^\s*\(\d+,'([A-Z_]+)','/);
  return match ? [match[1]] : [];
});

test("locked semantic contracts are exact", () => {
  assert.deepEqual(SEMANTIC_STATES, ["OBSERVED","FALSE","UNKNOWN","NOT_APPLICABLE"]);
  assert.equal(new Set(layers).size, 18);
  assert.equal(layers[0], "ASSET_IDENTITY_PROVENANCE"); assert.equal(layers[17], "SEARCH_EMBEDDINGS");
  assert.deepEqual(EVIDENCE_TYPES, ["ASSET_LEVEL","SCENE_LEVEL","EVENT_LEVEL","KEYFRAME_LEVEL","TRANSCRIPT","OCR","HUMAN_REVIEW"]);
  assert.deepEqual(ORIGINS, ["AI_MODEL","DETERMINISTIC_PROCESSOR","DATABASE_METADATA","HUMAN_REVIEW"]);
});

test("evidence and precedence safeguards are declared", () => {
  assert.match(migration, /FALSE assertion requires complete negative evidence/);
  assert.match(migration, /search-critical OBSERVED assertion requires evidence/);
  assert.match(migration, /HUMAN_GOLD/); assert.match(migration, /APPROVED_AI/); assert.match(migration, /UNVERIFIED_AI/);
  assert.match(migration, /security_invoker=true/g); assert.match(migration, /signed-off gold is immutable/);
});

test("video and image relational scopes are available", () => {
  for (const table of ["asset_events","semantic_assertions","semantic_assertion_evidence","semantic_narratives"]) assert.match(migration, new RegExp(`create table if not exists public\\.${table}`));
  for (const link of ["scene_id uuid", "event_id uuid", "keyframe_id uuid", "transcript_chunk_id bigint", "ocr_observation_id uuid"]) assert.match(migration, new RegExp(link));
  assert.match(migration, /NOT_APPLICABLE/); assert.match(migration, /UNKNOWN/);
});

test("replay idempotency and mixed embedding dimensions are guarded", () => {
  assert.match(migration, /unique\(asset_id,run_type,source_fingerprint,processor_version,configuration_fingerprint\)/);
  assert.match(migration, /idempotency_key text not null unique/);
  assert.match(migration, /vector_dims\(embedding\)=dimensions/);
});
