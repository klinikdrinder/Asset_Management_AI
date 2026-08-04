import "server-only";

import type { DecodedIdToken } from "firebase-admin/auth";
import { FirebaseAdminConfigurationError, getFirebaseAdminAuth } from "./admin";
import { FirebaseAdminCredentialError } from "./admin-credentials";
import { FirebaseIdentityError, validateVerifiedFirebaseIdentity } from "./identity-validation";
export { FirebaseIdentityError } from "./identity-validation";

function sdkErrorCode(error: unknown) {
  return typeof error === "object" && error !== null && "code" in error && typeof error.code === "string" ? error.code : "";
}

export async function verifyFirebaseIdToken(token: string, checkRevoked = true): Promise<DecodedIdToken> {
  if (!token || token.length > 16_384) throw new FirebaseIdentityError("request_validation", "missing_or_invalid_token", 400);
  let decoded: DecodedIdToken;
  try {
    decoded = await getFirebaseAdminAuth().verifyIdToken(token, checkRevoked);
  } catch (error) {
    if (error instanceof FirebaseAdminConfigurationError || error instanceof FirebaseAdminCredentialError) {
      throw new FirebaseIdentityError("firebase_token_verification", "firebase_admin_credential_unavailable", 503);
    }
    const code = sdkErrorCode(error);
    if (["app/invalid-credential", "auth/invalid-credential", "auth/insufficient-permission"].includes(code)) {
      throw new FirebaseIdentityError("firebase_token_verification", "firebase_admin_credential_unavailable", 503);
    }
    if (code === "auth/id-token-expired") throw new FirebaseIdentityError("firebase_token_verification", "firebase_token_expired");
    if (code === "auth/id-token-revoked") throw new FirebaseIdentityError("firebase_token_verification", "firebase_token_revoked");
    throw new FirebaseIdentityError("firebase_token_verification", "invalid_firebase_token");
  }
  return validateVerifiedFirebaseIdentity(decoded);
}
