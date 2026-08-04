import "server-only";

import { cookies } from "next/headers";
import { getFirebaseAdminAuth } from "./admin";
import { FIREBASE_PROJECT_ID } from "./config";

export const FIREBASE_SESSION_COOKIE = "__session";
export const FIREBASE_CSRF_COOKIE = "kdi_csrf";
export const SESSION_MAX_AGE_MS = 8 * 60 * 60 * 1000;

export async function verifyFirebaseSession() {
  const value = (await cookies()).get(FIREBASE_SESSION_COOKIE)?.value;
  if (!value) return null;
  try {
    const decoded = await getFirebaseAdminAuth().verifySessionCookie(value, true);
    if (decoded.aud !== FIREBASE_PROJECT_ID || decoded.iss !== `https://session.firebase.google.com/${FIREBASE_PROJECT_ID}`
      || decoded.email_verified !== true || decoded.role !== "authenticated") return null;
    return decoded;
  } catch {
    return null;
  }
}
