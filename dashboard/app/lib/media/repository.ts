import "server-only";
import { requireStaffOrAdmin } from "../../auth";
import { categoryRestFilter, classifyMedia, MEDIA_CATEGORIES } from "../library/classification";
import { liveRest } from "../library/live-transport";
import type { MediaAsset, MediaPage, MediaQuery, MediaSort } from "../../types/media";

type Json = Record<string, unknown>;
const PAGE_SIZES = [25, 50, 100] as const;
const SORTS: readonly MediaSort[] = ["newest", "oldest", "smallest", "largest"];
export class InvalidMediaQuery extends Error {}
function objects(value: unknown): Json[] { if (Array.isArray(value)) return value.filter((item): item is Json => Boolean(item) && typeof item === "object"); return value && typeof value === "object" ? [value as Json] : []; }
function text(value: unknown): string | null { return value == null ? null : String(value); }
function cleanSearch(value: string | undefined) { return (value ?? "").trim().slice(0, 100).replace(/[*,()]/g, ""); }

export function parseMediaQuery(input: Record<string, string | undefined>): MediaQuery {
  const allowed = new Set(["page", "pageSize", "query", "category", "type", "extension", "sort"]);
  if (Object.keys(input).some((key) => !allowed.has(key))) throw new InvalidMediaQuery("Unsupported library filter");
  const page = Math.max(1, Number.parseInt(input.page ?? "1", 10) || 1);
  const requestedSize = Number.parseInt(input.pageSize ?? "25", 10);
  const pageSize = PAGE_SIZES.includes(requestedSize as (typeof PAGE_SIZES)[number]) ? requestedSize : 25;
  const requestedCategory = input.category ?? input.type ?? "";
  if (requestedCategory && !MEDIA_CATEGORIES.includes(requestedCategory as (typeof MEDIA_CATEGORIES)[number])) throw new InvalidMediaQuery("Unsupported media category");
  const requestedSort = input.sort ?? "newest";
  if (!SORTS.includes(requestedSort as MediaSort)) throw new InvalidMediaQuery("Unsupported sort order");
  return { page, pageSize, search: cleanSearch(input.query), category: requestedCategory as MediaQuery["category"], extension: (input.extension ?? "").replace(/[^a-z0-9]/gi, "").slice(0, 12).toLowerCase(), sort: requestedSort as MediaSort };
}

const select = "id,file_name,mime_type,file_extension,size_bytes,upload_status,created_at,updated_at,asset_sources(source_file_id,source_files(id,source_folder_id,drive_created_at,drive_modified_at,source_folders(source_name))),asset_destinations(id,destination_google_file_id,upload_status,verification_level)";
function mapAsset(row: Json, canDownload: boolean): MediaAsset {
  const link = objects(row.asset_sources)[0] ?? {}, source = objects(link.source_files)[0] ?? {}, folder = objects(source.source_folders)[0] ?? {};
  const verified = objects(row.asset_destinations).find((item) => item.upload_status === "VERIFIED" && item.destination_google_file_id) ?? null;
  const extension = text(row.file_extension), mimeType = text(row.mime_type), id = String(row.id);
  const category = classifyMedia(mimeType, extension);
  return { id, sourceFileId: text(source.id) ?? text(link.source_file_id), filename: String(row.file_name || "File"), extension, mimeType, category, sizeBytes: row.size_bytes == null ? null : Number(row.size_bytes), createdAt: text(row.created_at) ?? text(source.drive_created_at), modifiedAt: text(row.updated_at) ?? text(source.drive_modified_at), sourceFolder: String(folder.source_name || "Central library"), storageDestination: verified ? "google-drive" : null, migrationStatus: String(verified?.upload_status || row.upload_status || "NOT_STARTED"), verificationStatus: String(verified?.verification_level || "NONE"), canPreview: Boolean(verified), canDownload: Boolean(verified) && canDownload, previewUrl: verified ? `/api/media/${id}/preview` : null, downloadUrl: verified && canDownload ? `/api/media/${id}/download` : null, thumbnailUrl: verified && (category === "image" || category === "video") ? `/api/media/${id}/thumbnail` : null };
}
function sortExpression(sort: MediaSort) { if (sort === "oldest") return "updated_at.asc.nullslast,id.asc"; if (sort === "smallest") return "size_bytes.asc.nullslast,id.asc"; if (sort === "largest") return "size_bytes.desc.nullslast,id.asc"; return "updated_at.desc.nullslast,id.asc"; }

export async function getMediaAssets(input: Record<string, string | undefined> = {}): Promise<MediaPage> {
  const user = await requireStaffOrAdmin(), query = parseMediaQuery(input), filters: string[] = [];
  if (query.search) filters.push(`file_name.ilike.${encodeURIComponent(`*${query.search}*`)}`);
  if (query.category) filters.push(categoryRestFilter(query.category));
  if (query.extension) filters.push(`file_extension=ilike.${encodeURIComponent(query.extension)}`);
  const offset = (query.page - 1) * query.pageSize;
  const response = await liveRest(`assets?select=${select}${filters.length ? `&${filters.join("&")}` : ""}&order=${sortExpression(query.sort)}&offset=${offset}&limit=${query.pageSize}`, { headers: { Prefer: "count=exact" } });
  const rows = (await response.json()) as Json[], total = Number((response.headers.get("content-range") ?? "").split("/")[1] || 0), totalPages = Math.max(1, Math.ceil(total / query.pageSize));
  return { items: rows.map((row) => mapAsset(row, user.canDownload)), total, page: Math.min(query.page, totalPages), pageSize: query.pageSize, totalPages };
}
