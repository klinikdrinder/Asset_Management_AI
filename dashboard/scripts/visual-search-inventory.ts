import { readFileSync } from "node:fs";
import path from "node:path";
import { createClient } from "@supabase/supabase-js";

function loadEnv(file: string): Record<string, string> {
  try {
    return Object.fromEntries(readFileSync(file, "utf8").split(/\r?\n/).flatMap((line) => {
      const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
      return match ? [[match[1], match[2].trim().replace(/^(['"])(.*)\1$/, "$2")]] : [];
    }));
  } catch { return {}; }
}

const root = path.resolve(process.cwd(), "..");
const fileEnv = { ...loadEnv(path.join(root, ".env")), ...loadEnv(path.join(root, ".env.local")), ...loadEnv(path.join(process.cwd(), ".env.local")) };
const url = process.env.NEXT_PUBLIC_SUPABASE_URL || fileEnv.NEXT_PUBLIC_SUPABASE_URL || fileEnv.SUPABASE_URL;
const key = process.env.SUPABASE_SERVICE_ROLE_KEY || fileEnv.SUPABASE_SERVICE_ROLE_KEY;
if (!url || !key) throw new Error("Configured Supabase URL/service role key not found");
const db = createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });

async function allAssets() {
  const rows: Array<{ id: string; mime_type: string | null; file_extension: string | null }> = [];
  for (let start = 0; ; start += 1000) {
    const { data, error } = await db.from("assets").select("id,mime_type,file_extension").range(start, start + 999);
    if (error) throw error;
    rows.push(...(data ?? []));
    if ((data?.length ?? 0) < 1000) return rows;
  }
}

async function count(table: string): Promise<number | null> {
  const { count, error } = await db.from(table).select("*", { count: "exact", head: true });
  if (error) {
    if (error.code === "42P01" || error.code === "PGRST205") return null;
    throw new Error(`${table}: ${error.code} ${error.message}`);
  }
  return count ?? 0;
}

async function countState(table: string, column: string, states: string[]): Promise<Record<string, number> | null> {
  const out: Record<string, number> = {};
  for (const state of states) {
    const { count, error } = await db.from(table).select("*", { count: "exact", head: true }).eq(column, state);
    if (error) return null;
    out[state] = count ?? 0;
  }
  return out;
}

const assets = await allAssets();
const images = assets.filter((a) => a.mime_type?.startsWith("image/"));
const videos = assets.filter((a) => a.mime_type?.startsWith("video/"));
const documents = assets.filter((a) => !a.mime_type?.startsWith("image/") && !a.mime_type?.startsWith("video/"));
const distribution = (field: "mime_type" | "file_extension") => Object.entries(assets.reduce<Record<string, number>>((out, row) => {
  const key = row[field] || "(null)"; out[key] = (out[key] || 0) + 1; return out;
}, {})).sort((a, b) => b[1] - a[1]);
const semantic = await count("asset_semantic_index");
const qwen = await count("asset_embeddings");
const visual = await count("asset_visual_embeddings");
const jobs = await count("asset_visual_index_jobs");
const jobStates = jobs === null ? null : await countState("asset_visual_index_jobs", "status", ["QUEUED", "PROCESSING", "INDEXED", "RETRY", "FAILED", "NOT_APPLICABLE"]);
const report = {
  generated_at: new Date().toISOString(), total_assets: assets.length, image_assets: images.length,
  video_assets: videos.length, document_assets: documents.length, supported_visual_assets: images.length + videos.length,
  existing_semantic_rows: semantic, existing_qwen_embedding_rows: qwen, existing_visual_embedding_rows: visual ?? 0,
  visual_assets_not_indexed: images.length + videos.length - (visual ?? 0), failed_visual_jobs: jobStates?.FAILED ?? 0,
  queued_visual_jobs: jobStates?.QUEUED ?? 0, visual_job_states: jobStates, visual_schema_present: visual !== null,
  visual_job_schema_present: jobs !== null, mime_distribution: distribution("mime_type"), extension_distribution: distribution("file_extension")
};
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
