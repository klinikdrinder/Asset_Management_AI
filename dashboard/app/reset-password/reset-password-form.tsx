"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { createPasswordAuthClient } from "../lib/supabase/auth-client";

export function ResetPasswordForm() {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (password.length < 8) return setError("Password must be at least 8 characters.");
    if (password !== confirm) return setError("Passwords do not match.");
    setPending(true);
    const auth = createPasswordAuthClient(true);
    const result = await auth.auth.updateUser({ password });
    if (result.error) {
      setError("The reset link is invalid or expired.");
      setPending(false);
      return;
    }
    // Revoke all sessions so a stolen or pre-reset session cannot survive the credential change.
    const signedOut = await auth.auth.signOut({ scope: "global" });
    if (signedOut.error) await auth.auth.signOut({ scope: "local" });
    setDone(true);
    setPending(false);
  }

  if (done) return <div className="authSuccess"><p>Password updated successfully.</p><Link href="/login">Return to Sign In</Link></div>;
  return <form className="authForm" onSubmit={submit}>
    <label>New Password<input type="password" autoComplete="new-password" minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
    <label>Confirm New Password<input type="password" autoComplete="new-password" minLength={8} required value={confirm} onChange={(event) => setConfirm(event.target.value)} /></label>
    {error && <div className="authError" role="alert">{error}</div>}
    <button className="authPrimary" disabled={pending}>{pending ? "Resetting…" : "Reset Password"}</button>
  </form>;
}
