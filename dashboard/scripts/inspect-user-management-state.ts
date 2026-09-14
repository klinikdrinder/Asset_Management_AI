import { readFileSync } from "node:fs";
import { createClient } from "@supabase/supabase-js";

function localEnvironment() {
  return Object.fromEntries(readFileSync(".env.local", "utf8").replace(/^\uFEFF/, "").split(/\r?\n/).flatMap((line) => {
    const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    return match ? [[match[1], match[2].trim().replace(/^(['"])(.*)\1$/, "$2")]] : [];
  }));
}

const environment = { ...process.env, ...localEnvironment() };
const url = environment.NEXT_PUBLIC_SUPABASE_URL;
const serviceKey = environment.SUPABASE_SERVICE_ROLE_KEY;
if (!url || !serviceKey) throw new Error("Supabase server configuration is unavailable");
const client = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });

const [{ data: customAdmins, error: customError }, authResult] = await Promise.all([
  client.from("admin_accounts").select("id,email,role,is_active"),
  client.auth.admin.listUsers({ page: 1, perPage: 1000 }),
]);
for (const error of [customError, authResult.error]) if (error) throw error;
const authUsers = authResult.data.users;
const customEmails = new Set((customAdmins ?? []).map((row) => row.email));
const authEmails = new Set(authUsers.flatMap((user) => user.email ? [user.email.toLowerCase()] : []));

console.log(JSON.stringify({
  customAdminAccounts: customAdmins?.length ?? 0,
  activeCustomAdminAccounts: customAdmins?.filter((row) => row.is_active).length ?? 0,
  supabaseAuthUsers: authUsers.length,
  customAdminMatchesSupabaseAuth: [...customEmails].filter((email) => authEmails.has(email)).length,
}, null, 2));
