import assert from "node:assert/strict";
import test from "node:test";
import { interpretQuery, QUERY_PARSER_VERSION } from "../db/query-interpreter";

const codes = (plan: Awaited<ReturnType<typeof interpretQuery>>, polarity: "positive" | "negative") =>
  plan.semantic[`${polarity}_concepts`].map((concept) => concept.canonical_code);

test("v1.3 exclusion behavior remains compatible", async () => {
  assert.match(QUERY_PARSER_VERSION, /^kdi_query_parser_v1_[34]$/);
});

for (const query of [
  "Omit all injections from the selection",
  "Avoid any kind of syringe footage",
  "Do not include injection scenes",
  "Anything except injecting",
  "Remove every instance of a syringe",
  "Leave injections out of the results",
  "Not showing a needle injection",
]) test(`general exclusion: ${query}`, async () => {
  const plan = await interpretQuery(query);
  assert.ok(codes(plan, "negative").includes("INJECTING"));
  assert.ok(!codes(plan, "positive").includes("INJECTING"));
});

test("negation remains clause scoped", async () => {
  const plan = await interpretQuery("No injection but the doctor must be visible");
  assert.ok(codes(plan, "negative").includes("INJECTING"));
  assert.ok(codes(plan, "positive").includes("CLINICIAN"));
});

test("same action keeps both occurrences and conflict", async () => {
  const plan = await interpretQuery("Without a syringe, although injection must appear");
  assert.ok(codes(plan, "negative").includes("INJECTING"));
  assert.ok(codes(plan, "positive").includes("INJECTING"));
  assert.ok(plan.parser_metadata.conflicts.some((conflict: any) => conflict.conflict_type === "CONCEPT_POLARITY_CONFLICT"));
});

test("object aliases do not create treatment", async () => {
  const plan = await interpretQuery("Exclude every syringe");
  assert.ok(!plan.semantic.positive_concepts.some((concept) => concept.concept_type === "TREATMENT"));
  assert.ok(!plan.semantic.negative_concepts.some((concept) => concept.concept_type === "TREATMENT"));
});

test("conservative fuzzy and unknown protections remain", async () => {
  const donor = await interpretQuery("donor");
  assert.ok(!codes(donor, "positive").includes("CLINICIAN"));
  const unknown = await interpretQuery("quartz scalp harmonic");
  assert.ok(!codes(unknown, "positive").includes("SCALP"));
  assert.ok(unknown.semantic.unresolved_concepts.length > 0);
});
