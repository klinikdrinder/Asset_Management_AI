import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "./app/lib/supabase/proxy";
import { isLocalAuthBypassConfigured, isLoopbackHost } from "./app/lib/local-auth-bypass-config";

export async function proxy(request: NextRequest) {
  // TEMPORARY LOCAL AUTH BYPASS. Restore authentication before public deployment.
  if(isLocalAuthBypassConfigured()&&isLoopbackHost(request.headers.get("host"))){
    return NextResponse.next();
  }
  const isLocalDevRoute=request.nextUrl.pathname === "/dev/library" || request.nextUrl.pathname.startsWith("/dev/library/") || request.nextUrl.pathname.startsWith("/dev/semantic-review") || request.nextUrl.pathname.startsWith("/api/dev/library/") || request.nextUrl.pathname.startsWith("/api/dev/semantic-review");
  if(isLocalDevRoute){
    if(!(process.env.NODE_ENV === "development" && process.env.KDI_LIBRARY_DEV_BYPASS === "true")) return new NextResponse("Not Found", { status: 404, headers: { "Cache-Control": "private, no-store" } });
    return NextResponse.next();
  }
  return updateSession(request);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|css|js)$).*)"],
};
