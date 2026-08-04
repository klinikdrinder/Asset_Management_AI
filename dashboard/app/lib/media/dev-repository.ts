import "server-only";
import { createServiceClient } from "../supabase/service";
import { classifyMedia } from "../library/classification";
import { isLibraryDevBypassEnabled } from "../library/dev-bypass";
import type { MediaAsset, MediaPage, MediaQuery, MediaSort } from "../../types/media";

type Json = Record<string, unknown>;
const SELECT = "id,file_name,mime_type,file_extension,size_bytes,updated_at,asset_sources(source_file_id,source_files(source_folders(source_name))),asset_destinations(destination_google_file_id,upload_status)";
const values = (value: unknown): Json[] => Array.isArray(value) ? value as Json[] : value && typeof value === "object" ? [value as Json] : [];
const text = (value: unknown) => value == null ? null : String(value);
const PAGE_SIZES = [25, 50, 100] as const, SORTS: readonly MediaSort[] = ["newest", "oldest", "smallest", "largest"];
function parseDevQuery(input: Record<string, string | undefined>): MediaQuery { const allowed = new Set(["page", "pageSize", "query", "category", "type", "extension", "sort"]); if (Object.keys(input).some(key => !allowed.has(key))) throw new Error("Invalid development media query"); const page = Math.max(1, Number.parseInt(input.page ?? "1", 10) || 1), requestedSize = Number.parseInt(input.pageSize ?? "25", 10), pageSize = PAGE_SIZES.includes(requestedSize as never) ? requestedSize : 25, category = input.category ?? input.type ?? "", sort = input.sort ?? "newest"; if (category && !["image", "video", "document", "other"].includes(category)) throw new Error("Invalid development media category"); if (!SORTS.includes(sort as MediaSort)) throw new Error("Invalid development media sort"); return { page, pageSize, search: (input.query ?? "").trim().slice(0, 100).replace(/[*,()]/g, ""), category: category as MediaQuery["category"], extension: (input.extension ?? "").replace(/[^a-z0-9]/gi, "").slice(0, 12).toLowerCase(), sort: sort as MediaSort }; }

function assertDevAccess() { if (!isLibraryDevBypassEnabled()) throw new Error("Development library unavailable"); }
function mapAsset(row: Json): MediaAsset {
  const link = values(row.asset_sources)[0] ?? {}, source = values(link.source_files)[0] ?? {}, folder = values(source.source_folders)[0] ?? {};
  const verified = values(row.asset_destinations).find((item) => item.upload_status === "VERIFIED" && item.destination_google_file_id) ?? null;
  const extension = text(row.file_extension), mimeType = text(row.mime_type), id = String(row.id);
  const category = classifyMedia(mimeType, extension);
  return { id, sourceFileId: text(link.source_file_id), filename: String(row.file_name || "File"), extension, mimeType, category, sizeBytes: row.size_bytes == null ? null : Number(row.size_bytes), createdAt: null, modifiedAt: text(row.updated_at), sourceFolder: String(folder.source_name || "Central library"), storageDestination: verified ? "google-drive" : null, migrationStatus: String(verified?.upload_status || "NOT_STARTED"), verificationStatus: verified ? "VERIFIED" : "NONE", canPreview: Boolean(verified), canDownload: Boolean(verified), previewUrl: verified ? `/api/dev/library/media/${id}/preview` : null, downloadUrl: verified ? `/api/dev/library/media/${id}/download` : null, thumbnailUrl: verified && (category === "image" || category === "video") ? `/api/dev/library/media/${id}/thumbnail` : null };
}
function sorting(sort: MediaSort): { column: string; ascending: boolean } { if (sort === "oldest") return { column: "updated_at", ascending: true }; if (sort === "smallest") return { column: "size_bytes", ascending: true }; if (sort === "largest") return { column: "size_bytes", ascending: false }; return { column: "updated_at", ascending: false }; }
export async function getDevMediaAssets(input: Record<string, string | undefined> = {}): Promise<MediaPage> {
  assertDevAccess();
  const query = parseDevQuery(input), client = createServiceClient(), order = sorting(query.sort), from = (query.page - 1) * query.pageSize;
  let request = client.from("assets").select(SELECT, { count: "exact" });
  if (query.search) request = request.ilike("file_name", `%${query.search}%`);
  if (query.extension) request = request.ilike("file_extension", query.extension);
  if (query.category === "image") request = request.or("mime_type.ilike.image/%,file_extension.in.(jpg,jpeg,png,webp,JPG,JPEG,PNG,WEBP)");
  if (query.category === "video") request = request.or("mime_type.ilike.video/%,file_extension.in.(mp4,mov,MP4,MOV)");
  if (query.category === "document") request = request.or("mime_type.eq.application/pdf,mime_type.eq.application/vnd.openxmlformats-officedocument.presentationml.presentation,mime_type.ilike.%presentation%,file_extension.in.(pdf,pptx,PDF,PPTX)");
  if (query.category === "other") request = request.not("mime_type", "ilike", "image/%").not("mime_type", "ilike", "video/%").not("file_extension", "in", "(jpg,jpeg,png,webp,JPG,JPEG,PNG,WEBP,mp4,mov,MP4,MOV,pdf,pptx,PDF,PPTX)");
  const { data, error, count } = await request.order(order.column, { ascending: order.ascending, nullsFirst: false }).order("id", { ascending: true }).range(from, from + query.pageSize - 1);
  if (error) throw new Error("Live development library query failed");
  const total = count ?? 0, totalPages = Math.max(1, Math.ceil(total / query.pageSize));
  return { items: (data as unknown as Json[]).map(mapAsset), total, page: Math.min(query.page, totalPages), pageSize: query.pageSize, totalPages };
}

export async function getDevMediaAsset(id: string): Promise<MediaAsset | null> {
  assertDevAccess();
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id)) return null;
  const { data, error } = await createServiceClient().from("assets").select(SELECT).eq("id", id).maybeSingle();
  if (error) throw new Error("Live development asset query failed");
  return data ? mapAsset(data as unknown as Json) : null;
}

export async function getDevAuthorizedMediaRecord(id: string) {
  assertDevAccess();
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id)) return null;
  const { data, error } = await createServiceClient().from("assets").select("id,file_name,mime_type,file_extension,size_bytes,asset_destinations!inner(selected_source_file_id,destination_google_file_id,destination_filename,upload_status)").eq("id", id).eq("asset_destinations.upload_status", "VERIFIED").maybeSingle();
  if (error || !data) return null;
  const row = data as unknown as Json, destination = values(row.asset_destinations)[0];
  if (!destination?.destination_google_file_id) return null;
  return { sourceFileId: String(destination.selected_source_file_id), destinationFileId: String(destination.destination_google_file_id), destinationFilename: String(destination.destination_filename || row.file_name || "download"), filename: String(row.file_name || destination.destination_filename || "download"), mime: String(row.mime_type || "application/octet-stream"), extension: String(row.file_extension || ""), size: Number(row.size_bytes || 0) };
}
