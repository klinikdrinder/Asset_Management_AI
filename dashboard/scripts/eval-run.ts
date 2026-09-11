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
// The RLS gate hides is_clinical=NULL assets from everyone (no super-admin bypass), so the
// authorized pipeline is capped at the classified corpus. --ignore-acl scores the engine's
// pre-authorization retrieval instead, to smoke-test retrieval quality independent of the ACL.
const IGNORE_ACL = argv.includes("--ignore-acl");
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
  const channelHits = new Map<string, number>();          // channel -> relevant hits it touched
  const channelQueries = new Map<string, Set<string>>();  // channel -> gold ids where it appeared at all
  const failures: string[] = [];

  for (const gc of gold) {
    let retrieved: string[] = [];
    try {
      const r = await executeCanonicalSearch(supa, { query: gc.query, userId, requestedCount: K });
      const ranked = ((IGNORE_ACL ? r.retrieved?.candidates : r.eligible_candidates) ?? []) as Array<{ asset_id: string; channels?: { channel: string }[] }>;
      retrieved = ranked.map((x) => x.asset_id);
      const relevant = new Set(gc.relevantAssetIds);
      for (const cand of ranked) for (const h of cand.channels ?? []) {
        let qs = channelQueries.get(h.channel); if (!qs) { qs = new Set(); channelQueries.set(h.channel, qs); } qs.add(gc.id);
        if (relevant.has(cand.asset_id)) channelHits.set(h.channel, (channelHits.get(h.channel) ?? 0) + 1);
      }
    } catch (e) {
      failures.push(`${gc.id}: ${e instanceof Error ? e.message : e}`);
    }
    scores.push(scoreCase(gc, retrieved, 10));
  }

  const agg = aggregate(scores);
  const channels = [...channelHits.entries()].sort((a, b) => b[1] - a[1]);
  const channelQueryContribution = [...channelQueries.entries()].map(([c, s]) => [c, s.size] as [string, number]).sort((a, b) => b[1] - a[1]);
  const STRUCTURED = ["STRUCTURED_CANONICAL", "EXPANDED_STRUCTURED", "STRUCTURED_FALSE"];
  const structuredQueries = new Set<string>();
  for (const c of STRUCTURED) for (const q of channelQueries.get(c) ?? []) structuredQueries.add(q);
  const report = { generatedFor: userId, k: K, mode: IGNORE_ACL ? "PRE_AUTH_RETRIEVAL" : "AUTHORIZED", aggregate: agg, channelAttribution: Object.fromEntries(channels), channelQueryContribution: Object.fromEntries(channelQueryContribution), structuredChannelQueryCount: structuredQueries.size, failures, cases: scores };
  mkdirSync(path.dirname(OUT_JSON), { recursive: true });
  writeFileSync(OUT_JSON, JSON.stringify(report, null, 2));

  const md = [
    `# Search eval report`,
    ``,
    `Cases: ${agg.cases} · k=${K} · user ${userId} · mode ${IGNORE_ACL ? "PRE_AUTH_RETRIEVAL" : "AUTHORIZED"}`,
    failures.length ? `\n> ${failures.length} case(s) errored (search unavailable?). Metrics cover the rest.\n` : ``,
    `> mode=AUTHORIZED is ACL-bounded (is_clinical=NULL hidden from everyone incl. super-admin) — recall is capped until the backfill runs. mode=PRE_AUTH_RETRIEVAL scores the engine before the ACL gate.`,
    `> Structured channel contributed to ${structuredQueries.size}/${agg.cases} queries.`,
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
    `## Per-channel query contribution (queries where the channel appeared at all)`,
    ``,
    channelQueryContribution.length ? channelQueryContribution.map(([c, n]) => `- ${c}: ${n}`).join("\n") : `_none_`,
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
