import "server-only";
import { headers } from "next/headers";
import { isLocalAuthBypassConfigured, isLoopbackHost } from "./local-auth-bypass-config";

/** TEMPORARY LOCAL AUTH BYPASS.
 * Authentication must be restored before public deployment.
 * This flag alone is insufficient: the request Host must also be loopback,
 * and the production launcher binds Next.js to 127.0.0.1 only. */
export async function isLocalAuthBypassActive() {
  if (!isLocalAuthBypassConfigured()) return false;
  return isLoopbackHost((await headers()).get("host"));
}
export { isLocalAuthBypassConfigured, isLoopbackHost } from "./local-auth-bypass-config";
