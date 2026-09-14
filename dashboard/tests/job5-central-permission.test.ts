import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const media = readFileSync(new URL("../app/media-service.ts", import.meta.url), "utf8");

test("media resolution relies on asset RLS before Drive access", () => {
  assert.match(media, /liveRest\(`assets\?select=/);
  assert.match(media, /resolveAssetMediaLocation\(assetId, operation, fetchProductionAssetRow\)/);
});

test("downloads require the central per-user per-asset authorization", () => {
  assert.match(media, /rpc\("can_user_download_asset_for"/);
  assert.match(media, /p_user_id: user\.userId/);
  assert.match(media, /allowed !== true/);
  assert.match(media, /AuthorizationDenied/);
});
