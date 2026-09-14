import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json(
    { release: process.env.KDI_RELEASE_ID || "development" },
    { headers: { "Cache-Control": "no-store" } },
  );
}
