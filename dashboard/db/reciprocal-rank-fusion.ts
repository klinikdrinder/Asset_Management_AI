// Reciprocal Rank Fusion — a LOGGED signal, not the primary ranker.
//
// The deterministic reranker (Phase 19) remains authoritative. RRF is computed alongside it so
// we can measure which channels actually earn their placement (spec: "Log per-channel ranks so
// we can measure which channel is actually earning its place"). It also derives the per-channel
// score columns on search_results (filename/structured/semantic/visual/transcript) for tuning.
//
// RRF(asset) = Σ_channel 1 / (K + rank_of_asset_within_that_channel). K=60 is the standard
// constant. Ranks are computed within the supplied candidate set, so pass the full ranked set.

export const RRF_VERSION = "kdi_rrf_v1";
const K = 60;

// Raw retrieval channel -> coarse family used for the search_results score columns.
const FAMILY: Record<string, string> = {
  FILENAME_LITERAL: "filename",
  STRUCTURED_CANONICAL: "structured", EXPANDED_STRUCTURED: "structured", STRUCTURED_FALSE: "structured",
  TEXT_ASSET: "semantic", TEXT_SCENE: "semantic", TEXT_EVENT: "semantic", TEXT_OCR: "semantic",
  FULL_TEXT: "semantic", OCR_LITERAL: "semantic",
  TEXT_TRANSCRIPT: "transcript", TRANSCRIPT_LITERAL: "transcript",
  VISUAL_ASSET: "visual", VISUAL_SCENE: "visual", VISUAL_KEYFRAME: "visual",
};

type ChannelHit = { channel: string; normalized_channel_score?: number; raw_score?: number };
type FusionCandidate = { asset_id: string; channels?: ChannelHit[] };
export type RrfResult = { rrf: number; channelScores: Record<string, number>; channelRanks: Record<string, number> };

export function computeReciprocalRankFusion(candidates: FusionCandidate[]): Map<string, RrfResult> {
  const bestByChannel = new Map<string, Map<string, number>>(); // channel -> asset -> best score
  const familyBest = new Map<string, Record<string, number>>(); // asset -> family -> best score

  for (const c of candidates) {
    const fam: Record<string, number> = {};
    for (const h of c.channels ?? []) {
      const score = Number(h.normalized_channel_score ?? h.raw_score ?? 0);
      let m = bestByChannel.get(h.channel);
      if (!m) { m = new Map(); bestByChannel.set(h.channel, m); }
      m.set(c.asset_id, Math.max(m.get(c.asset_id) ?? 0, score));
      const f = FAMILY[h.channel];
      if (f) fam[f] = Math.max(fam[f] ?? 0, score);
    }
    familyBest.set(c.asset_id, fam);
  }

  // Rank assets within each channel by their best score in that channel.
  const ranksByChannel = new Map<string, Map<string, number>>();
  for (const [channel, m] of bestByChannel) {
    const ordered = [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    const rm = new Map<string, number>();
    ordered.forEach(([asset], i) => rm.set(asset, i + 1));
    ranksByChannel.set(channel, rm);
  }

  const out = new Map<string, RrfResult>();
  for (const c of candidates) {
    let rrf = 0;
    const channelRanks: Record<string, number> = {};
    for (const [channel, rm] of ranksByChannel) {
      const r = rm.get(c.asset_id);
      if (r) { rrf += 1 / (K + r); channelRanks[channel] = r; }
    }
    out.set(c.asset_id, { rrf, channelScores: familyBest.get(c.asset_id) ?? {}, channelRanks });
  }
  return out;
}
