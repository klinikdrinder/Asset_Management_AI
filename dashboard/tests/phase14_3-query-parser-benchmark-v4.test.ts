import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import path from "node:path";

test("V4 benchmark is frozen, English-only, unique, and correctly split", () => {
  const benchmark = JSON.parse(readFileSync(path.resolve(process.cwd(), "..", "config", "semantic-search", "benchmarks", "kdi_query_parser_benchmark_v4.json"), "utf8"));
  assert.equal(benchmark.benchmark_version, "kdi_query_parser_benchmark_v4");
  assert.equal(benchmark.frozen, true);
  assert.equal(benchmark.cases.length, 150);
  assert.equal(benchmark.cases.filter((c: any) => c.split === "DEV").length, 90);
  assert.equal(benchmark.cases.filter((c: any) => c.split === "VALIDATION").length, 30);
  assert.equal(benchmark.cases.filter((c: any) => c.split === "BLIND").length, 30);
  assert.equal(new Set(benchmark.cases.map((c: any) => c.query.toLowerCase())).size, 150);
  assert.ok(benchmark.cases.every((c: any) => c.language === "ENGLISH"));
});
