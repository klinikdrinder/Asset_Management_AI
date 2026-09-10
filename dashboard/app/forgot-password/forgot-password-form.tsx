"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError("");
    try {
      const response = await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(body.message ?? "We couldn't send the reset email right now. Please try again.");
        return;
      }
      setMessage(body.message ?? "We've sent password reset instructions to your email address.");
    } catch {
      setError("We couldn't send the reset email right now. Please try again.");
    } finally {
      setPending(false);
    }
  }

  if (message) return <div className="authSuccess"><h2>Check your email</h2><p>{message}</p><Link href="/login">Back to Sign In</Link></div>;
  return <form className="authForm" onSubmit={submit}>
    <label>Email<input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
    {error && <div className="authError" role="alert">{error}</div>}
    <button className="authPrimary" disabled={pending}>{pending ? "Sending…" : "Send Reset Link"}</button>
    <div className="authLinks"><Link href="/login">Back to Sign In</Link></div>
  </form>;
}
