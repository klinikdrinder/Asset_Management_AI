import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const search = readFileSync("app/lib/media/search.ts", "utf8");
const repository = readFileSync("app/lib/media/repository.ts", "utf8");
const page = readFileSync("app/media-library-page.tsx", "utf8");
const searchBox = readFileSync("app/library-search-box.tsx", "utf8");
const mediaTypes = readFileSync("app/types/media.ts", "utf8");
const rootEnvExample = readFileSync("../.env.example", "utf8");
const dashboardEnvExample = readFileSync(".env.example", "utf8");
const migration = readFileSync("../supabase/migrations/202608070001_add_semantic_search.sql", "utf8");
const correctiveMigration = readFileSync(
  "../supabase/migrations/202608110001_standardize_semantic_vectors_1024.sql",
  "utf8",
);

test("library search is server-only, authenticated, and delegates to the canonical engine", () => {
  assert.match(search, /server-only/);
  assert.match(search, /requireStaffOrAdmin/);
  assert.match(search, /executeCanonicalSearch/);
  // Authorization is enforced inside the canonical pipeline, so a service client here is correct.
  assert.match(search, /createServiceClient/);
});

test("no superseded search engine remains reachable from the library page", () => {
  assert.doesNotMatch(search, /liveRest/);
  assert.doesNotMatch(search, /hybrid_search_assets/);
  assert.doesNotMatch(search, /interpretV3Query/);
  assert.doesNotMatch(search, /localPreviewV3Search/);
});

test("the production search path contacts no external embedding provider", () => {
  assert.doesNotMatch(search, /api\.openai\.com/);
  assert.doesNotMatch(search, /OPENAI_API_KEY/);
  assert.doesNotMatch(search, /OLLAMA_/);
  assert.doesNotMatch(search, /11434/);
});

test("natural-language query is bounded before use", () => {
  assert.match(search, /NLQ_MAX_LEN/);
  assert.match(search, /\.slice\(0, NLQ_MAX_LEN\)/);
});

test("no raw embedding vector is ever selected for API responses", () => {
  assert.doesNotMatch(repository, /"embedding"|,embedding|embedding,/);
  assert.doesNotMatch(search, /asset_semantic_index\([^)]*embedding/);
  assert.doesNotMatch(search, /asset_embeddings\?select/);
  const selectMatch = repository.match(/ASSET_SELECT = "([^"]+)"/);
  assert.ok(selectMatch, "ASSET_SELECT constant should exist");
  assert.doesNotMatch(selectMatch![1], /embedding/);
});

test("match percentage is only rendered during an active semantic search", () => {
  assert.match(page, /asset\.matchPercent != null/);
  assert.match(page, /nlq \? await hybridSearchAssets/);
});

test("short_caption is fetched for normal browsing, independent of an active search", () => {
  assert.match(repository, /asset_semantic_index\(short_caption\)/);
  assert.match(mediaTypes, /shortCaption: string \| null/);
  assert.match(mediaTypes, /matchPercent: number \| null/);
});

test("the natural-language search input is a client island that still submits via GET navigation", () => {
  assert.match(searchBox, /"use client"/);
  assert.match(searchBox, /method="get"/);
  assert.match(searchBox, /name="refine"/);
  assert.match(searchBox, /maxLength=\{300\}/);
});

test("no AI provider is hardcoded outside the OpenAI adapter itself, and Gemini is fully gone", () => {
  for (const source of [search, migration]) {
    assert.doesNotMatch(source, /gemini/i);
    assert.doesNotMatch(source, /GEMINI_API_KEY/);
  }
});

test("no OpenAI credential is referenced or logged anywhere in library search", () => {
  assert.doesNotMatch(search, /NEXT_PUBLIC_OPENAI/);
  assert.doesNotMatch(search, /apiKey/i);
  assert.doesNotMatch(search, /console\.(log|error|warn)/);
});

test("query embedding text uses the same normalization rules documented for the Python side", () => {
  assert.match(search, /normalizeEmbeddingText/);
  assert.match(search, /\.trim\(\)\.replace\(\/\\s\+\/g, " "\)/);
  assert.match(search, /EMBEDDING_TEXT_MAX_LEN/);
});

test("root env example documents the approved provider for the Python worker without a real key", () => {
  assert.match(rootEnvExample, /AI_DESCRIPTION_PROVIDER=ollama/);
  assert.match(rootEnvExample, /AI_EMBEDDING_PROVIDER=ollama/);
  assert.match(rootEnvExample, /OLLAMA_BASE_URL=http:\/\/127\.0\.0\.1:11434/);
  assert.match(rootEnvExample, /OLLAMA_VISION_MODEL=qwen3-vl:2b/);
  assert.match(rootEnvExample, /OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0\.6b/);
  assert.match(rootEnvExample, /OLLAMA_EMBEDDING_DIMENSIONS=1024/);
  assert.match(rootEnvExample, /OPENAI_API_KEY=\s*$/m);
  assert.match(rootEnvExample, /OPENAI_DESCRIPTION_MODEL=gpt-5\.6-luna/);
  assert.match(rootEnvExample, /OPENAI_EMBEDDING_DIMENSIONS=1024/);
});

test("dashboard env example documents only the query-embedding vars it actually reads, no real key", () => {
  assert.match(dashboardEnvExample, /AI_EMBEDDING_PROVIDER=ollama/);
  assert.match(dashboardEnvExample, /OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0\.6b/);
  assert.match(dashboardEnvExample, /OLLAMA_EMBEDDING_DIMENSIONS=1024/);
  assert.match(dashboardEnvExample, /OPENAI_API_KEY=\s*$/m);
  assert.match(dashboardEnvExample, /OPENAI_EMBEDDING_DIMENSIONS=1024/);
  assert.doesNotMatch(dashboardEnvExample, /NEXT_PUBLIC_OPENAI/);
});

test("historical 1536 migration is unchanged and corrective migration standardizes vectors on 1024", () => {
  assert.equal(
    createHash("sha256").update(migration.replace(/\r\n/g, "\n")).digest("hex").toUpperCase(),
    "BDDB7B390B54793AA6412B4DC2FAD60CF14B1EAED879C843EB1EE8979A2021D0",
  );
  assert.match(migration, /embedding public\.vector\(1536\) not null/);
  assert.match(correctiveMigration, /alter column embedding type public\.vector\(1024\)/);
  assert.match(correctiveMigration, /query_embedding public\.vector\(1024\) default null/);
  const dimensionDeclarations = correctiveMigration.match(/public\.vector\((\d+)\)/g) ?? [];
  assert.ok(dimensionDeclarations.length > 0, "expected at least one vector(n) declaration");
  for (const declaration of dimensionDeclarations) {
    assert.equal(declaration, "public.vector(1024)");
  }
});

test("corrective migration is transactional and fails closed unless both semantic tables are empty", () => {
  assert.match(correctiveMigration, /^begin;/m);
  assert.match(correctiveMigration, /lock table public\.asset_semantic_index in access exclusive mode/);
  assert.match(correctiveMigration, /lock table public\.asset_embeddings in access exclusive mode/);
  assert.match(correctiveMigration, /semantic_count <> 0 or embedding_count <> 0/);
  assert.match(correctiveMigration, /raise exception/);
  assert.doesNotMatch(correctiveMigration, /^\s*(truncate\b|delete\s+from\s+public\.asset_)/im);
  assert.match(correctiveMigration, /commit;/);
});

test("pgvector type and cosine operator use the production public extension schema under locked search_path", () => {
  assert.match(migration, /create extension if not exists vector with schema public/);
  assert.match(migration, /to_regoperator\('public\.<=>\(public\.vector,public\.vector\)'\)/);
  assert.match(migration, /OPERATOR\(public\.<=>\)/);
  assert.doesNotMatch(migration, /\bembedding\s+vector\(/);
  assert.doesNotMatch(migration, /\bquery_embedding\s+vector\(/);
  assert.doesNotMatch(migration, /ae\.embedding\s+<=>\s+query_embedding/);
});

test("all two-argument score rounding crosses an explicit numeric type boundary", () => {
  const hybridFunction = migration.match(
    /create or replace function public\.hybrid_search_assets[\s\S]*?\$\$;/,
  );
  assert.ok(hybridFunction, "expected hybrid_search_assets SQL body");
  const roundCalls = hybridFunction[0].match(/\bround\s*\(/g) ?? [];
  const numericPrecisionBoundaries = hybridFunction[0].match(/::numeric,\s*2\s*\)/g) ?? [];
  assert.equal(roundCalls.length, 5, "expected final score plus four diagnostic score rounds");
  assert.equal(numericPrecisionBoundaries.length, roundCalls.length);
  assert.doesNotMatch(hybridFunction[0], /round\(least\(/);
  assert.doesNotMatch(hybridFunction[0], /round\(scored\./);
  for (const score of ["match_score", "semantic_score", "text_score", "structured_score", "filename_score"]) {
    assert.match(hybridFunction[0], new RegExp(`${score} numeric`));
  }
});

test("hybrid_search_assets is security definer and manually re-checks the caller's own authorization", () => {
  assert.match(migration, /security definer\s+set search_path = ''\s+stable\s+as \$\$/);
  assert.match(migration, /private\.is_active_app_user\(\) as is_authorized/);
  assert.match(migration, /where auth\.is_authorized/);
  const fnMatch = migration.match(/create or replace function public\.hybrid_search_assets[\s\S]*?\$\$;/);
  assert.ok(fnMatch, "hybrid_search_assets function should exist");
  assert.doesNotMatch(fnMatch![0].split("returns table")[1].split(")")[0], /embedding/);
});

test("asset_embeddings grants no direct SELECT to authenticated/anon - only the definer RPC may read it", () => {
  assert.match(migration, /alter table public\.asset_embeddings enable row level security/);
  assert.match(
    migration,
    /revoke all on table public\.asset_embeddings from public, anon, authenticated/,
  );
  assert.match(
    migration,
    /grant select, insert, update, delete on table public\.asset_embeddings to service_role/,
  );
  // No `create policy ... on public.asset_embeddings ... to authenticated` anywhere.
  assert.doesNotMatch(migration, /create policy[^;]*on public\.asset_embeddings[^;]*to authenticated/);
});

test("asset_semantic_index keeps its existing individual-read policy for authenticated staff/admin", () => {
  assert.match(migration, /alter table public\.asset_semantic_index enable row level security/);
  assert.match(migration, /create policy asset_semantic_index_individual_read/);
});

test("incompatible embedding dimensions are rejected at the schema level", () => {
  assert.match(correctiveMigration, /check \(embedding_dimensions = 1024\)/);
});

test("corrective RPC preserves authorization, ranking, fallback, filters, and grants", () => {
  assert.match(correctiveMigration, /security definer\s+set search_path = ''\s+stable\s+as \$\$/);
  assert.match(correctiveMigration, /private\.is_active_app_user\(\) as is_authorized/);
  for (const weight of ["0.45::numeric as semantic_weight", "0.20::numeric as fulltext_weight",
    "0.08::numeric as treatment_weight", "0.07::numeric as subject_weight",
    "0.10::numeric as doctor_weight", "0.10::numeric as filename_weight"]) {
    assert.ok(correctiveMigration.includes(weight));
  }
  assert.match(correctiveMigration, /query_embedding is not null/);
  assert.match(correctiveMigration, /si\.treatment OPERATOR\(public\.\%\) b\.q/);
  assert.match(correctiveMigration, /si\.subject OPERATOR\(public\.\%\) b\.q/);
  assert.match(correctiveMigration, /si\.doctor_name OPERATOR\(public\.\%\) b\.q/);
  assert.match(correctiveMigration, /a\.file_name ilike/);
  assert.match(correctiveMigration, /filter_category/);
  assert.match(correctiveMigration, /filter_extension/);
  assert.match(correctiveMigration, /to authenticated/);
});

test("one embedding per asset/provider/model/version is enforced by a unique constraint", () => {
  assert.match(
    migration,
    /unique \(asset_id, embedding_provider, embedding_model, embedding_version\)/,
  );
});

test("metadata and embeddings are stored in separate tables (rebuildable without rewriting metadata)", () => {
  assert.match(migration, /create table if not exists public\.asset_semantic_index/);
  assert.match(migration, /create table if not exists public\.asset_embeddings/);
  assert.match(migration, /asset_id uuid not null references public\.assets\(id\) on delete cascade/);
});

test("ranking weights are centralized in one place and documented, approximately matching the pilot spec", () => {
  const weightsBlock = migration.match(/weights as \(([\s\S]*?)\)/);
  assert.ok(weightsBlock, "expected a centralized `weights` CTE");
  assert.match(weightsBlock![1], /0\.45::numeric as semantic_weight/);
  assert.match(weightsBlock![1], /0\.20::numeric as fulltext_weight/);
  assert.match(weightsBlock![1], /0\.08::numeric as treatment_weight/);
  assert.match(weightsBlock![1], /0\.07::numeric as subject_weight/);
  assert.match(weightsBlock![1], /0\.10::numeric as doctor_weight/);
  assert.match(weightsBlock![1], /0\.10::numeric as filename_weight/);
  // Only one `weights as (` CTE exists anywhere in the file - single source.
  const occurrences = migration.match(/weights as \(/g) ?? [];
  assert.equal(occurrences.length, 1);
});

test("migration is additive only - no destructive statement against existing tables", () => {
  assert.doesNotMatch(migration, /drop table (?!if exists public\.asset)/i);
  assert.doesNotMatch(migration, /^\s*truncate table/im);
  assert.doesNotMatch(migration, /delete from public\.assets/i);
  assert.doesNotMatch(migration, /alter table public\.assets drop column/i);
  assert.doesNotMatch(migration, /update public\.assets set/i);
});

test("removed-source assets are excluded from results, restorable when a source becomes active again", () => {
  assert.match(migration, /sf\.sync_classification is distinct from 'REMOVED_FROM_SOURCE'/);
  assert.match(migration, /sfo\.active = true/);
});

test("filters, filename fallback, treatment/subject/doctor-name boosts, and pagination are all present", () => {
  assert.match(migration, /si\.treatment OPERATOR\(public\.\%\) b\.q/);
  assert.match(migration, /si\.subject OPERATOR\(public\.\%\) b\.q/);
  assert.match(migration, /si\.doctor_name OPERATOR\(public\.\%\) b\.q/);
  assert.match(migration, /a\.file_name ilike/);
  assert.match(migration, /filter_category/);
  assert.match(migration, /filter_extension/);
  assert.match(migration, /limit \(select bounded_limit from bounded\)/);
  assert.match(migration, /offset \(select bounded_offset from bounded\)/);
});
