import test from "node:test";
import assert from "node:assert/strict";
import { precisionAtK, recallAtK, reciprocalRank, averagePrecision, ndcgAtK, scoreCase, aggregate } from "../db/eval-metrics";

const close = (a: number, b: number, msg?: string) => assert.ok(Math.abs(a - b) < 1e-4, `${msg ?? ""} expected ${b}, got ${a}`);
const S = (...ids: string[]) => new Set(ids);

test("precision/recall/RR basics", () => {
  close(precisionAtK(["a", "b", "c"], S("a"), 3), 1 / 3, "P@3");
  close(recallAtK(["a", "b"], S("a", "c"), 10), 0.5, "R@10");
  close(reciprocalRank(["x", "y", "a"], S("a")), 1 / 3, "RR");
  assert.equal(reciprocalRank(["x", "y"], S("a")), 0, "RR no hit");
});

test("perfect ranking scores 1.0", () => {
  close(averagePrecision(["a", "b"], S("a", "b")), 1, "AP perfect");
  close(ndcgAtK(["a", "b"], S("a", "b"), 2), 1, "nDCG perfect");
});

test("empty relevant set yields zeros", () => {
  const empty = S();
  assert.equal(recallAtK(["a"], empty, 5), 0);
  assert.equal(averagePrecision(["a"], empty), 0);
  assert.equal(ndcgAtK(["a"], empty, 5), 0);
});

test("mixed ranking has known values", () => {
  const s = scoreCase({ id: "1", query: "q", relevantAssetIds: ["b", "d"], source: "curated" }, ["a", "b", "c", "d", "e"], 10);
  close(s.precisionAtK, 0.4, "P@5");
  close(s.recallAtK, 1, "R@10");
  close(s.reciprocalRank, 0.5, "RR");
  close(s.averagePrecision, 0.5, "AP");
  close(s.ndcgAtK, 0.6509, "nDCG@10");
  assert.equal(s.hit, true);
});

test("aggregate averages across cases", () => {
  const a = aggregate([
    scoreCase({ id: "1", query: "q1", relevantAssetIds: ["a"], source: "curated" }, ["a"], 10),
    scoreCase({ id: "2", query: "q2", relevantAssetIds: ["b"], source: "curated" }, ["x", "y"], 10),
  ]);
  assert.equal(a.cases, 2);
  close(a.mrr, 0.5, "MRR = mean(1, 0)");
  close(a.hitRateAt10, 0.5, "hit rate");
});
