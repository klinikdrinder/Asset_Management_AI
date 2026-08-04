const PROJECT_REF = "wcqqjpndlwsvatjuqnol";

export const secureCookieOptions = {
  httpOnly: true,
  sameSite: "lax" as const,
  secure: process.env.NODE_ENV === "production",
  path: "/",
};

export function getSupabasePublicConfig(env: NodeJS.ProcessEnv = process.env) {
  const url = env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const key = (env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? env.NEXT_PUBLIC_SUPABASE_ANON_KEY)?.trim();
  if (!url || !key) throw new Error("Authentication configuration is unavailable");
  const parsed = new URL(url);
  if (parsed.protocol !== "https:" || parsed.hostname !== `${PROJECT_REF}.supabase.co` || parsed.pathname !== "/") {
    throw new Error("Authentication configuration is unavailable");
  }
  if (!(key.startsWith("sb_publishable_") || key.split(".").length === 3)) {
    throw new Error("Authentication configuration is unavailable");
  }
  return { url, key };
}

export function safeReturnPath(value: string | null | undefined, fallback = "/") {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\") || /[\r\n]/.test(value)) return fallback;
  try {
    const parsed = new URL(value, "https://local.invalid");
    return parsed.origin === "https://local.invalid" ? `${parsed.pathname}${parsed.search}${parsed.hash}` : fallback;
  } catch {
    return fallback;
  }
}

export function applicationOrigin(requestUrl: string, env: NodeJS.ProcessEnv = process.env) {
  const configured = env.NEXT_PUBLIC_APP_URL?.trim();
  if (configured) {
    const parsed = new URL(configured);
    if (parsed.protocol !== "https:" && parsed.hostname !== "localhost" && parsed.hostname !== "127.0.0.1") throw new Error("Authentication configuration is unavailable");
    return parsed.origin;
  }
  const incoming = new URL(requestUrl);
  if (incoming.hostname !== "localhost" && incoming.hostname !== "127.0.0.1") throw new Error("Authentication configuration is unavailable");
  return incoming.origin;
}
