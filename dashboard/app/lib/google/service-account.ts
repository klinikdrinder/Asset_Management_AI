import "server-only";

import { readFileSync } from "node:fs";
import { JWT } from "google-auth-library";

// drive.readonly is intentionally the only scope requested: the KDI website
// only ever reads from the KDI Master Shared Drive, never writes or deletes.
const DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"];

export type GoogleServiceAccountErrorCode =
  | "google_service_account_credentials_unavailable"
  | "google_service_account_credentials_malformed"
  | "google_service_account_credentials_incomplete"
  | "google_service_account_private_key_malformed"
  | "google_service_account_authentication_failed"
  | "kdi_master_drive_id_unavailable";

export class GoogleServiceAccountError extends Error {
  constructor(public readonly code: GoogleServiceAccountErrorCode) {
    super(code);
    this.name = "GoogleServiceAccountError";
  }
}

type ServiceAccountKey = { clientEmail: string; privateKey: string };
type ServiceAccountJson = { type?: unknown; client_email?: unknown; private_key?: unknown };

// Google Cloud env-var conventions store the PEM private key with literal
// "\n" sequences (real newlines are not shell/dotenv safe). Decode both the
// escaped and already-unescaped forms, and tolerate a wrapping pair of quotes
// some .env tooling adds automatically.
function normalizePrivateKey(raw: string): string {
  const trimmed = raw.trim();
  const unquoted = trimmed.length >= 2 && trimmed.startsWith('"') && trimmed.endsWith('"') ? trimmed.slice(1, -1) : trimmed;
  const withNewlines = unquoted.includes("\\n") ? unquoted.replace(/\\n/g, "\n") : unquoted;
  return withNewlines.trim();
}

function readServiceAccountJson(text: string): ServiceAccountKey {
  let parsed: ServiceAccountJson;
  try {
    parsed = JSON.parse(text) as ServiceAccountJson;
  } catch {
    throw new GoogleServiceAccountError("google_service_account_credentials_malformed");
  }
  if (
    parsed.type !== "service_account" ||
    typeof parsed.client_email !== "string" || !parsed.client_email.trim() ||
    typeof parsed.private_key !== "string" || !parsed.private_key.trim()
  ) {
    throw new GoogleServiceAccountError("google_service_account_credentials_incomplete");
  }
  return { clientEmail: parsed.client_email.trim(), privateKey: normalizePrivateKey(parsed.private_key) };
}

function readServiceAccountFile(path: string): ServiceAccountKey {
  let text: string;
  try {
    text = readFileSync(/*turbopackIgnore: true*/ path, "utf8");
  } catch {
    throw new GoogleServiceAccountError("google_service_account_credentials_unavailable");
  }
  return readServiceAccountJson(text);
}

// Resolution order (first match wins), all server-only and never exposed to
// the browser:
//  1. GOOGLE_DRIVE_SERVICE_ACCOUNT_EMAIL + GOOGLE_DRIVE_SERVICE_ACCOUNT_PRIVATE_KEY
//     (dedicated Drive service account, discrete key-pair env vars).
//  2. GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_JSON (inline service-account JSON).
//  3. GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH, or the repository's
//     existing GOOGLE_APPLICATION_CREDENTIALS convention (already used for
//     Firebase Admin) pointing at a service-account JSON file.
export function resolveGoogleServiceAccount(env: NodeJS.ProcessEnv = process.env): ServiceAccountKey {
  const email = env.GOOGLE_DRIVE_SERVICE_ACCOUNT_EMAIL?.trim();
  const rawKey = env.GOOGLE_DRIVE_SERVICE_ACCOUNT_PRIVATE_KEY;
  if (email && rawKey) {
    const privateKey = normalizePrivateKey(rawKey);
    if (!privateKey.includes("BEGIN PRIVATE KEY")) throw new GoogleServiceAccountError("google_service_account_private_key_malformed");
    return { clientEmail: email, privateKey };
  }
  const inlineJson = env.GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_JSON?.trim();
  if (inlineJson) return readServiceAccountJson(inlineJson);
  const filePath = env.GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH?.trim() || env.GOOGLE_APPLICATION_CREDENTIALS?.trim();
  if (filePath) return readServiceAccountFile(filePath);
  throw new GoogleServiceAccountError("google_service_account_credentials_unavailable");
}

export function resolveKdiMasterDriveId(env: NodeJS.ProcessEnv = process.env): string {
  const id = env.KDI_MASTER_DRIVE_ID?.trim();
  if (!id) throw new GoogleServiceAccountError("kdi_master_drive_id_unavailable");
  return id;
}

let cachedClient: JWT | null = null;
let cachedClientKey = "";

function clientCacheKey(env: NodeJS.ProcessEnv): string {
  return [
    env.GOOGLE_DRIVE_SERVICE_ACCOUNT_EMAIL ?? "",
    env.GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH ?? env.GOOGLE_APPLICATION_CREDENTIALS ?? "",
    env.GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_JSON ? "inline" : "",
  ].join("|");
}

// google-auth-library's JWT client caches and transparently renews its own
// access token internally (authorize()/getAccessToken() reuse the cached
// token until it is near expiry, then re-sign a fresh JWT bearer assertion
// with the service-account private key) - there is never a manually
// generated or manually refreshed access token involved.
export function getDriveJwtClient(env: NodeJS.ProcessEnv = process.env): JWT {
  const key = clientCacheKey(env);
  if (cachedClient && cachedClientKey === key) return cachedClient;
  const account = resolveGoogleServiceAccount(env);
  cachedClient = new JWT({ email: account.clientEmail, key: account.privateKey, scopes: DRIVE_SCOPES });
  cachedClientKey = key;
  return cachedClient;
}

export async function getDriveAccessToken(env: NodeJS.ProcessEnv = process.env): Promise<string> {
  const client = getDriveJwtClient(env);
  let token: string | null | undefined;
  try {
    token = (await client.authorize()).access_token;
  } catch {
    // Never surface the underlying error: it may echo back key material or
    // Google's diagnostic text in ways that are unsafe to log verbatim.
    throw new GoogleServiceAccountError("google_service_account_authentication_failed");
  }
  if (!token) throw new GoogleServiceAccountError("google_service_account_authentication_failed");
  return token;
}

// For tests and the Phase 9 diagnostic only: forces the next call to mint a
// fresh client instead of reusing the cached one.
export function resetDriveServiceAccountCache() {
  cachedClient = null;
  cachedClientKey = "";
}
