import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "./app/lib/supabase/proxy";
import { isLocalAuthBypassConfigured, isLoopbackHost } from "./app/lib/local-auth-bypass-config";

export async function proxy(request: NextRequest) {
  // TEMPORARY LOCAL AUTH BYPASS. Restore authentication before public deployment.
  if(isLocalAuthBypassConfigured()&&isLoopbackHost(request.headers.get("host"))){
    return NextResponse.next();
  }
  const isLibraryPreview=request.nextUrl.pathname==="/dev/library-preview"||request.nextUrl.pathname.startsWith("/dev/library-preview/");
  const isLocalDevRoute=request.nextUrl.pathname === "/dev/library" || request.nextUrl.pathname.startsWith("/dev/library/") || request.nextUrl.pathname.startsWith("/dev/semantic-review") || request.nextUrl.pathname.startsWith("/api/dev/library/") || request.nextUrl.pathname.startsWith("/api/dev/semantic-review") || isLibraryPreview;
  if(isLocalDevRoute){
    const previewAllowed=process.env.NODE_ENV==="development"&&process.env.KDI_LOCAL_LIBRARY_PREVIEW==="true"&&isLoopbackHost(request.headers.get("host"))&&(isLibraryPreview||request.nextUrl.pathname.startsWith("/api/dev/library/"));
    if(!(process.env.NODE_ENV === "development" && process.env.KDI_LIBRARY_DEV_BYPASS === "true")&&!previewAllowed) return new NextResponse("Not Found", { status: 404, headers: { "Cache-Control": "private, no-store" } });
    return NextResponse.next();
  }
  return updateSession(request);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|css|js)$).*)"],
};
