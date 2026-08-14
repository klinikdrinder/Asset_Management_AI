import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const read = (path: string) => readFileSync(path, "utf8");

test("no Google credential of any kind is ever prefixed NEXT_PUBLIC_", () => {
  for (const path of [".env.example", "app/lib/google/service-account.ts", "app/lib/google/drive-client.ts"]) {
    const source = read(path);
    assert.doesNotMatch(source, /NEXT_PUBLIC_[A-Z_]*GOOGLE/);
    assert.doesNotMatch(source, /NEXT_PUBLIC_[A-Z_]*DRIVE/);
  }
});

test(".env.example documents the service-account variables without a real credential", () => {
  const source = read(".env.example");
  assert.match(source, /KDI_MASTER_DRIVE_ID=/);
  assert.match(source, /GOOGLE_DRIVE_SERVICE_ACCOUNT_EMAIL=/);
  assert.match(source, /GOOGLE_DRIVE_SERVICE_ACCOUNT_PRIVATE_KEY=/);
  assert.doesNotMatch(source, /BEGIN PRIVATE KEY/);
  assert.doesNotMatch(source, /-----BEGIN/);
});

test("the frontend thumbnail component only ever receives an internal API URL, never a Google Drive URL", () => {
  const component = read("app/asset-thumbnail.tsx");
  assert.doesNotMatch(component, /googleapis|googleusercontent|drive\.google\.com|thumbnailLink|webContentLink/i);
  const repository = read("app/lib/media/repository.ts");
  assert.match(repository, /thumbnailUrl:.*\/api\/media\//);
  assert.doesNotMatch(repository, /googleapis|googleusercontent|drive\.google\.com/i);
  const liveProvider = read("app/lib/library/live-provider.ts");
  assert.match(liveProvider, /thumbnailUrl:verified&&\(category==="image"\|\|category==="video"\)\?`\/api\/media\/\$\{x\.id\}\/thumbnail`:null/);
});

test("a changed thumbnail URL remounts the thumbnail image (key prop) so a stale failed state cannot persist", () => {
  const page = read("app/media-library-page.tsx"), ui = read("app/library-ui.tsx");
  assert.match(page, /<AssetThumbnail key=\{asset\.thumbnailUrl\}/);
  assert.match(ui, /<AssetThumbnail key=\{f\.thumbnailUrl\}/);
  const component = read("app/asset-thumbnail.tsx");
  assert.match(component, /onError=\{\(\) => setState\("error"\)\}/);
  assert.match(component, /onLoad=\{\(\) => setState\("loaded"\)\}/);
  assert.match(component, /useState<"loading" \| "loaded" \| "error">\("loading"\)/);
});

test("the real preview surface renders MediaViewer against the internal preview route only when the destination is verified", () => {
  const detail = read("app/simplified-asset-detail.tsx");
  assert.match(detail, /verified=asset\.migration==="VERIFIED"/);
  assert.match(detail, /!previewRole&&verified\?<MediaViewer/);
  assert.doesNotMatch(detail, /googleapis|googleusercontent|drive\.google\.com/i);
  const viewer = read("app/media-viewer.tsx");
  assert.match(viewer, /\/api\/media\/\$\{id\}\/preview/);
  assert.doesNotMatch(viewer, /googleapis|googleusercontent|drive\.google\.com/i);
});
