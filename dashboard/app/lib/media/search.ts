import "server-only";
import { requireStaffOrAdmin } from "../../auth";
import type { MediaAsset, MediaPage, MediaQuery } from "../../types/media";
import { ASSET_SELECT, getMediaAssets, InvalidMediaQuery, mapAsset, parseMediaQuery } from "./repository";
import { createServiceClient } from "../supabase/service";
import { executeCanonicalSearch } from "../../../db/canonical-production-retriever";

const NLQ_MAX_LEN = 300;
const EMBEDDING_TEXT_MAX_LEN = 4000;

export { InvalidMediaQuery };

/** Trims and bounds a raw natural-language query before it reaches the canonical parser. */
export function normalizeNaturalLanguageQuery(value: string | undefined): string {
  return (value ?? "").trim().slice(0, NLQ_MAX_LEN);
}

/** Deterministic text normalization shared with the Python worker
 * (kdi_media.providers.base.normalize_embedding_text: trim, collapse whitespace, cap length).
 * Keep the two in sync. */
export function normalizeEmbeddingText(text: string): string {
  return text.trim().replace(/\s+/g, " ").slice(0, EMBEDDING_TEXT_MAX_LEN);
}

/** Server-rendered library search. Delegates entirely to the canonical search engine:
 * interpretation, concept resolution, multi-channel retrieval, authorization, hybrid fusion and
 * requested-count control all happen inside executeCanonicalSearch. This function only maps the
 * canonical result onto the library page shape. There is no second engine and no fallback. */
export async function hybridSearchAssets(
  input: Record<string, string | undefined>,
): Promise<MediaPage> {
  const user = await requireStaffOrAdmin();
  const nlq = normalizeNaturalLanguageQuery(input.nlq);
  const rest = { ...input };
  delete rest.nlq;
  const parsed: MediaQuery = parseMediaQuery(rest);

  if (!nlq) return getMediaAssets(rest);

  const client=createServiceClient();
  const canonical=await executeCanonicalSearch(client,{
    query:nlq,userId:user.userId,requestedCount:input.pageSize?parsed.pageSize:null,
    mediaType:parsed.category?parsed.category.toUpperCase() as "IMAGE"|"VIDEO"|"DOCUMENT":null,
    extension:parsed.extension||null,
  });
  const candidates=canonical.controlled.candidates;
  if (process.env.NODE_ENV === "development" && process.env.KDI_SEARCH_DEBUG === "true") {
    // The canonical engine explains its own run; nothing is recomputed here.
    console.debug(JSON.stringify({scope:"canonical_search",query:nlq,searchVersion:canonical.search_version,...canonical.diagnostics}));
  }

  if (candidates.length === 0) {
    return { items: [], total: 0, page: 1, pageSize: canonical.controlled.count.effective_count, totalPages: 1 };
  }

  const total = canonical.controlled.count.available_valid_count;
  const requestedCount = canonical.controlled.count.effective_count;
  const totalPages = Math.max(1, Math.ceil(total / Math.max(1, requestedCount)));
  const canonicalByAssetId = new Map(candidates.map((row:any) => [String(row.asset_id), row]));
  const orderedIds = candidates.map((row:any) => String(row.asset_id));
  const {data:assetRows,error}=await client.from("assets").select(ASSET_SELECT).in("id",orderedIds);
  if(error)throw error;
  const assetsById = new Map(assetRows.map((row) => [String(row.id), row]));

  const items: MediaAsset[] = orderedIds.flatMap((id) => {
    const row = assetsById.get(id);
    const candidate = canonicalByAssetId.get(id);
    // Download authority is candidate-specific. A broad staff capability must never override the
    // canonical per-asset authorization decision made before ranking and count control.
    return row && candidate
      ? [mapAsset(row, candidate.authorization?.download === true, Number(candidate.phase19?.normalizedScore ?? 0))]
      : [];
  });

  return { items, total, page: parsed.page, pageSize: requestedCount, totalPages };
}
