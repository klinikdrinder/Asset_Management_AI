import { fetchDevDriveThumbnail, mediaErrorResponse, thumbnailHeaders } from "../../../../../../media-service";
import { isLibraryDevBypassEnabled } from "../../../../../../lib/library/dev-bypass";

export const dynamic = "force-dynamic";

export async function GET(request: Request, { params }: { params: Promise<{ assetId: string }> }) {
  if (!isLibraryDevBypassEnabled()) return new Response("Not Found", { status: 404, headers: { "Cache-Control": "private, no-store" } });
  try {
    const thumbnail = await fetchDevDriveThumbnail((await params).assetId, request.signal, request.headers.get("if-none-match"));
    return new Response(thumbnail.upstream.status === 304 ? null : thumbnail.upstream.body, { status: thumbnail.upstream.status, headers: thumbnailHeaders(thumbnail.upstream, thumbnail.modifiedTime) });
  } catch (error) {
    return mediaErrorResponse(error);
  }
}
