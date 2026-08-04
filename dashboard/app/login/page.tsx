import Link from "next/link";
import { GoogleLoginButton } from "./google-login-button";

export const dynamic = "force-dynamic";

const safeErrors: Record<string, string> = {
  oauth_provider_error: "Google sign-in was declined or could not be completed.",
  missing_authorization_code: "The sign-in response was incomplete. Please start again.",
  missing_pkce_verifier: "The secure sign-in state expired or was replaced. Reset sign-in and try once.",
  code_exchange_failed: "The secure sign-in response could not be verified. Please try once more.",
  session_not_created: "A secure session could not be created.",
  user_lookup_failed: "The signed-in Google identity could not be verified.",
  profile_not_linked: "This Google account is not approved for the media library.",
  account_disabled: "This media-library account is disabled.",
  insufficient_role: "This account does not have an assigned library role.",
  oauth_start_failed: "Google sign-in could not be started.",
  auth_configuration_failed: "Authentication is temporarily unavailable.",
};

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const params = await searchParams;
  const reason = params.error && safeErrors[params.error] ? params.error : params.error ? "authentication_failed" : null;
  return <main className="authPage"><section className="authCard"><Link className="authBrand" href="/"><span>KDI</span><div>Central Media<small>Library</small></div></Link><div className="authKicker">SECURE SIGN IN</div><h1>Welcome back</h1><p>Continue with an approved KDI Google account to access the media library.</p>{reason&&<div className="authError" role="alert">{safeErrors[reason] ?? "Authentication failed."} <code>{reason}</code></div>}<GoogleLoginButton />{reason&&<a href="/auth/reset" className="textLink">Reset sign-in state</a>}<small className="authNotice">Access is limited to individually approved Staff and Administrator accounts.</small></section></main>;
}
