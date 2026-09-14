// Relevance metrics for the search eval harness. Pure functions over a ranked list of retrieved
// asset ids and the set of relevant asset ids for a query, so they are unit-testable with no DB,
// models, or network. Binary relevance (an asset either is or isn't in the gold set).

export type GoldCase = {
  id: string;
  query: string;
  relevantAssetIds: string[];
  note?: string;
  source: "structured_weak" | "curated";
};

export type CaseScore = {
  id: string;
  query: string;
  relevant: number;
  retrieved: number;
  precisionAtK: number;
  recallAtK: number;
  reciprocalRank: number;
  averagePrecision: number;
  ndcgAtK: number;
  hit: boolean;
};

const topHits = (retrieved: string[], relevant: Set<string>, k: number) =>
  retrieved.slice(0, k).filter((id) => relevant.has(id)).length;

/** Fraction of the top-k that are relevant (divided by k, so short result lists are penalised). */
export function precisionAtK(retrieved: string[], relevant: Set<string>, k: number): number {
  if (k <= 0) return 0;
  return topHits(retrieved, relevant, k) / k;
}

/** Fraction of all relevant assets that appear in the top-k. */
export function recallAtK(retrieved: string[], relevant: Set<string>, k: number): number {
  if (relevant.size === 0) return 0;
  return topHits(retrieved, relevant, k) / relevant.size;
}

/** 1 / rank of the first relevant hit (0 if none). */
export function reciprocalRank(retrieved: string[], relevant: Set<string>): number {
  const idx = retrieved.findIndex((id) => relevant.has(id));
  return idx === -1 ? 0 : 1 / (idx + 1);
}

/** Average precision over the full retrieved list, normalised by the number of relevant assets. */
export function averagePrecision(retrieved: string[], relevant: Set<string>): number {
  if (relevant.size === 0) return 0;
  let hits = 0, sum = 0;
  retrieved.forEach((id, i) => { if (relevant.has(id)) { hits++; sum += hits / (i + 1); } });
  return sum / relevant.size;
}

/** Normalised discounted cumulative gain at k with binary gains. */
export function ndcgAtK(retrieved: string[], relevant: Set<string>, k: number): number {
  if (relevant.size === 0 || k <= 0) return 0;
  let dcg = 0;
  retrieved.slice(0, k).forEach((id, i) => { if (relevant.has(id)) dcg += 1 / Math.log2(i + 2); });
  let idcg = 0;
  for (let i = 0; i < Math.min(k, relevant.size); i++) idcg += 1 / Math.log2(i + 2);
  return idcg === 0 ? 0 : dcg / idcg;
}

export function scoreCase(gold: GoldCase, retrieved: string[], k = 10): CaseScore {
  const relevant = new Set(gold.relevantAssetIds);
  return {
    id: gold.id,
    query: gold.query,
    relevant: relevant.size,
    retrieved: retrieved.length,
    precisionAtK: precisionAtK(retrieved, relevant, Math.min(k, 5)),
    recallAtK: recallAtK(retrieved, relevant, k),
    reciprocalRank: reciprocalRank(retrieved, relevant),
    averagePrecision: averagePrecision(retrieved, relevant),
    ndcgAtK: ndcgAtK(retrieved, relevant, k),
    hit: topHits(retrieved, relevant, k) > 0,
  };
}

export type AggregateScore = {
  cases: number;
  meanPrecisionAt5: number;
  meanRecallAt10: number;
  mrr: number;
  map: number;
  meanNdcgAt10: number;
  hitRateAt10: number;
};

const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);

export function aggregate(scores: CaseScore[]): AggregateScore {
  return {
    cases: scores.length,
    meanPrecisionAt5: mean(scores.map((s) => s.precisionAtK)),
    meanRecallAt10: mean(scores.map((s) => s.recallAtK)),
    mrr: mean(scores.map((s) => s.reciprocalRank)),
    map: mean(scores.map((s) => s.averagePrecision)),
    meanNdcgAt10: mean(scores.map((s) => s.ndcgAtK)),
    hitRateAt10: mean(scores.map((s) => (s.hit ? 1 : 0))),
  };
}
