/**
 * Generate a weak-label gold set for search eval from the genuine structured data: for each real
 * canonical concept code (canonical_concept_code <> layer_id) that is OBSERVED on a reasonable
 * number of assets, the "relevant" set is exactly those assets, and the query is the concept's
 * human name. These are WEAK labels (derived from the same assertions the search indexes), useful
 * for regression tracking and channel comparison — not a substitute for human-curated gold.
 *
 * A hand-curated file at reports/eval/gold-set.curated.json (same shape) is merged in if present.
 *
 * Read-only (SELECT via the Supabase Management API). Run from dashboard/:
 *   cross-env NODE_OPTIONS=--conditions=react-server tsx scripts/eval-generate-gold.ts
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import path from "node:path";
import type { GoldCase } from "../db/eval-metrics";

const REF = "wcqqjpndlwsvatjuqnol";
const MIN_ASSETS = 3;   // specific enough to be a meaningful query
const MAX_ASSETS = 80;  // not so broad the concept is trivially everywhere
const OUT = path.join(process.cwd(), "..", "reports", "eval", "gold-set.json");
const CURATED = path.join(process.cwd(), "..", "reports", "eval", "gold-set.curated.json");

function loadEnvLocal() {
  try {
    for (const line of readFileSync(path.join(process.cwd(), ".env.local"), "utf8").split(/\r?\n/)) {
      const m = /^([A-Z0-9_]+)=(.*)$/.exec(line.trim());
      if (m && !(m[1] in process.env)) process.env[m[1]] = m[2];
    }
  } catch { /* rely on ambient env */ }
}

async function query<T>(sql: string, token: string): Promise<T[]> {
  const r = await fetch(`https://api.supabase.com/v1/projects/${REF}/database/query`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ query: sql }),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T[]>;
}

const prettyCode = (code: string) => code.toLowerCase().replace(/_/g, " ");

async function main() {
  loadEnvLocal();
  const token = process.env.SUPABASE_DASHBOARD_ACCESS_TOKEN;
  if (!token) throw new Error("SUPABASE_DASHBOARD_ACCESS_TOKEN missing (dashboard/.env.local)");

  const grouped = await query<{ code: string; assets: string[]; n: number }>(`
    SELECT sa.canonical_concept_code AS code,
           array_agg(DISTINCT sa.asset_id) AS assets,
           count(DISTINCT sa.asset_id) AS n
    FROM semantic_assertions sa
    WHERE sa.active AND sa.semantic_state = 'OBSERVED'
      AND sa.canonical_concept_code IS NOT NULL
      AND sa.canonical_concept_code <> sa.layer_id
      AND sa.superseded_by IS NULL
    GROUP BY 1
    HAVING count(DISTINCT sa.asset_id) BETWEEN ${MIN_ASSETS} AND ${MAX_ASSETS}
    ORDER BY n DESC;`, token);

  const names = await query<{ code: string; name: string }>(`
    SELECT code, name FROM treatments
    UNION ALL SELECT code, name FROM anatomy_terms
    UNION ALL SELECT code, name FROM actions
    UNION ALL SELECT code, label FROM clinical_observation_definitions
    UNION ALL SELECT code, name FROM locations
    UNION ALL SELECT code, name FROM relationship_types;`, token);
  const nameByCode = new Map(names.map((r) => [r.code, r.name]));

  const generated: GoldCase[] = grouped.map((g) => ({
    id: `weak-${g.code}`,
    query: nameByCode.get(g.code) ?? prettyCode(g.code),
    relevantAssetIds: g.assets,
    note: `${g.n} OBSERVED assets carry ${g.code}`,
    source: "structured_weak",
  }));

  let curated: GoldCase[] = [];
  if (existsSync(CURATED)) {
    try { curated = JSON.parse(readFileSync(CURATED, "utf8")) as GoldCase[]; } catch { console.warn("[eval] curated gold-set unreadable, ignoring"); }
  }
  const merged = [...curated, ...generated];

  mkdirSync(path.dirname(OUT), { recursive: true });
  writeFileSync(OUT, JSON.stringify(merged, null, 2));
  console.log(`[eval] gold set written: ${merged.length} cases (${generated.length} weak, ${curated.length} curated) -> ${OUT}`);
  generated.slice(0, 12).forEach((c) => console.log(`  ${c.query.padEnd(28)} ${c.relevantAssetIds.length} assets  (${c.id})`));
}

main().catch((e) => { console.error(e); process.exit(1); });
