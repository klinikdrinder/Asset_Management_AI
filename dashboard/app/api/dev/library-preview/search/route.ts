/**
 * Developer library-preview search. Explicitly NOT a production search authority.
 *
 * This exists so the offline preview tool keeps working against a local trusted database. It is
 * unreachable unless NODE_ENV is development, KDI_LOCAL_LIBRARY_PREVIEW is enabled and the request
 * arrives on a loopback host; otherwise it returns 404. Production search never reaches this file
 * and never falls back to it - the canonical route at /api/search has no branch to it at all.
 */
import { NextRequest, NextResponse } from "next/server";
import { isLocalLibraryPreviewActive } from "../../../../lib/library/local-preview";
import { localPreviewV3Search } from "../../../../lib/media/local-preview-search";
import { sameOrigin } from "../../../../lib/user-management";

const headers = { "Cache-Control": "private, no-store" };

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ error: "Request could not be verified." }, { status: 403, headers });
  if (!(await isLocalLibraryPreviewActive())) return NextResponse.json({ error: "Not found." }, { status: 404, headers });
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const raw = typeof body.query === "string" ? body.query.trim().slice(0, 300) : "";
  if (!raw) return NextResponse.json({ error: "A search query is required." }, { status: 400, headers });
  try {
    return NextResponse.json({ resolvedQuery: raw, ...(await localPreviewV3Search(raw)) }, { headers });
  } catch {
    return NextResponse.json({ error: "Search is temporarily unavailable." }, { status: 503, headers });
  }
}
