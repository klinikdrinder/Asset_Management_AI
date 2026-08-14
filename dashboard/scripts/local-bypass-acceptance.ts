import { readFileSync } from "node:fs";
import path from "node:path";
import { createClient } from "@supabase/supabase-js";

function loadEnv(file: string) {
  return Object.fromEntries(
    readFileSync(file, "utf8").replace(/^\uFEFF/, "").split(/\r?\n/).flatMap((line) => {
      const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
      return match ? [[match[1], match[2].trim().replace(/^(['"])(.*)\1$/, "$2")]] : [];
    }),
  );
}

const env = { ...process.env, ...loadEnv(path.resolve(".env.local")) };
const admin = createClient(env.NEXT_PUBLIC_SUPABASE_URL!, env.SUPABASE_SERVICE_ROLE_KEY!, {
  auth: { persistSession: false, autoRefreshToken: false },
});
const result: Record<string, string | number> = {};

const count = await admin.from("assets").select("id", { count: "exact", head: true });
result.assets = !count.error && count.count === 881 ? `PASS (${count.count})` : `FAIL (${count.count ?? "unknown"})`;

const destinations = await admin
  .from("asset_destinations")
  .select("asset_id")
  .eq("upload_status", "VERIFIED")
  .not("destination_google_file_id", "is", null)
  .limit(100);
const ids = [...new Set((destinations.data ?? []).map((row) => String(row.asset_id)))];
const assets = ids.length
  ? await admin.from("assets").select("id,mime_type,file_name").in("id", ids)
  : { data: [], error: new Error("No verified destinations") };
const image = assets.data?.find((asset) => String(asset.mime_type).startsWith("image/"));
const video = assets.data?.find((asset) => String(asset.mime_type).startsWith("video/"));

async function page(name: string, route: string, marker: RegExp) {
  const response = await fetch(`http://127.0.0.1:3000${route}`, { redirect: "manual" });
  const body = await response.text();
  result[name] = response.status === 200 && marker.test(body) && !/Database unavailable|Internal Server Error/.test(body) ? "PASS" : `FAIL (${response.status})`;
}
await page("library", "/library", /fileCard/);
await page("filename_search", "/library?query=IMG", /fileCard/);
await page("semantic_search", "/library?nlq=clinic%20room", /fileCard/);
await page("filters", "/library?category=image", /fileCard/);
await page("pagination", "/library?page=2", /fileCard/);

async function media(name: string, assetId: string | undefined, operation: string) {
  if (!assetId) { result[name] = "FAIL (no verified asset)"; return; }
  const response = await fetch(`http://127.0.0.1:3000/api/media/${assetId}/${operation}`, {
    headers: { Range: "bytes=0-63" }, redirect: "manual",
  });
  result[name] = response.status === 200 || response.status === 206 ? "PASS" : `FAIL (${response.status})`;
  await response.body?.cancel();
}
await media("thumbnail", image?.id, "thumbnail");
await media("image_preview", image?.id, "preview");
await media("video_preview", video?.id, "preview");
await media("download", image?.id, "download");

const embeddings = await admin.from("asset_visual_embeddings").select("id", { count: "exact", head: true });
const qwen = await admin.from("asset_embeddings").select("id", { count: "exact", head: true });
result.visual_embeddings = embeddings.error ? "FAIL" : Number(embeddings.count);
result.qwen_embeddings = qwen.error ? "FAIL" : Number(qwen.count);

console.log(JSON.stringify(result, null, 2));
