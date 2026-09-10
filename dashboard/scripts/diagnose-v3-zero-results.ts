import { readFileSync } from "node:fs";

for (const line of readFileSync(".env.local", "utf8").split(/\r?\n/)) {
  const index = line.indexOf("=");
  if (index > 0 && !line.trimStart().startsWith("#")) process.env[line.slice(0, index).trim()] = line.slice(index + 1).trim();
}
const { createClient } = await import("@supabase/supabase-js");
const { interpretV3Query, V3_RANKING } = await import("../app/lib/media/search-v3");
const { localTrustedRest } = await import("../app/lib/library/local-trusted-rest");

const queries = [
  "male patient hair transplant consultation",
  "doctor discussing hairline design",
  "hair transplant procedure",
  "patient consultation with clinician",
  "male over 30 years old doing hair transplant",
  "hairline consultation",
  "frontal hairline",
  "doctor consultation",
  "hairline design",
];
const url = process.env.NEXT_PUBLIC_SUPABASE_URL!, serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;
if (!url || !serviceKey) throw new Error("Supabase configuration is unavailable");
const service = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });

type Asset = { id: string; file_name: string };
type VectorRow = { asset_id: string; embedding: string | number[] };
type RpcRow = { asset_id: string; match_score: number; visual_asset_score: number; visual_scene_score: number; visual_keyframe_score: number; lexical_asset_score: number; lexical_scene_score: number; structured_score: number; filename_score: number; total_count: number };
const { data: assets, error: assetError } = await service.from("assets").select("id,file_name");
const { data: vectors, error: vectorError } = await service.from("asset_visual_embeddings").select("asset_id,embedding").eq("model_provider", "open_clip").eq("model_name", "ViT-B-32").eq("model_version", "laion2b_s34b_b79k").eq("embedding_dimensions", 512);
if (assetError || vectorError) throw assetError ?? vectorError;
const names = new Map((assets as Asset[]).map((asset) => [asset.id, asset.file_name]));
const parseVector = (value: string | number[]) => Array.isArray(value) ? value.map(Number) : value.slice(1, -1).split(",").map(Number);
const indexed = (vectors as VectorRow[]).map((row) => ({ id: row.asset_id, vector: parseVector(row.embedding) }));
const norm = (values: number[]) => Math.sqrt(values.reduce((sum, value) => sum + value * value, 0));
const cosine = (a: number[], b: number[]) => { const denominator = norm(a) * norm(b); return denominator ? a.reduce((sum, value, index) => sum + value * b[index], 0) / denominator : 0; };
async function embed(text: string) {
  const response = await fetch("http://127.0.0.1:8765/embed-text", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
  if (!response.ok) throw new Error("OpenCLIP query embedding failed");
  const body = await response.json() as { provider: string; model: string; version: string; dimensions: number; embedding: number[] };
  if (body.provider !== "open_clip" || body.model !== "ViT-B-32" || body.version !== "laion2b_s34b_b79k" || body.dimensions !== 512 || body.embedding.length !== 512) throw new Error("OpenCLIP identity mismatch");
  return body.embedding;
}
async function rpc(query: string, embedding: number[], filters: Record<string, string>, threshold: number) {
  const response = await localTrustedRest("rpc/hybrid_search_assets_v3", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ search_query: query, visual_query_embedding: embedding, structured_filters: filters, excluded_asset_ids: [], result_limit: 50, result_offset: 0, minimum_relevance: threshold }) });
  if (!response.ok) throw new Error(`V3 RPC failed: ${response.status}`);
  return await response.json() as RpcRow[];
}
const reports = [];
for (const query of queries) {
  const intent = interpretV3Query(query), embedding = await embed(query);
  const rawVector = indexed.map((row) => ({ filename: names.get(row.id) ?? row.id, assetId: row.id, similarity: cosine(embedding, row.vector) })).sort((a, b) => b.similarity - a.similarity).slice(0, 10);
  const noFilterZero = await rpc(query, embedding, {}, 0), noFilterThreshold = await rpc(query, embedding, {}, V3_RANKING.minimumRelevance);
  const filteredZero = await rpc(query, embedding, intent.filters, 0), filteredThreshold = await rpc(query, embedding, intent.filters, V3_RANKING.minimumRelevance);
  const mapRows = (rows: RpcRow[]) => rows.slice(0, 10).map((row) => ({ filename: names.get(row.asset_id) ?? row.asset_id, assetId: row.asset_id, final: Number(row.match_score), visualAsset: Number(row.visual_asset_score), visualScene: Number(row.visual_scene_score), visualKeyframe: Number(row.visual_keyframe_score), lexicalAsset: Number(row.lexical_asset_score), lexicalScene: Number(row.lexical_scene_score), structured: Number(row.structured_score), filenameScore: Number(row.filename_score) }));
  reports.push({ query, parsedQuery: intent.resolvedQuery, filters: intent.filters, embedding: { model: "ViT-B-32", version: "laion2b_s34b_b79k", dimensions: embedding.length }, stages: { visualEmbeddingRows: indexed.length, authorizedAndEligibleBeforeRanking: noFilterZero[0]?.total_count ?? 0, afterThresholdWithoutStructuredFilters: noFilterThreshold[0]?.total_count ?? 0, afterMandatoryStructuredFiltersBeforeThreshold: filteredZero[0]?.total_count ?? 0, finalResults: filteredThreshold[0]?.total_count ?? 0 }, rawVectorTop10: rawVector, unfilteredHybridTop10: mapRows(noFilterZero), finalTop10: mapRows(filteredThreshold) });
}
process.stdout.write(JSON.stringify(reports.map((report) => ({
  query: report.query, filters: report.filters, embedding: report.embedding, stages: report.stages,
  rawVectorCandidates: report.stages.visualEmbeddingRows,
  finalTop10: report.finalTop10.map((candidate) => ({ filename: candidate.filename, final: candidate.final, visualAsset: candidate.visualAsset, visualScene: candidate.visualScene, lexicalAsset: candidate.lexicalAsset, lexicalScene: candidate.lexicalScene, structured: candidate.structured })),
})), null, 2));
