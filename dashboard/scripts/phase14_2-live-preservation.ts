import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

function env(file: string) {
  try {
    return Object.fromEntries(readFileSync(file, "utf8").replace(/^\uFEFF/, "").split(/\r?\n/).flatMap((line) => {
      const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
      return match ? [[match[1], match[2].trim().replace(/^(['"])(.*)\1$/, "$2")]] : [];
    }));
  } catch { return {}; }
}

const root = path.resolve(process.cwd(), "..");
const out = path.join(root, "reports", "semantic-search", "phase14_2");
const rootEnv: any = env(path.join(root, ".env.local"));
const appEnv: any = env(path.join(process.cwd(), ".env.local"));
const url = appEnv.NEXT_PUBLIC_SUPABASE_URL || rootEnv.NEXT_PUBLIC_SUPABASE_URL;
const token = [rootEnv.SUPABASE_DASHBOARD_ACCESS_TOKEN, appEnv.SUPABASE_DASHBOARD_ACCESS_TOKEN].find((value) => value?.startsWith("sbp_"));
if (!url || !token) throw new Error("Supabase configuration unavailable");

const ref = new URL(url).hostname.split(".")[0];
const baseline: Record<string, number> = {
  assets: 881, semantic_assertions: 333, semantic_assertion_evidence: 270,
  asset_scenes: 312, asset_events: 22, asset_keyframes: 345,
  asset_transcript_chunks: 14, ocr_observations: 19, semantic_narratives: 37,
  asset_search_concepts_v2: 270, semantic_embeddings: 106,
  semantic_review_decisions: 0, gold_standard_assets: 0, search_queries: 0,
};
const tables = Object.keys(baseline);
const response = await fetch(`https://api.supabase.com/v1/projects/${ref}/database/query`, {
  method: "POST",
  headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  body: JSON.stringify({ query: `select t.table_name,(xpath('/row/c/text()',query_to_xml(format('select count(*) c from public.%I',t.table_name),false,true,'')))[1]::text::bigint row_count from(values ${tables.map((table) => `('${table}')`).join(",")})t(table_name) order by 1` }),
});
if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
const rows = await response.json() as Array<{ table_name: string; row_count: number | string }>;
const current = Object.fromEntries(rows.map((row) => [row.table_name, Number(row.row_count)]));
const comparison = tables.map((table) => ({ table, before: baseline[table], after: current[table], delta: current[table] - baseline[table] }));
const report = {
  generated_at: new Date().toISOString(),
  status: comparison.every((row) => row.delta === 0) ? "PASS" : "FAIL",
  semantic_data_changed: comparison.filter((row) => row.table !== "search_queries").some((row) => row.delta !== 0),
  production_benchmark_queries_added: current.search_queries,
  embeddings: { before: 106, after: current.semantic_embeddings },
  comparison,
};
writeFileSync(path.join(out, "phase14_2_database_preservation.json"), JSON.stringify(report, null, 2) + "\n");
for (const name of ["phase14_2_summary.json", "phase14_2_validation.json"]) {
  const file = path.join(out, name);
  const content = JSON.parse(readFileSync(file, "utf8"));
  content.database = report;
  writeFileSync(file, JSON.stringify(content, null, 2) + "\n");
}
console.log(JSON.stringify(report, null, 2));
