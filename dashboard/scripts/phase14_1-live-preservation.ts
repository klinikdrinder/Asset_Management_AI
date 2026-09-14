import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
function env(file: string) {
  try {
    return Object.fromEntries(
      readFileSync(file, "utf8")
      .replace(/^\uFEFF/, "")
      .split(/\r?\n/)
        .flatMap((x) => {
          const m = x.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
          return m ? [[m[1], m[2].trim().replace(/^(['"])(.*)\1$/, "$2")]] : [];
        }),
    );
  } catch {
    return {};
  }
}
const root = path.resolve(process.cwd(), ".."),
  out = path.join(root, "reports", "semantic-search", "phase14_1"),
  a = env(path.join(root, ".env.local")),
  b = env(path.join(process.cwd(), ".env.local")),
  url = b.NEXT_PUBLIC_SUPABASE_URL || a.NEXT_PUBLIC_SUPABASE_URL,
  token = [
    a.SUPABASE_DASHBOARD_ACCESS_TOKEN,
    b.SUPABASE_DASHBOARD_ACCESS_TOKEN,
  ].find((x) => x?.startsWith("sbp_"));
if (!url || !token) throw new Error("Supabase configuration unavailable");
const ref = new URL(url).hostname.split(".")[0],
  tables = [
    "assets",
    "semantic_assertions",
    "semantic_assertion_evidence",
    "asset_scenes",
    "asset_events",
    "asset_keyframes",
    "asset_transcript_chunks",
    "ocr_observations",
    "semantic_narratives",
    "asset_search_concepts_v2",
    "semantic_embeddings",
    "semantic_review_decisions",
    "gold_standard_assets",
    "search_queries",
  ];
const response = await fetch(
  `https://api.supabase.com/v1/projects/${ref}/database/query`,
  {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query: `select t.table_name,(xpath('/row/c/text()',query_to_xml(format('select count(*) c from public.%I',t.table_name),false,true,'')))[1]::text::bigint row_count from(values ${tables.map((x) => `('${x}')`).join(",")})t(table_name) order by 1`,
    }),
  },
);
if (!response.ok)
  throw new Error(`${response.status}: ${await response.text()}`);
const rows = (await response.json()) as any[],
  current = Object.fromEntries(
    rows.map((x) => [x.table_name, Number(x.row_count)]),
  ),
  baseline = {
    assets: 881,
    semantic_assertions: 333,
    semantic_assertion_evidence: 270,
    asset_scenes: 312,
    asset_events: 22,
    asset_keyframes: 345,
    asset_transcript_chunks: 14,
    ocr_observations: 19,
    semantic_narratives: 37,
    asset_search_concepts_v2: 270,
    semantic_embeddings: 106,
    semantic_review_decisions: 0,
    gold_standard_assets: 0,
    search_queries: 0,
  },
  comparison = tables.map((table) => ({
    table,
    before: (baseline as any)[table],
    after: current[table],
    delta: current[table] - (baseline as any)[table],
  })),
  report = {
    generated_at: new Date().toISOString(),
    status: comparison.every((x) => x.delta === 0) ? "PASS" : "FAIL",
    semantic_data_changed: comparison
      .filter((x) => !x.table.startsWith("search_"))
      .some((x) => x.delta !== 0),
    production_benchmark_queries_added: current.search_queries,
    embeddings: { before: 106, after: current.semantic_embeddings },
    comparison,
  };
writeFileSync(
  path.join(out, "phase14_1_database_preservation.json"),
  JSON.stringify(report, null, 2) + "\n",
);
for (const name of ["phase14_1_summary.json", "phase14_1_validation.json"]) {
  const file = path.join(out, name),
    obj = JSON.parse(readFileSync(file, "utf8"));
  obj.database = report;
  writeFileSync(file, JSON.stringify(obj, null, 2) + "\n");
}
console.log(JSON.stringify(report, null, 2));
