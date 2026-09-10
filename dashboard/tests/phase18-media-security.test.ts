import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path: string) => readFileSync(path, "utf8");

test("production media authorization runs before location resolution", () => {
  const source = read("app/media-service.ts");
  const fn = source.slice(source.indexOf("export async function authorizedMedia"), source.indexOf("async function devAuthorizedMedia"));
  assert.ok(fn.indexOf('rpc("phase18_authorize_candidates_for"') < fn.indexOf("resolveAssetMediaLocation"));
  assert.match(fn, /decision\?\.discover !== true/);
  assert.match(fn, /decision\?\.view_metadata !== true/);
  assert.match(fn, /decision\?\.preview !== true/);
  assert.match(fn, /download && decision\.download !== true/);
  assert.match(fn, /rpc\("can_user_download_asset_for"/);
});

test("media responses are private and authorization-sensitive output is not publicly cached", () => {
  for (const path of [
    "app/api/media/[sourceFileId]/preview/route.ts",
    "app/api/media/[sourceFileId]/download/route.ts",
    "app/api/media/[sourceFileId]/thumbnail/route.ts",
  ]) {
    const source = read(path);
    assert.match(source, /force-dynamic/);
  }
  assert.match(read("app/media-service.ts"), /Cache-Control["']?,\s*["']private|private, no-store|no-store, private/i);
  assert.doesNotMatch(read("db/candidate-authorizer.ts"), /unstable_cache|cache\(/);
});

test("batch authorization RPC is backend-only and canonical functions fail closed", () => {
  const migration = read("../supabase/migrations/20260826043121_phase18_authorization_enforcement.sql");
  assert.match(migration, /revoke all on function public\.phase18_authorize_candidates_for[\s\S]*from public,anon,authenticated/i);
  assert.match(migration, /grant execute on function public\.phase18_authorize_candidates_for[\s\S]*to service_role/i);
  assert.match(migration, /internal_usage_status\s*=\s*'ALLOWED'/i);
  assert.match(migration, /ac\.is_clinical is not null/i);
  assert.match(migration, /private\.is_asset_source_available/i);
});
