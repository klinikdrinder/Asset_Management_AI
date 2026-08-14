import "server-only";
import { requireStaffOrAdmin } from "../../auth";
import { liveRest } from "../library/live-transport";
import type { MediaAsset, MediaPage, MediaQuery } from "../../types/media";
import { ASSET_SELECT, getMediaAssets, InvalidMediaQuery, mapAsset, parseMediaQuery } from "./repository";

type Json = Record<string, unknown>;

const NLQ_MAX_LEN = 300;
const EMBEDDING_TEXT_MAX_LEN = 4000;
const QUERY_CACHE_TTL_MS = 15 * 60 * 1000;
const QUERY_CACHE_MAX = 250;
const queryEmbeddingCache = new Map<string, { expiresAt: number; embedding: number[] }>();
const visualQueryCache = new Map<string, { expiresAt: number; embedding: number[] }>();
const VISUAL_IDENTITY = { provider: "open_clip", model: "ViT-B-32", version: "laion2b_s34b_b79k", dimensions: 512 } as const;

/** Server-only provider selection. Ollama is local-first; OpenAI remains an
 * explicit optional provider and is never an implicit fallback. */
const EMBEDDING_PROVIDER = process.env.AI_EMBEDDING_PROVIDER?.trim().toLowerCase() || null;

function embeddingIdentity(): { model: string; dimensions: number; version: string } | null {
  if (EMBEDDING_PROVIDER === "ollama") return {
    model: process.env.OLLAMA_EMBEDDING_MODEL || "",
    dimensions: Number(process.env.OLLAMA_EMBEDDING_DIMENSIONS || ""),
    version: process.env.OLLAMA_EMBEDDING_VERSION || "v1",
  };
  if (EMBEDDING_PROVIDER === "openai") return {
    model: process.env.OPENAI_EMBEDDING_MODEL || "",
    dimensions: Number(process.env.OPENAI_EMBEDDING_DIMENSIONS || ""),
    version: process.env.OPENAI_EMBEDDING_VERSION || "v1",
  };
  return null;
}

export { InvalidMediaQuery };

/** Trims/bounds a raw natural-language query. Does not strip PostgREST
 * special characters: the hybrid_search_assets RPC parameterizes the query
 * text (no client-built filter string), so injection is not a concern here. */
export function normalizeNaturalLanguageQuery(value: string | undefined): string {
  return (value ?? "").trim().slice(0, NLQ_MAX_LEN);
}

/** Deterministic normalization shared by asset-text and query-text
 * embedding. Must match kdi_media.providers.base.normalize_embedding_text
 * (Python side: trim, collapse whitespace, cap length) - keep in sync. */
export function normalizeEmbeddingText(text: string): string {
  return text.trim().replace(/\s+/g, " ").slice(0, EMBEDDING_TEXT_MAX_LEN);
}

/**
 * Embeds the query server-side via the configured AI provider. Returns null
 * (never throws) whenever no provider is configured/recognized, its config
 * is incomplete, or the call fails, so callers always fall back to
 * full-text/metadata/filename search - natural-language search degrades gracefully
 * instead of erroring. Never logs or echoes OPENAI_API_KEY.
 */
async function generateQueryEmbedding(query: string): Promise<number[] | null> {
  const identity = embeddingIdentity();
  if (!identity || !identity.model || identity.dimensions !== 1024) return null;

  const normalized = normalizeEmbeddingText(query);
  if (!normalized) return null;
  const cacheKey = [EMBEDDING_PROVIDER, identity.model, identity.version,
    identity.dimensions, normalized.toLocaleLowerCase("en")].join("|");
  const cached = queryEmbeddingCache.get(cacheKey);
  if (cached && cached.expiresAt > Date.now()) return [...cached.embedding];

  try {
    let response: Response;
    if (EMBEDDING_PROVIDER === "ollama") {
      const base = new URL(process.env.OLLAMA_BASE_URL || "http://127.0.0.1:11434");
      if (base.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(base.hostname)
        || base.port !== "11434") return null;
      response = await fetch(new URL("/api/embed", base), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: identity.model, input: normalized,
          dimensions: identity.dimensions, truncate: false,
          options: {
            num_ctx: Number(process.env.OLLAMA_EMBEDDING_CONTEXT_LENGTH || "2048"),
            num_batch: Number(process.env.OLLAMA_EMBEDDING_BATCH_SIZE || "32"),
          },
          keep_alive: 0 }),
        signal: AbortSignal.timeout(120000),
      });
    } else {
      const apiKey = process.env.OPENAI_API_KEY;
      if (!apiKey) return null;
      response = await fetch("https://api.openai.com/v1/embeddings", {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
        body: JSON.stringify({ model: identity.model, input: normalized, dimensions: identity.dimensions }),
        signal: AbortSignal.timeout(8000),
      });
    }
    if (!response.ok) return null;
    const data = (await response.json()) as { data?: { embedding?: unknown }[]; embeddings?: unknown[] };
    const values = EMBEDDING_PROVIDER === "ollama" ? data.embeddings?.[0] : data.data?.[0]?.embedding;
    if (!Array.isArray(values) || values.length !== identity.dimensions) return null;
    if (!values.every((value) => typeof value === "number" && Number.isFinite(value))) return null;
    const embedding = values as number[];
    if (queryEmbeddingCache.size >= QUERY_CACHE_MAX) queryEmbeddingCache.delete(queryEmbeddingCache.keys().next().value ?? "");
    queryEmbeddingCache.set(cacheKey, { expiresAt: Date.now() + QUERY_CACHE_TTL_MS, embedding });
    return [...embedding];
  } catch {
    return null;
  }
}

async function generateVisualQueryEmbedding(query: string): Promise<number[] | null> {
  const normalized = normalizeEmbeddingText(query);
  if (!normalized) return null;
  const key = normalized.toLocaleLowerCase("en");
  const cached = visualQueryCache.get(key);
  if (cached && cached.expiresAt > Date.now()) return [...cached.embedding];
  try {
    const base = new URL(process.env.KDI_VISUAL_EMBEDDING_URL || "http://127.0.0.1:8765");
    if (base.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(base.hostname)) return null;
    const response = await fetch(new URL("/embed-text", base), { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: normalized }), signal: AbortSignal.timeout(120000) });
    if (!response.ok) return null;
    const data = await response.json() as { provider?: unknown; model?: unknown; version?: unknown; dimensions?: unknown; embedding?: unknown };
    if (data.provider !== VISUAL_IDENTITY.provider || data.model !== VISUAL_IDENTITY.model || data.version !== VISUAL_IDENTITY.version ||
      data.dimensions !== VISUAL_IDENTITY.dimensions || !Array.isArray(data.embedding) || data.embedding.length !== VISUAL_IDENTITY.dimensions ||
      !data.embedding.every((value) => typeof value === "number" && Number.isFinite(value))) return null;
    const embedding = data.embedding as number[];
    if (visualQueryCache.size >= QUERY_CACHE_MAX) visualQueryCache.delete(visualQueryCache.keys().next().value ?? "");
    visualQueryCache.set(key, { expiresAt: Date.now() + QUERY_CACHE_TTL_MS, embedding });
    return [...embedding];
  } catch { return null; }
}

/** Server-side hybrid search: semantic + full-text + filename + field boosts,
 * ranked and permission-filtered entirely inside hybrid_search_assets (a
 * security-definer function that re-checks the caller's own JWT internally
 * - see the migration - so raw embeddings are never directly selectable by
 * this or any other client-facing code path). Falls back to the existing
 * non-vector hybrid ranking whenever query-embedding generation fails, so natural-
 * language search never breaks the baseline search experience. */
export async function hybridSearchAssets(
  input: Record<string, string | undefined>,
): Promise<MediaPage> {
  const user = await requireStaffOrAdmin();
  const nlq = normalizeNaturalLanguageQuery(input.nlq);
  const rest = { ...input };
  delete rest.nlq;
  const parsed: MediaQuery = parseMediaQuery(rest);

  if (!nlq) return getMediaAssets(rest);

  const [embedding, visualEmbedding] = await Promise.all([generateQueryEmbedding(nlq), generateVisualQueryEmbedding(nlq)]);
  const identity = embeddingIdentity();
  const offset = (parsed.page - 1) * parsed.pageSize;
  const response = await liveRest(visualEmbedding ? "rpc/hybrid_search_assets_v2" : "rpc/hybrid_search_assets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(visualEmbedding ? {
      search_query: nlq, visual_query_embedding: visualEmbedding,
      visual_provider: VISUAL_IDENTITY.provider, visual_model: VISUAL_IDENTITY.model, visual_version: VISUAL_IDENTITY.version,
      qwen_query_embedding: embedding, qwen_provider: embedding ? EMBEDDING_PROVIDER : null,
      qwen_model: embedding ? identity?.model || null : null, qwen_version: embedding ? identity?.version || null : null,
      filter_category: parsed.category || null, filter_extension: parsed.extension || null,
      result_limit: parsed.pageSize, result_offset: offset,
    } : {
      search_query: nlq,
      query_embedding: embedding,
      // Scopes the join in hybrid_search_assets to embeddings produced by
      // this exact provider/model/version, so a future model upgrade never
      // compares a query vector against an incompatible stored vector.
      query_embedding_provider: embedding ? EMBEDDING_PROVIDER : null,
      query_embedding_model: embedding ? identity?.model || null : null,
      query_embedding_version: embedding ? identity?.version || null : null,
      filter_category: parsed.category || null,
      filter_extension: parsed.extension || null,
      result_limit: parsed.pageSize,
      result_offset: offset,
    }),
  });
  const rows = (await response.json()) as Json[];
  if (process.env.NODE_ENV === "development" && process.env.KDI_SEARCH_DEBUG === "true") {
    console.debug(JSON.stringify({
      scope: "conversational_search_ranking",
      query: nlq,
      embeddingAvailable: embedding !== null, visualEmbeddingAvailable: visualEmbedding !== null,
      results: rows.map((row, index) => ({
        rank: index + 1, assetId: String(row.asset_id), visualScore: Number(row.visual_score ?? 0), semanticScore: Number(row.semantic_score ?? 0),
        textScore: Number(row.text_score ?? 0), structuredScore: Number(row.structured_score ?? 0),
        filenameScore: Number(row.filename_score ?? 0), matchScore: Number(row.match_score ?? 0),
      })),
    }));
  }
  if (rows.length === 0) {
    return { items: [], total: 0, page: 1, pageSize: parsed.pageSize, totalPages: 1 };
  }

  const total = Number(rows[0]?.total_count ?? rows.length);
  const totalPages = Math.max(1, Math.ceil(total / parsed.pageSize));
  const matchPercentByAssetId = new Map(rows.map((row) => [String(row.asset_id), Number(row.match_score ?? 0)]));
  const orderedIds = rows.map((row) => String(row.asset_id));

  const assetResponse = await liveRest(`assets?select=${ASSET_SELECT}&id=in.(${orderedIds.join(",")})`);
  const assetRows = (await assetResponse.json()) as Json[];
  const assetsById = new Map(assetRows.map((row) => [String(row.id), row]));

  const items: MediaAsset[] = orderedIds
    .map((id) => assetsById.get(id))
    .filter((row): row is Json => Boolean(row))
    .map((row) => mapAsset(row, user.canDownload, matchPercentByAssetId.get(String(row.id)) ?? 0));

  return { items, total, page: parsed.page, pageSize: parsed.pageSize, totalPages };
}
