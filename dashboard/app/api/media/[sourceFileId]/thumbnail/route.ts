import { fetchDriveThumbnail, mediaErrorResponse, resolveThumbnailSignedUrl, thumbnailHeaders } from "../../../../media-service";

export const dynamic = "force-dynamic";

export async function GET(request: Request, { params }: { params: Promise<{ sourceFileId: string }> }) {
  const sourceFileId = (await params).sourceFileId;
  try {
    // Prefer a short-lived signed URL to the pre-generated WebP (offloads bytes to Storage). A
    // miss/transient here just falls through to the on-demand stream, which re-checks auth.
    try {
      const signed = await resolveThumbnailSignedUrl(sourceFileId);
      if (signed) return Response.redirect(signed, 302);
    } catch { /* fall through */ }
    const result = await fetchDriveThumbnail(sourceFileId, request.signal, request.headers.get("if-none-match"));
    if (result.status === 304) return new Response(null, { status: 304, headers: { ETag: result.etag, "Cache-Control": "private, max-age=3600, stale-while-revalidate=86400" } });
    return new Response(new Uint8Array(result.bytes), { status: 200, headers: thumbnailHeaders(result.etag, result.contentType) });
  } catch (error) {
    return mediaErrorResponse(error, { operation: "thumbnail" });
  }
}
