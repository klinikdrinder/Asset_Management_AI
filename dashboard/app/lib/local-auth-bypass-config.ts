/** TEMPORARY LOCAL AUTH BYPASS. Authentication must be restored before public deployment. */
export function isLocalAuthBypassConfigured(env: NodeJS.ProcessEnv = process.env) {
  return env.LOCAL_AUTH_BYPASS === "true";
}
export function isLoopbackHost(value: string | null | undefined) {
  const host = (value ?? "").trim().toLowerCase();
  return host === "localhost" || host.startsWith("localhost:") || host === "127.0.0.1" ||
    host.startsWith("127.0.0.1:") || host === "::1" || host === "[::1]" || host.startsWith("[::1]:");
}
