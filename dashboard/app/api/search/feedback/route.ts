/**
 * Search relevance feedback. Writes to the (previously empty) search_feedback table under the
 * caller's own RLS identity — the search_feedback_owner_insert policy only permits feedback on a
 * query in the caller's own session, so a user can never annotate someone else's search.
 */
import { NextRequest, NextResponse } from "next/server";
import { requireStaffOrAdmin } from "../../../auth";
import { sameOrigin } from "../../../lib/user-management";
import { resolveSearchDb } from "../../../lib/supabase/search-client";

const headers = { "Cache-Control": "private, no-store" };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const FEEDBACK_TYPES = new Set(["GOOD_MATCH", "BAD_MATCH", "MISSING_RESULT", "WRONG_RANK", "WRONG_TIMESTAMP", "WRONG_PERSON", "WRONG_TREATMENT", "OTHER"]);

export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({ error: "Request could not be verified." }, { status: 403, headers });
  const user = await requireStaffOrAdmin().catch(() => null);
  if (!user) return NextResponse.json({ error: "Authentication required." }, { status: 401, headers });

  const body = await request.json().catch(() => ({})) as Record<string, unknown>;
  const queryId = typeof body.queryId === "string" && uuid.test(body.queryId) ? body.queryId : null;
  const feedbackType = typeof body.feedbackType === "string" && FEEDBACK_TYPES.has(body.feedbackType) ? body.feedbackType : null;
  if (!queryId || !feedbackType) return NextResponse.json({ error: "A queryId and a valid feedbackType are required." }, { status: 400, headers });
  const resultId = typeof body.resultId === "string" && uuid.test(body.resultId) ? body.resultId : null;
  const assetId = typeof body.assetId === "string" && uuid.test(body.assetId) ? body.assetId : null;
  const sceneId = typeof body.sceneId === "string" && uuid.test(body.sceneId) ? body.sceneId : null;
  const comment = typeof body.comment === "string" ? (body.comment.trim().slice(0, 1000) || null) : null;

  const resolved = await resolveSearchDb(request, user);
  if ("error" in resolved) return NextResponse.json({ error: "Please sign in again to submit feedback." }, { status: 401, headers });

  const { error } = await resolved.client.from("search_feedback").insert({
    search_query_id: queryId, search_result_id: resultId, asset_id: assetId, scene_id: sceneId,
    user_id: user.userId, feedback_type: feedbackType, comment,
  });
  // 42501 = RLS denial (feedback on a query the caller does not own).
  if (error) return NextResponse.json({ error: "Feedback could not be recorded." }, { status: error.code === "42501" ? 403 : 500, headers });
  return NextResponse.json({ ok: true }, { headers });
}
