import "server-only";
import { createServiceClient } from "../supabase/service";
import { classifyMedia } from "../library/classification";
import { isLibraryDevBypassEnabled } from "../library/dev-bypass";
import { isLocalLibraryPreviewConfigured } from "../library/local-preview";
import type { MediaAsset, MediaPage, MediaQuery, MediaSort } from "../../types/media";

type Json = Record<string, unknown>;
const SELECT = "id,file_name,mime_type,file_extension,size_bytes,updated_at,asset_sources(source_file_id,source_files(source_folders(source_name))),asset_destinations(destination_google_file_id,upload_status),asset_semantic_index(short_caption)";
const values = (value: unknown): Json[] => Array.isArray(value) ? value as Json[] : value && typeof value === "object" ? [value as Json] : [];
const text = (value: unknown) => value == null ? null : String(value);
const PAGE_SIZES = [25, 50, 100] as const, SORTS: readonly MediaSort[] = ["newest", "oldest", "smallest", "largest"];
function parseDevQuery(input: Record<string, string | undefined>): MediaQuery { const allowed = new Set(["page", "pageSize", "query", "category", "type", "extension", "sort"]); if (Object.keys(input).some(key => !allowed.has(key))) throw new Error("Invalid development media query"); const page = Math.max(1, Number.parseInt(input.page ?? "1", 10) || 1), requestedSize = Number.parseInt(input.pageSize ?? "25", 10), pageSize = PAGE_SIZES.includes(requestedSize as never) ? requestedSize : 25, category = input.category ?? input.type ?? "", sort = input.sort ?? "newest"; if (category && !["image", "video", "document", "other"].includes(category)) throw new Error("Invalid development media category"); if (!SORTS.includes(sort as MediaSort)) throw new Error("Invalid development media sort"); return { page, pageSize, search: (input.query ?? "").trim().slice(0, 100).replace(/[*,()]/g, ""), category: category as MediaQuery["category"], extension: (input.extension ?? "").replace(/[^a-z0-9]/gi, "").slice(0, 12).toLowerCase(), sort: sort as MediaSort }; }

function assertDevAccess() { if (!isLibraryDevBypassEnabled() && !isLocalLibraryPreviewConfigured()) throw new Error("Development library unavailable"); }
function mapAsset(row: Json): MediaAsset {
  const link = values(row.asset_sources)[0] ?? {}, source = values(link.source_files)[0] ?? {}, folder = values(source.source_folders)[0] ?? {};
  const verified = values(row.asset_destinations).find((item) => item.upload_status === "VERIFIED" && item.destination_google_file_id) ?? null;
  const extension = text(row.file_extension), mimeType = text(row.mime_type), id = String(row.id);
  const category = classifyMedia(mimeType, extension);
  const semantic=values(row.asset_semantic_index)[0]??{},downloadsEnabled=isLibraryDevBypassEnabled()&&!isLocalLibraryPreviewConfigured();
  return { id, sourceFileId: text(link.source_file_id), filename: String(row.file_name || "File"), extension, mimeType, category, sizeBytes: row.size_bytes == null ? null : Number(row.size_bytes), createdAt: null, modifiedAt: text(row.updated_at), sourceFolder: String(folder.source_name || "Central library"), storageDestination: verified ? "google-drive" : null, migrationStatus: String(verified?.upload_status || "NOT_STARTED"), verificationStatus: verified ? "VERIFIED" : "NONE", canPreview: Boolean(verified), canDownload: Boolean(verified)&&downloadsEnabled, previewUrl: verified ? `/api/dev/library/media/${id}/preview` : null, downloadUrl: verified&&downloadsEnabled ? `/api/dev/library/media/${id}/download` : null, thumbnailUrl: verified && (category === "image" || category === "video") ? `/api/dev/library/media/${id}/thumbnail` : null, shortCaption: text(semantic.short_caption), matchPercent: null };
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

export async function getDevMediaAssetsByIds(ids:string[],scores:Map<string,number>):Promise<MediaPage>{assertDevAccess();const unique=[...new Set(ids)].filter(id=>/^[0-9a-f-]{36}$/i.test(id)).slice(0,50);if(!unique.length)return{items:[],total:0,page:1,pageSize:25,totalPages:1};const{data,error}=await createServiceClient().from("assets").select(SELECT).in("id",unique);if(error)throw new Error("Live preview search asset query failed");const byId=new Map((data as unknown as Json[]).map(row=>[String(row.id),row]));const items=unique.flatMap(id=>{const row=byId.get(id);if(!row)return[];return[{...mapAsset(row),matchPercent:scores.get(id)??null}]});return{items,total:items.length,page:1,pageSize:items.length||25,totalPages:1}}

// Canonical Drive-media resolution for the development bypass lives in
// media-service.ts -> lib/media/resolve-location.ts (shared with
// production), not here.
