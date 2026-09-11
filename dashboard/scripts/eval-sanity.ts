/**
 * Hand sanity-check: run a handful of realistic queries through the real engine and print the
 * top-5 with per-channel "why matched" + matched concepts, so a human can judge whether the
 * results are actually right (not just scored).
 *
 * Shows PRE-authorization retrieval (r.retrieved) because the RLS gate hides is_clinical=NULL
 * assets from everyone — the authorized view is capped at the 30 classified assets. This reflects
 * what the ENGINE finds; the ACL cap is a separate, known issue.
 *
 * Needs the embedding sidecar (EMBED_SERVICE_URL) + SUPABASE_SERVICE_ROLE_KEY. Run from dashboard/:
 *   NODE_OPTIONS=--conditions=react-server npx tsx scripts/eval-sanity.ts
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { createClient } from "@supabase/supabase-js";
import { executeCanonicalSearch } from "../db/canonical-production-retriever";

const USER = "3938c364-0250-40a1-8db6-9ef704ca0122"; // super-admin (for the authorize step; we read pre-auth)
const QUERIES = [
  "doctor explaining hair transplant procedure",
  "frontal hairline thinning before treatment",
  "clinician implanting grafts",
  "patient consultation room",
  "video with visible text on screen",
];

function loadEnvLocal() {
  try {
    for (const line of readFileSync(path.join(process.cwd(), ".env.local"), "utf8").split(/\r?\n/)) {
      const m = /^([A-Z0-9_]+)=(.*)$/.exec(line.trim());
      if (m && !(m[1] in process.env)) process.env[m[1]] = m[2];
    }
  } catch { /* ambient env */ }
}

type Hit = { channel: string; normalized_channel_score?: number; raw_score?: number; channel_rank?: number; matched_concepts?: string[] };
type Cand = { asset_id: string; filename?: string | null; channels?: Hit[]; matched_hard_constraints?: string[]; matched_strong_requirements?: string[]; matched_preferences?: string[] };

function topChannels(c: Cand): string {
  const best = new Map<string, { score: number; rank: number | null }>();
  for (const h of c.channels ?? []) {
    const score = Number(h.normalized_channel_score ?? h.raw_score ?? 0);
    const cur = best.get(h.channel);
    if (!cur || score > cur.score) best.set(h.channel, { score, rank: h.channel_rank ?? null });
  }
  return [...best.entries()].sort((a, b) => b[1].score - a[1].score).slice(0, 4)
    .map(([ch, v]) => `${ch}(${v.score.toFixed(2)}${v.rank ? `#${v.rank}` : ""})`).join(" ");
}

function concepts(c: Cand): string {
  const set = new Set<string>([
    ...(c.matched_hard_constraints ?? []), ...(c.matched_strong_requirements ?? []), ...(c.matched_preferences ?? []),
    ...(c.channels ?? []).flatMap((h) => h.matched_concepts ?? []),
  ].filter((x) => x && x !== ""));
  return set.size ? [...set].join(", ") : "—";
}

async function main() {
  loadEnvLocal();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL, key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw new Error("SUPABASE creds missing");
  const supa = createClient(url, key, { auth: { persistSession: false } });

  for (const query of QUERIES) {
    console.log(`\n================================================================`);
    console.log(`QUERY: ${query}`);
    let r: any;
    try { r = await executeCanonicalSearch(supa, { query, userId: USER, requestedCount: 5 }); }
    catch (e) { console.log(`  ERROR: ${e instanceof Error ? e.message : e}`); continue; }
    const parsed = r.diagnostics?.parsed_intent;
    console.log(`  parsed intent: ${JSON.stringify(parsed)}  concepts=${JSON.stringify(r.diagnostics?.canonical_concepts ?? [])}`);
    const cands = (r.retrieved?.candidates ?? []).slice(0, 5) as Cand[];
    const authorized = (r.eligible_candidates ?? []).length;
    console.log(`  retrieved=${(r.retrieved?.candidates ?? []).length}  authorized(ACL)=${authorized}  showing top ${cands.length} (pre-ACL):`);
    cands.forEach((c, i) => {
      console.log(`   ${i + 1}. ${c.filename ?? c.asset_id}`);
      console.log(`      why: ${topChannels(c)}`);
      console.log(`      concepts: ${concepts(c)}`);
    });
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
