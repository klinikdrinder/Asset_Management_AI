import { readFileSync } from "node:fs";
import path from "node:path";

function envFile(file: string) {
  try { return Object.fromEntries(readFileSync(file, "utf8").split(/\r?\n/).flatMap((line) => {
    const m = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/); return m ? [[m[1], m[2].trim().replace(/^(['"])(.*)\1$/, "$2")]] : [];
  })); } catch { return {}; }
}
const root = path.resolve(process.cwd(), "..");
const env = { ...envFile(path.join(root, ".env")), ...envFile(path.join(root, ".env.local")), ...envFile(path.join(process.cwd(), ".env.local")) };
const url = env.NEXT_PUBLIC_SUPABASE_URL || env.SUPABASE_URL;
const key = env.SUPABASE_SERVICE_ROLE_KEY;
if (!url || !key) throw new Error("Supabase configuration missing");
const response = await fetch(`${url}/rest/v1/`, { headers: { apikey: key, Authorization: `Bearer ${key}` } });
if (!response.ok) throw new Error(`OpenAPI request failed: ${response.status}`);
const schema = await response.json() as { definitions?: Record<string, unknown>; paths?: Record<string, unknown> };
const names = ["asset_visual_embeddings", "asset_visual_index_jobs"];
process.stdout.write(JSON.stringify({
  definitions: Object.fromEntries(names.map((name) => [name, schema.definitions?.[name] ?? null])),
  rpc_paths: Object.fromEntries(Object.entries(schema.paths ?? {}).filter(([name]) => /visual/i.test(name)))
}, null, 2));
