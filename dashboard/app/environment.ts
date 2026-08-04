const PROJECT = "wcqqjpndlwsvatjuqnol";

function payload(token: string): Record<string, unknown> {
  const part = token.split(".")[1];
  if (!part) throw new Error("Reader token is malformed");
  try { return JSON.parse(Buffer.from(part, "base64url").toString("utf8")); }
  catch { throw new Error("Reader token is malformed"); }
}

export function validateDashboardEnvironment(env: Record<string, string | undefined> = process.env) {
  const {url,key}=validateDashboardPublicEnvironment(env);
  const token = env.SUPABASE_DASHBOARD_ACCESS_TOKEN?.trim();
  if (!token) throw new Error("Authorized dashboard credentials are not configured");
  const claims = payload(token);
  const metadata = (claims.app_metadata || {}) as Record<string, unknown>;
  if (claims.aud !== "authenticated" || !claims.sub) throw new Error("Reader token is not authenticated");
  if (typeof claims.exp !== "number" || claims.exp <= Date.now() / 1000) throw new Error("Reader token is expired");
  if (typeof claims.iss !== "string" || !claims.iss.startsWith(`${url}/auth/v1`)) throw new Error("Reader token belongs to a different project");
  if (metadata.kdi_media_reader !== "true") throw new Error("Reader token is missing the required reader claim");
  if (metadata.kdi_media_access !== true) throw new Error("Reader token has an invalid access claim");
  return { url, key, token };
}

export function validateDashboardPublicEnvironment(env: Record<string, string | undefined> = process.env) {
  const url = env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
  if (!url || !key) throw new Error("Authorized dashboard credentials are not configured");
  let parsed: URL;
  try { parsed = new URL(url); } catch { throw new Error("Supabase URL is invalid"); }
  if (parsed.protocol !== "https:" || parsed.hostname !== `${PROJECT}.supabase.co` || parsed.pathname !== "/") throw new Error("Supabase project does not match the approved project");
  if (payload(key).role !== "anon") throw new Error("Configured API key is not a legacy anon key");
  return { url, key };
}
