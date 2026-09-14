import { NextResponse } from "next/server";
import { createServiceClient } from "../../lib/supabase/service";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  try {
    const { error } = await createServiceClient().from("assets").select("id", { head: true, count: "exact" }).limit(1);
    if (error) throw error;
    return NextResponse.json({ status: "ok" }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ status: "unavailable" }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
