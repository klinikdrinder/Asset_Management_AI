import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "../..");
const report = JSON.parse(readFileSync(path.join(root, "reports/semantic-search/30-asset-rollout/phase01/phase01_selection_audit.json"), "utf8"));
const manifest = JSON.parse(readFileSync(path.join(root, "reports/semantic-search/30-asset-rollout/phase01/kdi_30_asset_rollout_v1.json"), "utf8"));

test("Phase 1 rollout selection targeted checks", () => {
  const checks = [
    report.baseline.system_fingerprint === "ba59fb115bd96b878971a74cd3ee1c6a4601930110b29b3505a586c69acf4751",
    report.baseline.spec_fingerprint === "6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7",
    report.baseline.original_pilot === 10,
    report.selection.selected === 20,
    report.selection.unique_asset_ids === 20,
    report.selection.unique_hashes === 20,
    report.selection.original_overlap === 0,
    report.selection.duplicate_content === 0,
    report.selection.supported_format === 20,
    report.selection.hash_present === 20,
    report.selection.provenance === 20,
    report.selection.available === 20,
    manifest.new_assets.length === 20,
    manifest.new_assets.every((x: any) => x.rollout_number >= 11 && x.rollout_number <= 30),
    manifest.new_assets.filter((x: any) => x.canary).length === 1,
    manifest.new_assets.filter((x: any) => x.rollout_wave === "WAVE_1").length === 1,
    manifest.new_assets.filter((x: any) => x.rollout_wave === "WAVE_2").length === 4,
    manifest.new_assets.filter((x: any) => x.rollout_wave === "WAVE_3").length === 5,
    manifest.new_assets.filter((x: any) => x.rollout_wave === "WAVE_4").length === 10,
    report.security.acl_preflight === 20,
    report.security.production_acl_modified === false,
    report.security.consent_auto_approved === 0,
    report.outputs.external_ai_enabled === false,
    report.outputs.openai_api_calls === 0,
    report.outputs.media_analysis === 0,
    report.outputs.semantic_facts === 0,
    report.outputs.newly_search_ready === 0,
    report.manifest.fingerprint_match === true,
    report.manifest.lock === "PASS",
    manifest.manifest_status === "LOCKED",
  ];
  assert.equal(checks.length, 30);
  assert.equal(checks.filter(Boolean).length, 30);
});
