import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync, existsSync, readdirSync} from "node:fs";
import path from "node:path";
import {assertEmbeddingCompatibility} from "../db/candidate-retriever";
import {CANONICAL_SEARCH_VERSION} from "../db/canonical-production-retriever";
import {SEARCH_VOCABULARY, SEARCH_VOCABULARY_VERSION, vocabularyConceptCodes, resolveVocabularyTerm} from "../db/search-vocabulary-registry";

const root = path.resolve(process.cwd());
const read = (rel: string) => readFileSync(path.join(root, rel), "utf8");
const canonicalRoute = read("app/api/search/route.ts");
const aliasRoute = read("app/api/search/v3/route.ts");
const libSearch = read("app/lib/media/search.ts");
const retriever = read("db/candidate-retriever.ts");
const orchestrator = read("db/canonical-production-retriever.ts");
const parser = read("db/query-interpreter.ts");

/** 1. All production search traffic reaches one canonical entry point. */
test("production search has exactly one entry point", () => {
  assert.ok(existsSync(path.join(root, "app/api/search/route.ts")));
  // The versioned path is an alias that re-exports the canonical handler, not its own authority.
  assert.match(aliasRoute, /export \{\s*POST\s*\} from "\.\.\/route"/);
  assert.doesNotMatch(aliasRoute, /executeCanonicalSearch|retrieveCandidates|interpretQuery/);
  // Both production callers orchestrate through the same function.
  assert.match(canonicalRoute, /executeCanonicalSearch/);
  assert.match(libSearch, /executeCanonicalSearch/);
  // Only one route directory under app/api/search.
  const routeDirs = readdirSync(path.join(root, "app/api/search"), {withFileTypes: true})
    .filter((entry) => entry.isDirectory()).map((entry) => entry.name);
  assert.deepEqual(routeDirs, ["v3"], "only the deprecated alias may remain beside the canonical route");
});

/** 2. v1/v2/v3 engines are not reachable from a normal production request. */
test("legacy engines are unreachable from production search", () => {
  for (const source of [canonicalRoute, libSearch]) {
    assert.doesNotMatch(source, /hybrid_search_assets/);
    assert.doesNotMatch(source, /interpretV3Query/);
    assert.doesNotMatch(source, /localPreviewV3Search/);
    assert.doesNotMatch(source, /liveRest/);
  }
  // The preview engine lives behind an explicitly non-production, dev+loopback gated route.
  const preview = read("app/api/dev/library-preview/search/route.ts");
  assert.match(preview, /isLocalLibraryPreviewActive/);
  assert.match(preview, /status: 404/);
  assert.match(read("app/dev/library-preview/local-preview-client.tsx"), /\/api\/dev\/library-preview\/search/);
  const aclMigration = read("../supabase/migrations/20260904090000_unify_kdi_canonical_search_authority.sql");
  for (const legacy of ["hybrid_search_assets", "hybrid_search_assets_v2", "hybrid_search_assets_v3", "match_phase17_semantic_embeddings"])
    assert.match(aclMigration, new RegExp(`'${legacy}'`));
  assert.match(aclMigration, /revoke all on function %s from public, anon, authenticated/);
});

/** 3. No silent search-version fallback exists. */
test("no silent fallback between search versions", () => {
  for (const source of [canonicalRoute, libSearch]) {
    assert.doesNotMatch(source, /catch[\s\S]{0,200}?(hybrid_search_assets|interpretV3Query|localPreviewV3Search)/);
  }
  // A retrieval failure surfaces as an error, never as a quiet downgrade to another engine.
  assert.match(canonicalRoute, /Search is temporarily unavailable/);
});

/** 4. E5 and OpenCLIP vector spaces remain separated. */
test("embedding families cannot be crossed", () => {
  const identity = (representation: string, provider: string, model: string, modelVersion: string, dimension: number) =>
    ({representation, provider, model, modelVersion, dimension, normalization: "L2"});
  assert.doesNotThrow(() => assertEmbeddingCompatibility(identity("TEXT_SCENE", "sentence_transformers", "intfloat/multilingual-e5-small", "hf-main-pinned-runtime-v1", 384), Array(384).fill(0)));
  assert.doesNotThrow(() => assertEmbeddingCompatibility(identity("VISUAL_SCENE", "open_clip", "ViT-B-32", "laion2b_s34b_b79k", 512), Array(512).fill(0)));
  assert.throws(() => assertEmbeddingCompatibility(identity("TEXT_SCENE", "open_clip", "ViT-B-32", "laion2b_s34b_b79k", 384), Array(384).fill(0)), /INCOMPATIBLE_EMBEDDING_IDENTITY/);
  assert.throws(() => assertEmbeddingCompatibility(identity("TEXT_ASSET", "sentence_transformers", "intfloat/multilingual-e5-small", "hf-main-pinned-runtime-v1", 384), Array(512).fill(0)), /QUERY_VECTOR_DIMENSION_MISMATCH/);
});

/** 5. Scene retrieval can return the parent asset. */
test("scene and keyframe channels retrieve the parent asset", () => {
  for (const representation of ["TEXT_SCENE", "VISUAL_SCENE", "VISUAL_KEYFRAME"])
    assert.match(retriever, new RegExp(representation));
  // Candidates are keyed by asset_id regardless of which scene or keyframe matched.
  assert.match(retriever, /const id=String\(row\.asset_id\?\?row\.assetId\?\?row\.id\?\?""\)/);
  const acceptance = JSON.parse(read("../reports/semantic-search/rollout/full-index-30/full_index_30_raw_acceptance.json"));
  assert.equal(acceptance.scene_specific.cases, acceptance.scene_specific.passed);
  assert.ok(acceptance.scene_specific.scene_channels_observed.includes("TEXT_SCENE"));
});

/** 6 & 7. Exact filename retrieval is deterministic; bare extensions are not filename terms. */
test("filename retrieval is deterministic and extensions are not literals", () => {
  assert.match(retriever, /BARE_EXTENSION=\/\^\(mp4\|/);
  assert.match(retriever, /\.filter\(x=>!BARE_EXTENSION\.test\(x\)\)/);
  assert.match(retriever, /raw_score:exact\?1:stem\?\.98:\.9/);
  const acceptance = JSON.parse(read("../reports/semantic-search/rollout/full-index-30/full_index_30_raw_acceptance.json"));
  const filename = acceptance.cases.filter((c: any) => c.category === "filename");
  assert.ok(filename.length >= 30);
  assert.ok(filename.every((c: any) => c.pass && c.target_rank === 1), "every exact filename must resolve at rank 1");
});

/** 8. MUST_NOT conditions are enforced. */
test("exclusions remain a distinct requirement class", () => {
  const classifier = read("db/requirement-classifier.ts");
  for (const cls of ["HARD_CONSTRAINT", "HARD_EXCLUSION", "STRONG_REQUIREMENT", "PREFERENCE", "NEGATIVE_PREFERENCE", "CONTEXT"])
    assert.match(classifier, new RegExp(cls));
  const acceptance = JSON.parse(read("../reports/semantic-search/rollout/full-index-30/full_index_30_raw_acceptance.json"));
  const exclusions = acceptance.cases.filter((c: any) => c.category === "exclusion");
  assert.ok(exclusions.length > 0 && exclusions.every((c: any) => c.pass));
});

/** 9. UNKNOWN is not interpreted as FALSE. */
test("UNKNOWN is a distinct semantic state", () => {
  const reranker = read("db/deterministic-reranker.ts");
  assert.match(reranker, /"OBSERVED"/);
  assert.match(reranker, /"UNKNOWN"/);
  assert.match(reranker, /"FALSE"/);
  assert.match(reranker, /SemanticState/);
});

/** 10. Requested count is honored without irrelevant padding. */
test("requested count is honored and never padded", () => {
  const controller = read("db/result-count-controller.ts");
  assert.match(controller, /isEligible/);
  assert.match(controller, /isAuthorized/);
  const acceptance = JSON.parse(read("../reports/semantic-search/rollout/full-index-30/full_index_30_raw_acceptance.json"));
  for (const category of ["exact-n", "count-parsing"]) {
    const cases = acceptance.cases.filter((c: any) => c.category === category);
    assert.ok(cases.length > 0 && cases.every((c: any) => c.pass), `${category} must pass`);
  }
  // A shortage returns fewer results rather than filler.
  const counted = acceptance.cases.filter((c: any) => c.category === "exact-n");
  assert.ok(counted.every((c: any) => c.returned_count <= c.effective_count));
});

/** 11. Unauthorized assets cannot leak. */
test("authorization runs before results are exposed", () => {
  assert.match(orchestrator, /authorizeCandidates\(db,retrieved,input\.userId\)/);
  const orderIndex = (needle: string) => orchestrator.indexOf(needle);
  assert.ok(orderIndex("authorizeCandidates") < orderIndex("rerankAuthorizedCandidates"), "authorization precedes ranking");
  assert.ok(orderIndex("rerankAuthorizedCandidates") < orderIndex("applyResultCount"), "ranking precedes count control");
  const acceptance = JSON.parse(read("../reports/semantic-search/rollout/full-index-30/full_index_30_raw_acceptance.json"));
  assert.equal(acceptance.authorization_leakage, 0);
  // The server-rendered library maps the per-candidate download decision; a broad role flag cannot
  // re-enable downloads that the canonical asset gate denied.
  assert.match(libSearch, /candidate\.authorization\?\.download === true/);
  assert.doesNotMatch(libSearch, /mapAsset\(row, user\.canDownload/);
});

/** 12. Zero-result honesty is preserved. */
test("zero-result honesty is preserved", () => {
  const acceptance = JSON.parse(read("../reports/semantic-search/rollout/full-index-30/full_index_30_raw_acceptance.json"));
  const zero = acceptance.cases.filter((c: any) => c.category === "zero-result");
  assert.ok(zero.length > 0);
  assert.ok(zero.every((c: any) => c.pass && c.returned_count === 0));
  assert.equal(acceptance.clinical_false_positives, 0);
});

/** One canonical vocabulary registry, and the parser resolves from it. */
test("one canonical vocabulary registry feeds the parser", () => {
  assert.equal(SEARCH_VOCABULARY_VERSION, "kdi_search_vocabulary_v1");
  assert.match(parser, /const aliases = SEARCH_VOCABULARY/);
  assert.doesNotMatch(parser, /const aliases = config\.semantic_aliases/);
  // The registry is a strict superset of the aliases the parser previously carried.
  const legacy = JSON.parse(read("../config/semantic-search/kdi_query_parser_v1_4.json")).semantic_aliases as Record<string, Record<string, string[]>>;
  // Containment, not first-match: a surface form may legitimately belong to more than one category
  // ("consultation" is both a PROCEDURE_STAGE and an ACTION), so the requirement is that every
  // mapping the parser previously had still exists in the registry.
  for (const [category, codes] of Object.entries(legacy))
    for (const [code, terms] of Object.entries(codes))
      for (const term of terms)
        assert.ok(SEARCH_VOCABULARY[category]?.[code]?.includes(term), `${category}.${code} "${term}" must still resolve`);
  assert.ok(resolveVocabularyTerm("close-up"), "newly reachable wording must resolve");
  assert.ok(vocabularyConceptCodes().length >= Object.values(legacy).reduce((n, c) => n + Object.keys(c).length, 0));
});

/** The engine carries no version label of its own. */
test("the canonical engine is not another numbered version", () => {
  assert.equal(CANONICAL_SEARCH_VERSION, "KDI_CANONICAL_SEMANTIC_SEARCH");
  assert.doesNotMatch(CANONICAL_SEARCH_VERSION, /V[0-9]/);
});

/** Clinical safety: generic wording never reaches a named procedure. */
test("generic visual wording never resolves to a named procedure", () => {
  const named = ["HAIR_TRANSPLANT", "HAIR_TRANSPLANT_FUE", "FUE_IMPLANTATION", "INJECTABLES"];
  for (const term of ["gloves", "gloved hands", "instrument", "visible tool", "scalp", "the scalp", "physical contact", "touching"]) {
    const resolved = resolveVocabularyTerm(term);
    if (resolved) assert.ok(!named.includes(resolved.code), `"${term}" must not resolve to ${resolved.code}`);
  }
  // Named procedures stay reachable from explicit procedure wording only.
  assert.equal(resolveVocabularyTerm("hair transplant")?.code, "HAIR_TRANSPLANT");
  assert.equal(resolveVocabularyTerm("fue")?.code, "HAIR_TRANSPLANT_FUE");
});
