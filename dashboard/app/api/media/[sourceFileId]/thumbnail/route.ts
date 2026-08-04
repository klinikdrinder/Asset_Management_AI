import { fetchDriveThumbnail, mediaErrorResponse, thumbnailHeaders } from "../../../../media-service";

export const dynamic = "force-dynamic";

export async function GET(request: Request, { params }: { params: Promise<{ sourceFileId: string }> }) {
  try {
    const thumbnail = await fetchDriveThumbnail((await params).sourceFileId, request.signal, request.headers.get("if-none-match"));
    return new Response(thumbnail.upstream.status === 304 ? null : thumbnail.upstream.body, { status: thumbnail.upstream.status, headers: thumbnailHeaders(thumbnail.upstream, thumbnail.modifiedTime) });
  } catch (error) {
    return mediaErrorResponse(error);
  }
}
