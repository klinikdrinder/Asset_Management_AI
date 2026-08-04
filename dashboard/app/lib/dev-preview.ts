import "server-only";
import { cookies, headers } from "next/headers";
import type { NextRequest } from "next/server";
export const DEV_PREVIEW_COOKIE="kdi_dev_frontend_preview";export type PreviewRole="STAFF"|"ADMIN";
function local(value:string){const v=value.trim().toLowerCase();return v==="::1"||v.startsWith("[::1]")||v.split(":")[0]==="localhost"||v.split(":")[0]==="127.0.0.1"}
export function previewEnabled(host:string,env:Record<string,string|undefined>=process.env){return env.NODE_ENV==="development"&&env.DEV_FRONTEND_PREVIEW==="true"&&local(host)}
export function previewRoleForRequest(r:NextRequest):PreviewRole|null{if(!previewEnabled(r.nextUrl.hostname))return null;const role=r.cookies.get(DEV_PREVIEW_COOKIE)?.value;return role==="STAFF"||role==="ADMIN"?role:null}
export async function getPreviewRole():Promise<PreviewRole|null>{const host=(await headers()).get("host")??"";if(!previewEnabled(host))return null;const role=(await cookies()).get(DEV_PREVIEW_COOKIE)?.value;return role==="STAFF"||role==="ADMIN"?role:null}
