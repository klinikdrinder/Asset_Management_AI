import nextEnv from "@next/env";
import {createHash} from "node:crypto";
import {createServiceClient} from "../app/lib/supabase/service";
import {materializePersonAppearance} from "../db/people-appearance-materializer";

nextEnv.loadEnvConfig(process.cwd());

// Deliberately capped at ten preselected assets. This script performs SELECTs only.
const sample = [
  ["b79c659c-c5fe-438c-8c46-10d1542b3301", "91deb0dc-6ea7-5bfb-9da7-07cf6990072b"],
  ["fbfe0bdf-bb73-49f1-883d-3c7043878355", "b091d741-b901-555f-9b58-76813248f0db"],
  ["8cfdfc5e-4c54-45b3-bdb5-54129cc96ba9", "5bebc495-5226-546b-956b-e08bf771cb12"],
  ["ef44c4b1-048b-41f7-b675-a1a0ae29331b", "e08fd554-6d30-5cc9-bbfb-ac01776d069e"],
  ["cd453280-2096-4a68-bfd2-1bf070f79140", "7303821b-c63a-55cb-9dcb-053e5ccb120d"],
  ["f29e992c-8072-4b9a-b4c7-fddfc6efbcd9", "f6b4abd1-e782-5271-b2b8-c21bf9e79919"],
  ["4248f9e4-9ace-4923-94be-ff6cde1eb506", "603b6cbf-2b86-5909-b0d1-11669a08b958"],
  ["536417dd-2987-4f12-9acc-2eb4daa790e4", "4e96a18a-dc39-5628-9ffb-eb62d9e3c2c3"],
  ["b1e6a644-b467-4867-af4f-66b60717ea38", "ad45886e-05dd-59a3-aa3d-b6e25127f48e"],
  ["0142e25c-f4d6-4c37-87dd-b09aab2c8cc4", "49ade68a-8318-5f23-853a-31346c478e8c"],
] as const;

const uuidFor = (value: string) => {
  const hex = createHash("sha256").update(value).digest("hex").slice(0, 32).split("");
  hex[12] = "4";
  hex[16] = ["8", "9", "a", "b"][Number.parseInt(hex[16], 16) % 4];
  return `${hex.slice(0, 8).join("")}-${hex.slice(8, 12).join("")}-${hex.slice(12, 16).join("")}-${hex.slice(16, 20).join("")}-${hex.slice(20).join("")}`;
};

const db = createServiceClient();
const results = [];
for (const [assetId, sceneId] of sample) {
  const assertions = await db.from("semantic_assertions")
    .select("id,asset_id,scene_id,keyframe_id,value_text,canonical_concept_code,confidence,human_review_status,analysis_run_id")
    .eq("asset_id", assetId).eq("scene_id", sceneId).eq("active", true).is("valid_to", null);
  if (assertions.error) throw assertions.error;
  const personId = uuidFor(`fix02-dry-run:${assetId}:${sceneId}:person-1`);
  const output = materializePersonAppearance(assertions.data ?? [], {personId, assetId, sceneId});
  results.push({
    asset_id: assetId,
    scene_id: sceneId,
    source_assertions: assertions.data?.length ?? 0,
    would_materialize: Boolean(output),
    proposed_person_id: output?.person.id ?? null,
    person_fields: output ? Object.keys(output.person).filter(key => !["id", "asset_id", "scene_id"].includes(key)).sort() : [],
    appearance_fields: output ? Object.keys(output.appearance).filter(key => !["scene_person_id", "asset_id", "scene_id", "authority_rank", "source_type", "appearance_confidence", "materialization_key"].includes(key)).sort() : [],
    evidence_rows: output?.evidence.length ?? 0,
    source_type: output?.appearance.source_type ?? null,
  });
}
console.log(JSON.stringify({read_only: true, sample_size: sample.length, database_rows_written: 0, results}, null, 2));
