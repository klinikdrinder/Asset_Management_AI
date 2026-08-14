import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { createClient } from "@supabase/supabase-js";

function fileEnv() { return Object.fromEntries(readFileSync(".env.local", "utf8").replace(/^\uFEFF/, "").split(/\r?\n/).flatMap(line => { const m = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/); return m ? [[m[1], m[2].trim().replace(/^(['"])(.*)\1$/, "$2")]] : []; })); }
const env = { ...fileEnv(), ...process.env };
const email = String(env.KDI_ADMIN_EMAIL || "").trim().toLowerCase();
const password = String(env.KDI_ADMIN_PASSWORD || "");
const recoveryKey = String(env.KDI_ADMIN_RECOVERY_KEY || "");
const url = String(env.NEXT_PUBLIC_SUPABASE_URL || "");
const serviceKey = String(env.SUPABASE_SERVICE_ROLE_KEY || "");
const base = "http://127.0.0.1:3000";
if (!email || !password || !recoveryKey || !url || !serviceKey) throw new Error("acceptance environment unavailable");
const admin = createClient(url, serviceKey, { auth: { persistSession: false, autoRefreshToken: false } });
const results: Record<string, string | number> = {};
const pass = (name: string, condition: unknown) => { if (!condition) throw new Error(`${name} failed`); results[name] = "PASS"; };
const cookieFrom = (response: Response) => { const value = response.headers.get("set-cookie")?.split(";", 1)[0] || ""; if (!value.startsWith("kdi_admin_session=")) throw new Error("session cookie unavailable"); return value; };
async function login(loginEmail: string, loginPassword: string, remember = false) { return fetch(`${base}/api/admin-auth/login`, { method: "POST", redirect: "manual", headers: { "Content-Type": "application/json", Origin: base }, body: JSON.stringify({ email: loginEmail, password: loginPassword, remember }) }); }
async function protectedGet(path: string, cookie = "") { return fetch(`${base}${path}`, { redirect: "manual", headers: cookie ? { Cookie: cookie } : {} }); }
async function clearLock() { const { error } = await admin.from("admin_accounts").update({ failed_login_attempts: 0, locked_until: null }).eq("email", email); if (error) throw error; }

const { data: account, error: accountError } = await admin.from("admin_accounts").select("id,email,full_name,role,is_active,password_hash,failed_login_attempts,locked_until").eq("email", email).single();
if (accountError || !account) throw accountError || new Error("administrator missing");
pass("admin_record", account.role === "admin" && account.is_active === true && account.email === email && /^\$2[aby]\$/.test(account.password_hash));
pass("plaintext_not_in_database", account.password_hash !== password && account.password_hash !== recoveryKey && !JSON.stringify(account).includes(recoveryKey));

await clearLock();
let response = await login(email, password);
pass("correct_login", response.status === 200);
const shortCookie = cookieFrom(response);
response = await login(email, `${password}--incorrect`);
pass("incorrect_password_rejection", response.status === 401);
response = await login(`unknown-${Date.now()}@example.invalid`, password);
pass("unknown_email_rejection", response.status === 401);
response = await protectedGet("/admin", shortCookie);
pass("admin_authorization", response.status === 200);

response = await login(email, password, true);
pass("remember_me_login", response.status === 200 && /Max-Age=2592000/i.test(response.headers.get("set-cookie") || ""));
const rememberedCookie = cookieFrom(response);
response = await protectedGet("/library", rememberedCookie);
pass("session_persistence", response.status === 200);
response = await fetch(`${base}/api/admin-auth/logout`, { method: "POST", headers: { Cookie: rememberedCookie, Origin: base } });
pass("sign_out", response.status === 200);
response = await protectedGet("/library", rememberedCookie);
pass("library_blocked_after_sign_out", [302, 303, 307, 308].includes(response.status) && String(response.headers.get("location")).includes("/login"));

const changedPassword = `${password}#KdiChange9`;
response = await fetch(`${base}/api/admin-auth/change-password`, { method: "POST", headers: { Cookie: shortCookie, Origin: base, "Content-Type": "application/json" }, body: JSON.stringify({ currentPassword: password, newPassword: changedPassword }) });
pass("change_password", response.status === 200);
response = await login(email, changedPassword, true);
pass("changed_password_login", response.status === 200);
const preRecoveryCookie1 = cookieFrom(response);
response = await login(email, changedPassword, true);
const preRecoveryCookie2 = cookieFrom(response);
response = await fetch(`${base}/api/admin-auth/recover`, { method: "POST", headers: { Origin: base, "Content-Type": "application/json" }, body: JSON.stringify({ email, recoveryKey, newPassword: password }) });
pass("recovery_key_reset", response.status === 200);
const revoked = await Promise.all([protectedGet("/library", preRecoveryCookie1), protectedGet("/library", preRecoveryCookie2)]);
pass("previous_sessions_revoked", revoked.every(r => [302, 303, 307, 308].includes(r.status)));
response = await login(email, password, true);
pass("recovered_password_login", response.status === 200);
const mediaCookie = cookieFrom(response);

await clearLock();
for (let i = 0; i < 5; i++) await login(email, `${password}--lock-${i}`);
response = await login(email, password);
const { data: locked } = await admin.from("admin_accounts").select("failed_login_attempts,locked_until").eq("email", email).single();
pass("lockout_brute_force", response.status === 401 && Number(locked?.failed_login_attempts) >= 5 && new Date(String(locked?.locked_until)).getTime() > Date.now());
await clearLock();

const { count: assetCount } = await admin.from("assets").select("id", { count: "exact", head: true });
pass("asset_count", assetCount === 881); results.assets = assetCount || 0;
const { count: openClipCount } = await admin.from("asset_visual_embeddings").select("id", { count: "exact", head: true });
const { count: qwenCount } = await admin.from("asset_embeddings").select("id", { count: "exact", head: true });
pass("openclip_embeddings_preserved", openClipCount === 875);
pass("qwen_embeddings_preserved", qwenCount === 20);
const { data: media } = await admin.from("assets").select("id,file_name,mime_type").order("created_at").limit(200);
const image = media?.find(x => String(x.mime_type).startsWith("image/"));
const video = media?.find(x => String(x.mime_type).startsWith("video/"));
if (!image || !video) throw new Error("media fixtures unavailable");
for (const [name, path] of [["thumbnail", `/api/media/${image.id}/thumbnail`], ["image_preview", `/api/media/${image.id}/preview`], ["video_preview", `/api/media/${video.id}/preview`], ["download", `/api/media/${image.id}/download`]] as const) { response = await protectedGet(path, mediaCookie); pass(name, response.status === 200 || response.status === 206); }
for (const [name, path, marker] of [["filename_search", `/library?query=${encodeURIComponent(String(image.file_name).slice(0, 12))}`, ""], ["semantic_search", "/library?refine=clinic%20room", ""], ["filters", "/library?category=image", ""], ["pagination", "/library?page=2", ""]] as const) { response = await protectedGet(path, mediaCookie); const body = await response.text(); pass(name, response.status === 200 && !/secureError|could not be loaded/i.test(body) && body.length > marker.length); }

const ignored = new Set([".git", ".next", "node_modules", ".cache", ".pytest_cache", ".logs", "dist", "build", "reports"]);
function containsSecret(root: string): boolean { for (const name of readdirSync(root)) { if (ignored.has(name) || name.startsWith(".env")) continue; const path = join(root, name); const stat = statSync(path); if (stat.isDirectory()) { if (containsSecret(path)) return true; } else if (stat.size < 2_000_000) { const value = readFileSync(path, "utf8"); if (value.includes(password) || value.includes(recoveryKey)) return true; } } return false; }
pass("plaintext_not_in_repository", !containsSecret("."));
console.log(JSON.stringify(results, null, 2));
