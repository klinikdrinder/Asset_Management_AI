import "server-only";

import { accessSync, constants, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { cert, type Credential } from "firebase-admin/app";
import { FIREBASE_PROJECT_ID } from "./config";

export type FirebaseAdminCredentialErrorCode =
  | "firebase_admin_credentials_unavailable"
  | "firebase_admin_credentials_malformed"
  | "firebase_admin_credentials_incomplete"
  | "firebase_admin_project_mismatch";

export class FirebaseAdminCredentialError extends Error {
  constructor(public readonly code: FirebaseAdminCredentialErrorCode) {
    super(code);
    this.name = "FirebaseAdminCredentialError";
  }
}

type ResolverOptions = { env?: Record<string, string | undefined>; cwd?: string; fallbackPaths?: string[]; expectedProjectId?: string };
type ServiceAccountShape = { type?: unknown; project_id?: unknown; client_email?: unknown; private_key?: unknown };

// Portable approved fallback: the repository-relative `.secrets` directory,
// resolved from the running process's working directory (the dashboard package,
// whose parent is the repository root). No machine-specific absolute path is
// embedded, so the allowlisted lookup travels with the clone. An explicit
// GOOGLE_APPLICATION_CREDENTIALS value still takes precedence in the resolver.
function approvedCandidates(cwd: string) {
  return [path.resolve(cwd, "..", ".secrets", "firebase-admin.json")];
}

function readableRegularFile(candidate: string) {
  try {
    const stat = statSync(candidate);
    accessSync(candidate, constants.R_OK);
    return stat.isFile();
  } catch { return false; }
}

export function resolveFirebaseAdminCredentialPath(options: ResolverOptions = {}) {
  const env = options.env ?? process.env;
  const cwd = options.cwd ?? process.cwd();
  const configured = env.GOOGLE_APPLICATION_CREDENTIALS?.trim();
  if (configured) {
    const resolved = path.resolve(/*turbopackIgnore: true*/ cwd, configured);
    if (!readableRegularFile(resolved)) throw new FirebaseAdminCredentialError("firebase_admin_credentials_unavailable");
    return resolved;
  }
  const seen = new Set<string>();
  for (const candidate of options.fallbackPaths ?? approvedCandidates(cwd)) {
    const resolved = path.resolve(/*turbopackIgnore: true*/ candidate);
    const normalized = path.normalize(resolved).toLowerCase();
    if (seen.has(normalized)) continue;
    seen.add(normalized);
    if (readableRegularFile(resolved)) return resolved;
  }
  throw new FirebaseAdminCredentialError("firebase_admin_credentials_unavailable");
}

function readValidatedServiceAccount(options: ResolverOptions = {}) {
  const credentialPath = resolveFirebaseAdminCredentialPath(options);
  let text: string;
  try {
    const bytes = readFileSync(/*turbopackIgnore: true*/ credentialPath);
    if (!bytes.length) throw new FirebaseAdminCredentialError("firebase_admin_credentials_malformed");
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch (error) {
    if (error instanceof FirebaseAdminCredentialError) throw error;
    throw new FirebaseAdminCredentialError("firebase_admin_credentials_malformed");
  }
  let parsed: ServiceAccountShape;
  try { parsed = JSON.parse(text) as ServiceAccountShape; }
  catch { throw new FirebaseAdminCredentialError("firebase_admin_credentials_malformed"); }
  if (parsed.type !== "service_account"
    || typeof parsed.project_id !== "string" || !parsed.project_id.trim()
    || typeof parsed.client_email !== "string" || !parsed.client_email.trim()
    || typeof parsed.private_key !== "string" || !parsed.private_key.trim()) {
    throw new FirebaseAdminCredentialError("firebase_admin_credentials_incomplete");
  }
  const env = options.env ?? process.env;
  const expectedProjectId = options.expectedProjectId ?? FIREBASE_PROJECT_ID;
  if (parsed.project_id !== expectedProjectId
    || (env.FIREBASE_PROJECT_ID && env.FIREBASE_PROJECT_ID !== expectedProjectId)
    || (env.NEXT_PUBLIC_FIREBASE_PROJECT_ID && env.NEXT_PUBLIC_FIREBASE_PROJECT_ID !== expectedProjectId)) {
    throw new FirebaseAdminCredentialError("firebase_admin_project_mismatch");
  }
  return { projectId: parsed.project_id, clientEmail: parsed.client_email, privateKey: parsed.private_key };
}

export function createExplicitFirebaseAdminCredential(options: ResolverOptions = {}): Credential {
  return cert(readValidatedServiceAccount(options));
}

export function firebaseAdminCredentialPreflight(options: ResolverOptions = {}) {
  resolveFirebaseAdminCredentialPath(options);
  createExplicitFirebaseAdminCredential(options);
  return { credentialResolved: true, projectMatched: true, metadataFallbackPrevented: true } as const;
}
