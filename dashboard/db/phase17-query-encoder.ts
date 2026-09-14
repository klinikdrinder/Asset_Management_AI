// Query-time embedding client.
//
// Previously this spawned two Python subprocesses per search and reloaded the e5
// and OpenCLIP models from disk every time — seconds of latency, and impossible
// on Cloudflare Workers, which cannot spawn processes. It now calls the warm
// embedding sidecar (visual_indexing/embedding_service.py) over HTTP; the sidecar
// keeps both models resident and in-region (ap-southeast-1). A small in-isolate
// LRU skips the network round-trip for repeated queries.
//
// The exported shape is unchanged: callers still receive {text[384], visual[512],
// provenance} per input, so the retriever is untouched.

const E5_DIM = 384;
const VISUAL_DIM = 512;
const CACHE_MAX = 512;
const DEFAULT_TIMEOUT_MS = 15_000;

// Loopback default for local dev; production sets EMBED_SERVICE_URL to the
// in-region sidecar. No trailing slash.
const SERVICE_URL = (process.env.EMBED_SERVICE_URL ?? "http://127.0.0.1:8799").replace(/\/+$/, "");

export type QueryEmbeddingProvenance = {
  e5: { provider: string; model: string; model_version?: string; dimension: number; preprocessing: string };
  openclip: { provider: string; model: string; checkpoint: string; dimension: number; preprocessing: string };
  elapsed_ms?: number;
};
export type QueryEmbedding = {
  text: number[];
  visual: number[];
  provenance: QueryEmbeddingProvenance;
};

const normalise = (text: string): string => text.replace(/\s+/g, " ").trim().slice(0, 300);

// Insertion-ordered Map used as an LRU: re-insert on hit, evict oldest on overflow.
const cache = new Map<string, QueryEmbedding>();
function cacheGet(key: string): QueryEmbedding | undefined {
  const hit = cache.get(key);
  if (hit) { cache.delete(key); cache.set(key, hit); }
  return hit;
}
function cachePut(key: string, value: QueryEmbedding): void {
  cache.set(key, value);
  while (cache.size > CACHE_MAX) cache.delete(cache.keys().next().value as string);
}

function validVector(vector: unknown, dimension: number): vector is number[] {
  return Array.isArray(vector) && vector.length === dimension && vector.every((x) => Number.isFinite(x));
}

async function callService(texts: string[], timeout = DEFAULT_TIMEOUT_MS) {
  const started = performance.now();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  let response: Response;
  try {
    response = await fetch(`${SERVICE_URL}/embed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texts }),
      signal: controller.signal,
    });
  } catch (error) {
    const e = error as { name?: string; message?: string };
    throw new Error(`QUERY_ENCODER_UNREACHABLE:${e?.name === "AbortError" ? "TIMEOUT" : e?.message ?? String(error)}`);
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) throw new Error(`QUERY_ENCODER_HTTP_${response.status}:${(await response.text().catch(() => "")).slice(0, 200)}`);
  const body = await response.json().catch(() => null) as { e5?: unknown[]; openclip?: unknown[]; provenance?: unknown } | null;
  const e5 = body?.e5, openclip = body?.openclip;
  if (!Array.isArray(e5) || !Array.isArray(openclip) || e5.length !== texts.length || openclip.length !== texts.length)
    throw new Error("QUERY_ENCODER_SHAPE_MISMATCH");
  return texts.map((_, i) => {
    if (!validVector(e5[i], E5_DIM)) throw new Error(`QUERY_ENCODER_DIMENSION_MISMATCH:${E5_DIM}`);
    if (!validVector(openclip[i], VISUAL_DIM)) throw new Error(`QUERY_ENCODER_DIMENSION_MISMATCH:${VISUAL_DIM}`);
    return { text: e5[i], visual: openclip[i], provenance: { ...(body?.provenance as QueryEmbeddingProvenance), elapsed_ms: performance.now() - started } };
  });
}

export async function encodePhase17Queries(texts: string[]): Promise<QueryEmbedding[]> {
  const clean = texts.map(normalise);
  if (!clean.length || clean.some((x) => !x)) throw new Error("QUERY_EMBEDDING_EMPTY_TEXT");

  const result = new Array<QueryEmbedding>(clean.length);
  const missIndexes: number[] = [];
  clean.forEach((key, i) => {
    const hit = cacheGet(key);
    if (hit) result[i] = hit; else missIndexes.push(i);
  });

  if (missIndexes.length) {
    const encoded = await callService(missIndexes.map((i) => clean[i]));
    missIndexes.forEach((i, j) => { result[i] = encoded[j]; cachePut(clean[i], encoded[j]); });
  }
  return result;
}

export async function encodePhase17Query(text: string): Promise<QueryEmbedding> {
  return (await encodePhase17Queries([text]))[0];
}
