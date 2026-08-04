import type { DecodedIdToken } from "firebase-admin/auth";
import { FIREBASE_ISSUER, FIREBASE_PROJECT_ID } from "./config";

export type VerificationStage = "request_validation" | "firebase_token_verification" | "firebase_project_validation" | "verified_email_validation";

export class FirebaseIdentityError extends Error {
  constructor(public readonly stage: VerificationStage, public readonly code: string, public readonly status = 401) {
    super(code);
    this.name = "FirebaseIdentityError";
  }
}

export function validateVerifiedFirebaseIdentity(decoded: DecodedIdToken) {
  if (decoded.aud !== FIREBASE_PROJECT_ID) throw new FirebaseIdentityError("firebase_project_validation", "wrong_audience");
  if (decoded.iss !== FIREBASE_ISSUER) throw new FirebaseIdentityError("firebase_project_validation", "wrong_issuer");
  if (decoded.email_verified !== true || !decoded.email) throw new FirebaseIdentityError("verified_email_validation", "email_not_verified");
  if (decoded.firebase?.sign_in_provider !== "google.com" || !decoded.uid) {
    throw new FirebaseIdentityError("firebase_token_verification", "invalid_firebase_token");
  }
  return decoded;
}
