
import { isLocalLibraryMediaConfigured } from "../../../../../../lib/library/local-preview";
import { isLibraryDevBypassEnabled } from "../../../../../../lib/library/dev-bypass";
import { fetchDevDriveMedia, mediaErrorResponse, mediaHeaders } from "../../../../../../media-service";
export const runtime = "nodejs"; export const dynamic = "force-dynamic";
export async function GET(request: Request, { params }: { params: Promise<{ assetId: string }> }) { if (!isLocalLibraryMediaConfigured()) return new Response("Not Found", { status: 404 }); try { const media = await fetchDevDriveMedia((await params).assetId, request.headers.get("range"), request.signal); if (media.record.extension.toLowerCase() === "pptx") return new Response("Preview unavailable for this format", { status: 415, headers: { "Cache-Control": "private, no-store" } }); return new Response(media.upstream.body, { status: media.upstream.status, headers: mediaHeaders(media.record, media.upstream, "inline") }); } catch (error) { return mediaErrorResponse(error, { operation: "preview" }); } }
