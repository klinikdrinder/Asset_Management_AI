import "server-only";
import { headers } from "next/headers";
import { isLoopbackHost } from "../local-auth-bypass-config";
export function isLocalLibraryPreviewConfigured(env:NodeJS.ProcessEnv=process.env){return env.NODE_ENV==="development"&&env.KDI_LOCAL_LIBRARY_PREVIEW==="true"}
export async function isLocalLibraryPreviewActive(){return isLocalLibraryPreviewConfigured()&&isLoopbackHost((await headers()).get("host"))}
export function isLocalLibraryMediaConfigured(env:NodeJS.ProcessEnv=process.env){return env.NODE_ENV==="development"&&(env.KDI_LIBRARY_DEV_BYPASS==="true"||env.KDI_LOCAL_LIBRARY_PREVIEW==="true")}
