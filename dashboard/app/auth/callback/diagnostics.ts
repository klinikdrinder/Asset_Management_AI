import "server-only";
import { appendFile, mkdir } from "node:fs/promises";
import path from "node:path";

type Diagnostic = { stage: string; reason: string; status: number; cookieNames?: string[]; errorCode?: string; errorClass?: string; errorMessage?: string; redirectPath?: string };
const safe = (value: string | undefined, fallback = "none") => (value ?? fallback).toLowerCase().replace(/[^a-z0-9_.-]/g, "_").slice(0, 80);

export function sanitizedAuthError(error: unknown) {
  const value = error as { code?: string; name?: string; message?: string } | null;
  const message = value?.message?.toLowerCase() ?? "";
  const errorMessage = value?.name === "AuthRetryableFetchError" ? "supabase_token_endpoint_fetch_failed" : message.includes("code verifier") ? "pkce_verifier_rejected" : message.includes("flow state") ? "oauth_flow_state_rejected" : message.includes("expired") ? "authorization_code_expired" : "supabase_exchange_rejected";
  return { errorCode: safe(value?.code, "unknown"), errorClass: safe(value?.name, "auth_error"), errorMessage };
}

export async function recordAuthDiagnostic(entry: Diagnostic) {
  const directory = process.env.KDI_AUTH_LOG_DIR || path.join("D:\\Asset_Management_AI\\dashboard", ".logs");
  const line = JSON.stringify({ timestamp: new Date().toISOString(), stage: safe(entry.stage), reason: safe(entry.reason), status: entry.status, cookieNames: [...new Set(entry.cookieNames ?? [])].filter((name) => /^sb-[a-z0-9-]+-auth-token/.test(name)), errorCode: safe(entry.errorCode), errorClass: safe(entry.errorClass), errorMessage: safe(entry.errorMessage), redirectPath: entry.redirectPath?.startsWith("/") ? entry.redirectPath.split("?")[0] : "none" }) + "\n";
  try {
    const response = await fetch("http://127.0.0.1:3001/auth-callback", { method: "POST", headers: { "Content-Type": "application/json" }, body: line, signal: AbortSignal.timeout(1_000) });
    if (response.ok) return;
  } catch { /* local diagnostic sidecar may be unavailable outside development */ }
  try { await mkdir(directory, { recursive: true }); await appendFile(path.join(directory, "auth-callback.log"), line, "utf8"); }
  catch { console.warn("KDI_AUTH_CALLBACK", { reason: "diagnostic_write_failed" }); }
}
