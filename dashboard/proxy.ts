import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "./app/lib/supabase/proxy";

export async function proxy(request: NextRequest) {
  if ((request.nextUrl.pathname === "/dev/library" || request.nextUrl.pathname.startsWith("/dev/library/") || request.nextUrl.pathname.startsWith("/api/dev/library/")) && !(process.env.NODE_ENV === "development" && process.env.KDI_LIBRARY_DEV_BYPASS === "true")) return new NextResponse("Not Found", { status: 404, headers: { "Cache-Control": "private, no-store" } });
  return updateSession(request);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|css|js)$).*)"],
};
