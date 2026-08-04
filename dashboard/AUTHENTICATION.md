# Firebase authentication migration

Firebase Google popup authentication is the primary browser flow. Firebase
Admin verifies ID tokens and creates finite, revocation-checked server session
cookies. Supabase browser requests use the signed-in user's Firebase ID token
through the supported `accessToken` callback. Database authorization remains in
`public.app_users`; Firebase custom claims contain only `role: authenticated`.

Apply `supabase/migrations/202608040001_add_firebase_identity_bridge.sql` only
after Supabase Third-Party Auth trusts Firebase project `kdi-media-library`, then
run `supabase/verification/verify_firebase_identity_bridge.sql`. The migration
keeps the existing Supabase UUID primary key and adds a unique text Firebase UID.

Server-only configuration includes `GOOGLE_APPLICATION_CREDENTIALS`,
`FIREBASE_PROJECT_ID`, and `SUPABASE_SERVICE_ROLE_KEY`. Public Firebase web
configuration uses only the documented `NEXT_PUBLIC_FIREBASE_*` variables.
Never expose the Admin credential or service-role key to browser modules.

Protected routes are `/library/**`, `/admin/**`, the operational report routes,
and `/api/media/**`. Media APIs return 401 without a session and 403 for an
active session lacking authorization. Admin does not implicitly receive the
independent clinical or download permissions.

The legacy Supabase OAuth callback/session path remains temporarily available
for rollback. Retire it only after the Firebase live-login, Supabase token/RLS,
route, refresh, media, and logout acceptance checks pass.
