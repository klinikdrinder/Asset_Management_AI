import { fetchDevDriveThumbnail, mediaErrorResponse, thumbnailHeaders } from "../../../../../../media-service";
import { isLibraryDevBypassEnabled } from "../../../../../../lib/library/dev-bypass";

export const dynamic = "force-dynamic";

export async function GET(request: Request, { params }: { params: Promise<{ assetId: string }> }) {
  if (!isLibraryDevBypassEnabled()) return new Response("Not Found", { status: 404, headers: { "Cache-Control": "private, no-store" } });
  try {
    const result = await fetchDevDriveThumbnail((await params).assetId, request.signal, request.headers.get("if-none-match"));
    if (result.status === 304) return new Response(null, { status: 304, headers: { ETag: result.etag, "Cache-Control": "private, max-age=3600, stale-while-revalidate=86400" } });
    return new Response(new Uint8Array(result.bytes), { status: 200, headers: thumbnailHeaders(result.etag, result.contentType) });
  } catch (error) {
    return mediaErrorResponse(error, { operation: "thumbnail" });
  }
}
