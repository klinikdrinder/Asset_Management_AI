import { createClient } from "@supabase/supabase-js";
import { readFileSync } from "node:fs";

const REMOVE = [
  "kdimediaautomation+kdi-admin-link-1786941925684@gmail.com",
  "kdimediaautomation+kdi-admin-link-1786941962681@gmail.com",
  "kdimediaautomation+kdi-admin-link-1786942289942@gmail.com",
  "kdimediaautomation+kdi-admin-user-email-1786942289942@gmail.com",
  "kdimediaautomation+kdi-user-link-1786942289942@gmail.com",
] as const;
const OWNER = "kdimediaautomation@gmail.com";
const REAL_INVITEE = "iotiques@gmail.com";

function env(path: string) {
  return Object.fromEntries(readFileSync(path, "utf8").replace(/^\uFEFF/, "").split(/\r?\n/).flatMap(line => {
    const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    return match ? [[match[1], match[2].trim().replace(/^(['"])(.*)\1$/, "$2")]] : [];
  }));
}
function assert(value: unknown, message: string): asserts value { if (!value) throw new Error(message); }

const e = env(".env.local");
const client = createClient(e.NEXT_PUBLIC_SUPABASE_URL, e.SUPABASE_SERVICE_ROLE_KEY, { auth: { persistSession: false, autoRefreshToken: false } });
const apply = process.argv.includes("--apply");
const allEmails = [OWNER, REAL_INVITEE, ...REMOVE];

async function snapshot() {
  const [profiles, invitations, approved, authPage] = await Promise.all([
    client.from("app_users").select("user_id,email,management_role,is_active,invited_by").in("email", allEmails),
    client.from("user_invitations").select("id,auth_user_id,email,assigned_role,status,invited_by,send_count").in("email", allEmails),
    client.from("approved_app_users").select("normalized_email,role,is_active").in("normalized_email", allEmails),
    client.auth.admin.listUsers({ page: 1, perPage: 1000 }),
  ]);
  assert(!profiles.error, `app_users query failed: ${profiles.error?.code}`);
  assert(!invitations.error, `user_invitations query failed: ${invitations.error?.code}`);
  assert(!approved.error, `approved_app_users query failed: ${approved.error?.code}`);
  assert(!authPage.error, "Auth user query failed");
  const auth = authPage.data.users.filter(user => allEmails.includes((user.email ?? "").toLowerCase() as typeof allEmails[number]));
  return { profiles: profiles.data, invitations: invitations.data, approved: approved.data, auth };
}

const before = await snapshot();
const owner = before.profiles.find(row => row.email === OWNER);
const realProfile = before.profiles.find(row => row.email === REAL_INVITEE);
const realInvitation = before.invitations.find(row => row.email === REAL_INVITEE);
assert(owner?.management_role === "super_admin" && owner.is_active, "Protected owner validation failed");
assert(realProfile?.management_role === "user" && !realProfile.is_active, "Real invitee profile validation failed");
assert(realInvitation?.status === "pending" && realInvitation.auth_user_id === realProfile.user_id, "Real invitation validation failed");

const testProfiles = before.profiles.filter(row => REMOVE.includes(row.email as typeof REMOVE[number]));
const testIds = testProfiles.map(row => row.user_id);
const dependent = testIds.length ? await client.from("user_invitations").select("id,email,invited_by,status").in("invited_by", testIds) : { data: [], error: null };
assert(!dependent.error, "Dependent invitation query failed");
const unsafeDependent = (dependent.data ?? []).filter(row => !REMOVE.includes(row.email as typeof REMOVE[number]));
assert(unsafeDependent.length === 0, `Non-test invitations depend on a test inviter: ${unsafeDependent.map(row => row.email).join(",")}`);

const audit = await client.from("user_management_audit").select("id", { count: "exact", head: true }).in("target_email", REMOVE);
assert(!audit.error, "Audit count query failed");
console.log(JSON.stringify({ mode: apply ? "apply" : "dry-run", before: {
  profiles: before.profiles.map(row => ({ email: row.email, userId: row.user_id, role: row.management_role, active: row.is_active, invitedBy: row.invited_by })),
  invitations: before.invitations,
  approved: before.approved,
  auth: before.auth.map(user => ({ email: user.email, id: user.id })),
  dependentInvitations: dependent.data,
  preservedAuditRows: audit.count,
}}, null, 2));

if (apply) {
  const invitationDelete = await client.from("user_invitations").delete().in("email", REMOVE).select("id,email");
  assert(!invitationDelete.error, `Invitation deletion failed: ${invitationDelete.error?.code}`);
  const approvedDelete = await client.from("approved_app_users").delete().in("normalized_email", REMOVE).select("normalized_email");
  assert(!approvedDelete.error, `Approved-user deletion failed: ${approvedDelete.error?.code}`);
  const authToDelete = before.auth.filter(user => REMOVE.includes((user.email ?? "").toLowerCase() as typeof REMOVE[number]));
  for (const user of authToDelete) {
    const result = await client.auth.admin.deleteUser(user.id);
    assert(!result.error, `Auth deletion failed for allowlisted user ${user.id}`);
  }
  const after = await snapshot();
  const activeTestProfiles = after.profiles.filter(row => REMOVE.includes(row.email as typeof REMOVE[number]));
  const activeTestInvitations = after.invitations.filter(row => REMOVE.includes(row.email as typeof REMOVE[number]));
  const activeTestAuth = after.auth.filter(user => REMOVE.includes((user.email ?? "").toLowerCase() as typeof REMOVE[number]));
  assert(activeTestProfiles.length === 0 && activeTestInvitations.length === 0 && activeTestAuth.length === 0, "Test-account cleanup verification failed");
  const ownerAfter = after.profiles.find(row => row.email === OWNER);
  const realAfter = after.profiles.find(row => row.email === REAL_INVITEE);
  const realInviteAfter = after.invitations.find(row => row.email === REAL_INVITEE);
  assert(ownerAfter?.management_role === "super_admin" && ownerAfter.is_active, "Owner changed during cleanup");
  assert(realAfter?.management_role === "user" && !realAfter.is_active && realInviteAfter?.status === "pending", "Real invitation changed during cleanup");
  console.log(JSON.stringify({ result: "PASS", deleted: {
    invitations: invitationDelete.data,
    approvedUsers: approvedDelete.data,
    authUsers: authToDelete.map(user => ({ email: user.email, id: user.id })),
  }, retained: [OWNER, REAL_INVITEE], preservedAuditRows: audit.count }, null, 2));
}
