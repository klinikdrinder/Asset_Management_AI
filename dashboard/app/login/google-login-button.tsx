"use client";

import {
  getRedirectResult,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithRedirect,
  signOut,
  type User,
} from "firebase/auth";
import { useEffect, useRef, useState } from "react";
import { getFirebaseClientAuth } from "../lib/firebase/client";

const LOGIN_TIMEOUT_MS = 45_000;
const REDIRECT_PENDING_KEY = "kdi_google_redirect_pending";
const safeStages = new Set([
  "popup_started", "popup_completed", "bootstrap_started", "bootstrap_succeeded",
  "token_refreshed", "session_started", "session_succeeded", "redirect_started", "login_failed",
]);

type ApiResult = { landing?: string; code?: string; message?: string; stage?: string; refreshRequired?: boolean };
type LoginMode = "popup" | "redirect";

function diagnostic(stage: string) {
  if (safeStages.has(stage)) console.info(stage);
}

function csrfCookie() {
  const value = document.cookie.split(";").map((part) => part.trim())
    .find((part) => part.startsWith("kdi_csrf="))?.slice("kdi_csrf=".length) ?? "";
  try { return decodeURIComponent(value); } catch { return ""; }
}

function firebaseErrorCode(error: unknown) {
  return typeof error === "object" && error !== null && "code" in error && typeof error.code === "string"
    ? error.code : "";
}

function safeFirebaseMessage(error: unknown) {
  switch (firebaseErrorCode(error)) {
    case "auth/popup-blocked":
      return "Google sign-in was blocked by your browser. Allow popups for this site or use the redirect sign-in option.";
    case "auth/popup-closed-by-user": return "Google sign-in was closed before it completed. Please try again.";
    case "auth/cancelled-popup-request": return "The Google sign-in request was cancelled. Please try again.";
    case "auth/unauthorized-domain": return "Google sign-in is not available from this site.";
    case "auth/operation-not-allowed": return "Google sign-in is temporarily unavailable.";
    case "auth/network-request-failed": return "A network error interrupted Google sign-in. Please check your connection and try again.";
    case "auth/internal-error": return "Google sign-in could not be completed. Please try again.";
    default: return "Sign-in could not be completed. Please try again.";
  }
}

function apiMessage(result: ApiResult, fallback: string) {
  if (["account_not_approved", "account_inactive", "profile_link_conflict"].includes(result.code ?? "")) {
    return "Your Google account was authenticated, but it is not approved to access this application.";
  }
  return result.message || fallback;
}

async function jsonResponse(response: Response): Promise<ApiResult> {
  try { return await response.json() as ApiResult; } catch { return {}; }
}

async function withTimeout<T>(operation: (signal: AbortSignal) => Promise<T>) {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      operation(controller.signal),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => { controller.abort(); reject(new Error("login_timeout")); }, LOGIN_TIMEOUT_MS);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

async function popupWithTimeout<T>(popup: Promise<T>) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      popup,
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("login_timeout")), LOGIN_TIMEOUT_MS);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

async function establishSession(user: User) {
  const firstToken = await user.getIdToken(false);
  diagnostic("bootstrap_started");
  const bootstrap = await withTimeout((signal) => fetch("/api/auth/bootstrap", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ idToken: firstToken }), credentials: "same-origin", signal,
  }));
  const bootstrapResult = await jsonResponse(bootstrap);
  if (!bootstrap.ok) throw new LoginFlowError(apiMessage(bootstrapResult, "Application access could not be approved."));
  diagnostic("bootstrap_succeeded");

  const refreshedToken = await user.getIdToken(bootstrapResult.refreshRequired === true);
  diagnostic("token_refreshed");
  diagnostic("session_started");
  const session = await withTimeout((signal) => fetch("/api/auth/session", {
    method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfCookie() },
    body: JSON.stringify({ idToken: refreshedToken }), credentials: "same-origin", signal,
  }));
  const result = await jsonResponse(session);
  if (!session.ok || !result.landing) throw new LoginFlowError(apiMessage(result, "A secure session could not be created."));
  diagnostic("session_succeeded");
  return result.landing;
}

class LoginFlowError extends Error {}

let redirectResultPromise: ReturnType<typeof getRedirectResult> | null = null;

export function GoogleLoginButton() {
  const active = useRef<LoginMode | null>(null);
  const popupInFlight = useRef(false);
  const navigating = useRef(false);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");

  async function finish(user: User) {
    const landing = await establishSession(user);
    navigating.current = true;
    diagnostic("redirect_started");
    window.location.replace(landing);
  }

  async function fail(error: unknown) {
    diagnostic("login_failed");
    setMessage(error instanceof LoginFlowError ? error.message
      : error instanceof Error && error.message === "login_timeout"
        ? "Google sign-in took too long. Please try again."
        : safeFirebaseMessage(error));
    await signOut(getFirebaseClientAuth()).catch(() => undefined);
  }

  async function startGoogleLogin() {
    if (active.current) return;
    if (popupInFlight.current) {
      setMessage("The previous Google window is still open. Close it before trying again.");
      return;
    }
    active.current = "popup";
    popupInFlight.current = true;
    setPending(true);
    setMessage("");
    let popupCreated = false;
    try {
      const auth = getFirebaseClientAuth();
      diagnostic("popup_started");
      // This must remain the first asynchronous operation in the click handler.
      const popupPromise = signInWithPopup(auth, new GoogleAuthProvider());
      popupCreated = true;
      void popupPromise.then(() => { popupInFlight.current = false; }, () => { popupInFlight.current = false; });
      const result = await popupWithTimeout(popupPromise);
      diagnostic("popup_completed");
      await finish(result.user);
    } catch (error) {
      if (!popupCreated) popupInFlight.current = false;
      await fail(error);
    } finally {
      if (!navigating.current) { active.current = null; setPending(false); }
    }
  }

  async function startRedirectLogin() {
    if (active.current || popupInFlight.current) return;
    active.current = "redirect";
    setPending(true);
    setMessage("");
    sessionStorage.setItem(REDIRECT_PENDING_KEY, "1");
    diagnostic("redirect_started");
    try {
      await signInWithRedirect(getFirebaseClientAuth(), new GoogleAuthProvider());
    } catch (error) {
      sessionStorage.removeItem(REDIRECT_PENDING_KEY);
      await fail(error);
      active.current = null;
      setPending(false);
    }
  }

  useEffect(() => {
    if (sessionStorage.getItem(REDIRECT_PENDING_KEY) !== "1" || active.current) return;
    active.current = "redirect";
    setPending(true);
    setMessage("");
    sessionStorage.removeItem(REDIRECT_PENDING_KEY);
    const auth = getFirebaseClientAuth();
    redirectResultPromise ??= getRedirectResult(auth);
    void redirectResultPromise.then(async (result) => {
      if (!result) throw new LoginFlowError("The redirect sign-in response was incomplete. Please try again.");
      await finish(result.user);
    }).catch(fail).finally(() => {
      if (!navigating.current) { active.current = null; setPending(false); }
    });
  }, []);

  return <>
    <div className="authActions">
      <button className="googleButton" type="button" disabled={pending} onClick={startGoogleLogin}>
        <span aria-hidden="true">G</span>{pending ? "Signing in…" : "Continue with Google"}
      </button>
      <button className="textLink redirectButton" type="button" disabled={pending} onClick={startRedirectLogin}>
        Continue using redirect
      </button>
    </div>
    {message && <div className="authError" role="alert">{message}</div>}
  </>;
}
