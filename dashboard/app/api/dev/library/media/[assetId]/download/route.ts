import { isLibraryDevBypassEnabled } from "../../../../../../lib/library/dev-bypass";
import { fetchDevDriveMedia, mediaErrorResponse, mediaHeaders } from "../../../../../../media-service";
export const runtime = "nodejs"; export const dynamic = "force-dynamic";
export async function GET(request: Request, { params }: { params: Promise<{ assetId: string }> }) { if (!isLibraryDevBypassEnabled()) return new Response("Not Found", { status: 404 }); try { const media = await fetchDevDriveMedia((await params).assetId, request.headers.get("range"), request.signal); return new Response(media.upstream.body, { status: media.upstream.status, headers: mediaHeaders(media.record, media.upstream, "attachment") }); } catch (error) { return mediaErrorResponse(error); } }
