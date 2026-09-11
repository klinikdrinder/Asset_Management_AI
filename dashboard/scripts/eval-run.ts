/**
 * Run the gold set through the real search pipeline and score it. Reports overall relevance metrics
 * (P@5, R@10, MRR, MAP, nDCG@10, hit-rate), a per-query breakdown, and per-channel attribution
 * (which retrieval channels land the relevant hits — the "which channel earns its place" question).
 *
 * Requires the search to actually run: the embedding sidecar (EMBED_SERVICE_URL) with e5 + OpenCLIP
 * models loaded, plus SUPABASE_SERVICE_ROLE_KEY. Provide an app user to authorise retrieval:
 *   --user=<uuid>  (or EVAL_USER_ID) — an admin who can_view_clinical for the widest coverage.
 *
 * NOTE: retrieval is RLS/ACL-bounded. Until the is_clinical backfill runs, only ~30 assets are
 * visible, so recall is capped — the report prints the visible-corpus caveat.
 *
 *   cross-env NODE_OPTIONS=--conditions=react-server tsx scripts/eval-run.ts --user=<uuid>
 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { createClient } from "@supabase/supabase-js";
import { executeCanonicalSearch } from "../db/canonical-production-retriever";
import { scoreCase, aggregate, type GoldCase, type CaseScore } from "../db/eval-metrics";

const K = 20;
const GOLD = path.join(process.cwd(), "..", "reports", "eval", "gold-set.json");
const OUT_JSON = path.join(process.cwd(), "..", "reports", "eval", "eval-report.json");
const OUT_MD = path.join(process.cwd(), "..", "reports", "eval", "eval-report.md");

function loadEnvLocal() {
  try {
    for (const line of readFileSync(path.join(process.cwd(), ".env.local"), "utf8").split(/\r?\n/)) {
      const m = /^([A-Z0-9_]+)=(.*)$/.exec(line.trim());
      if (m && !(m[1] in process.env)) process.env[m[1]] = m[2];
    }
  } catch { /* rely on ambient env */ }
}

const argv = process.argv.slice(2);
const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

async function main() {
  loadEnvLocal();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL, key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw new Error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing");
  const userId = (argv.find((a) => a.startsWith("--user=")) ?? "").split("=")[1] || process.env.EVAL_USER_ID;
  if (!userId) throw new Error("Provide an authorising app user: --user=<uuid> (or EVAL_USER_ID)");

  const supa = createClient(url, key, { auth: { persistSession: false } });
  const gold = JSON.parse(readFileSync(GOLD, "utf8")) as GoldCase[];
  console.log(`[eval] scoring ${gold.length} gold cases (k=${K}) as user ${userId}`);

  const scores: CaseScore[] = [];
  const channelHits = new Map<string, number>();
  const failures: string[] = [];

  for (const gc of gold) {
    let retrieved: string[] = [];
    try {
      const r = await executeCanonicalSearch(supa, { query: gc.query, userId, requestedCount: K });
      const ranked = (r.eligible_candidates ?? []) as Array<{ asset_id: string; channels?: { channel: string }[] }>;
      retrieved = ranked.map((x) => x.asset_id);
      const relevant = new Set(gc.relevantAssetIds);
      for (const cand of ranked) if (relevant.has(cand.asset_id)) for (const h of cand.channels ?? []) channelHits.set(h.channel, (channelHits.get(h.channel) ?? 0) + 1);
    } catch (e) {
      failures.push(`${gc.id}: ${e instanceof Error ? e.message : e}`);
    }
    scores.push(scoreCase(gc, retrieved, 10));
  }

  const agg = aggregate(scores);
  const channels = [...channelHits.entries()].sort((a, b) => b[1] - a[1]);
  const report = { generatedFor: userId, k: K, aggregate: agg, channelAttribution: Object.fromEntries(channels), failures, cases: scores };
  mkdirSync(path.dirname(OUT_JSON), { recursive: true });
  writeFileSync(OUT_JSON, JSON.stringify(report, null, 2));

  const md = [
    `# Search eval report`,
    ``,
    `Cases: ${agg.cases} · k=${K} · user ${userId}`,
    failures.length ? `\n> ${failures.length} case(s) errored (search unavailable?). Metrics cover the rest.\n` : ``,
    `> Retrieval is ACL-bounded — until the is_clinical backfill runs, recall is capped by the visible corpus.`,
    ``,
    `| Metric | Value |`,
    `|---|---|`,
    `| Mean P@5 | ${pct(agg.meanPrecisionAt5)} |`,
    `| Mean R@10 | ${pct(agg.meanRecallAt10)} |`,
    `| MRR | ${agg.mrr.toFixed(3)} |`,
    `| MAP | ${agg.map.toFixed(3)} |`,
    `| Mean nDCG@10 | ${agg.meanNdcgAt10.toFixed(3)} |`,
    `| Hit-rate@10 | ${pct(agg.hitRateAt10)} |`,
    ``,
    `## Per-channel attribution (relevant hits touched)`,
    ``,
    channels.length ? channels.map(([c, n]) => `- ${c}: ${n}`).join("\n") : `_none_`,
    ``,
    `## Per-query`,
    ``,
    `| Query | Rel | Ret | P@5 | R@10 | RR | nDCG@10 | Hit |`,
    `|---|--:|--:|--:|--:|--:|--:|:--:|`,
    ...scores.map((s) => `| ${s.query} | ${s.relevant} | ${s.retrieved} | ${pct(s.precisionAtK)} | ${pct(s.recallAtK)} | ${s.reciprocalRank.toFixed(2)} | ${s.ndcgAtK.toFixed(2)} | ${s.hit ? "✓" : "·"} |`),
    ``,
  ].join("\n");
  writeFileSync(OUT_MD, md);
  console.log(`[eval] MAP=${agg.map.toFixed(3)} MRR=${agg.mrr.toFixed(3)} nDCG@10=${agg.meanNdcgAt10.toFixed(3)} hit@10=${pct(agg.hitRateAt10)} -> ${OUT_MD}`);
  if (failures.length) console.warn(`[eval] ${failures.length} case(s) errored — is the embedding sidecar running with models?`);
}

main().catch((e) => { console.error(e); process.exit(1); });
