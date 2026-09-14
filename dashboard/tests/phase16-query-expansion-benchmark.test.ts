import test from "node:test"; import assert from "node:assert/strict"; import benchmark from "../../config/semantic-search/benchmarks/kdi_query_expansion_benchmark_v1.json";
test("benchmark is frozen and split correctly",()=>{assert.equal(benchmark.cases.length,180);assert.deepEqual(benchmark.splits,{dev:120,validation:30,blind:30});assert.equal(benchmark.language,"ENGLISH")});
