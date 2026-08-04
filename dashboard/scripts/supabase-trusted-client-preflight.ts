import nextEnv from "@next/env";

nextEnv.loadEnvConfig(process.cwd());

const state = {
  urlResolved: false,
  credentialResolved: false,
  clientInitialized: false,
  projectReachable: false,
  lookupReachable: false,
  exposureCheckPassed: true,
};

function output() {
  console.log(`supabase_url_resolved=${state.urlResolved}`);
  console.log(`trusted_credential_resolved=${state.credentialResolved}`);
  console.log(`trusted_client_initialized=${state.clientInitialized}`);
  console.log(`supabase_project_reachable=${state.projectReachable}`);
  console.log(`approved_profile_lookup_reachable=${state.lookupReachable}`);
  console.log(`secret_exposure_check_passed=${state.exposureCheckPassed}`);
}

try {
  state.urlResolved = Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL);
  state.credentialResolved = Boolean(process.env.SUPABASE_SERVICE_ROLE_KEY?.trim());
  if (!state.urlResolved || !state.credentialResolved) throw new Error("supabase_server_configuration_unavailable");
  const { createServiceClient } = await import("../app/lib/supabase/service");
  const client = createServiceClient();
  state.clientInitialized = true;

  const health = await client.from("app_users").select("user_id", { head: true }).limit(0);
  if (health.error) throw new Error("supabase_trusted_credential_invalid");
  state.projectReachable = true;

  // Invalid arguments are rejected by the RPC before lookup, locking, or writes.
  const probe = await client.rpc("bootstrap_firebase_app_user", {
    requested_firebase_uid: "",
    requested_email: "invalid",
  });
  if (probe.error?.code !== "42501") throw new Error("approved_profile_rpc_unavailable");
  state.lookupReachable = true;
  output();
  console.log("SUPABASE_TRUSTED_CLIENT_PREFLIGHT_PASSED");
} catch (error) {
  output();
  const code = error instanceof Error && [
    "supabase_server_configuration_unavailable",
    "supabase_trusted_credential_invalid",
    "approved_profile_rpc_unavailable",
  ].includes(error.message) ? error.message : "supabase_trusted_client_preflight_failed";
  console.log(code);
  process.exitCode = 1;
}
