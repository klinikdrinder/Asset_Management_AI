import Link from "next/link";
import { createClient } from "../lib/supabase/server";
import { ResetPasswordForm } from "./reset-password-form";

export const dynamic = "force-dynamic";

export default async function ResetPasswordPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  return <main className="authPage"><section className="authCard">
    <Link className="authBrand" href="/"><span>KDI</span><div>Central Media<small>Library</small></div></Link>
    <div className="authKicker">SECURE RESET</div>
    <h1>Reset Password</h1>
    {user ? <ResetPasswordForm /> : <div className="authError" role="alert">This reset link is invalid or expired. <Link href="/forgot-password">Request a new reset link</Link>.</div>}
  </section></main>;
}
