import "server-only";

import { getApp, getApps, initializeApp } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";
import { createExplicitFirebaseAdminCredential, FirebaseAdminCredentialError } from "./admin-credentials";
import { FIREBASE_PROJECT_ID } from "./config";

export class FirebaseAdminConfigurationError extends Error {
  constructor(public readonly code = "firebase_admin_initialization_failed") {
    super(code);
    this.name = "FirebaseAdminConfigurationError";
  }
}

export function getFirebaseAdminApp() {
  if (getApps().length) return getApp();
  try {
    return initializeApp({ credential: createExplicitFirebaseAdminCredential(), projectId: FIREBASE_PROJECT_ID });
  } catch (error) {
    if (error instanceof FirebaseAdminCredentialError) throw error;
    throw new FirebaseAdminConfigurationError();
  }
}

export function getFirebaseAdminAuth() {
  return getAuth(getFirebaseAdminApp());
}
