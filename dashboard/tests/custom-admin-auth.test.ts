import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const read = (path: string) => readFileSync(path, "utf8");

test("custom administrator passwords use bcrypt and never plaintext storage", () => {
  const password = read("app/lib/admin-auth/password.ts");
  const bootstrap = read("scripts/create-admin.ts");
  assert.match(password, /bcrypt/);
  assert.match(password, /hashPassword/);
  assert.match(password, /verifyPassword/);
  assert.match(bootstrap, /password_hash:hash/);
  assert.doesNotMatch(bootstrap, /password:\s*password/);
});

test("recovery key remains server-only and revokes existing sessions", () => {
  const session = read("app/lib/admin-auth/session.ts");
  const recovery = read("app/api/admin-auth/recover/route.ts");
  assert.match(session, /process\.env\.KDI_ADMIN_RECOVERY_KEY/);
  assert.match(session, /timingSafeEqual/);
  assert.match(recovery, /verifyRecoveryKey/);
  assert.match(recovery, /revokeAllSessions/);
  assert.doesNotMatch(read(".env.example"), /NEXT_PUBLIC_KDI_ADMIN_RECOVERY_KEY/);
});

test("login provides generic failures lockout and remember-me sessions", () => {
  const login = read("app/api/admin-auth/login/route.ts");
  const session = read("app/lib/admin-auth/session.ts");
  assert.match(login, /Invalid email or password/);
  assert.match(login, /LOGIN_FAILURE_LIMIT/);
  assert.match(login, /locked_until/);
  assert.match(login, /body\.remember===true/);
  assert.match(session, /REMEMBER_SESSION_SECONDS/);
  assert.match(session, /httpOnly:true/);
  assert.match(session, /sameSite:"lax"/);
});

test("password changes and sign out revoke server-side sessions", () => {
  assert.match(read("app/api/admin-auth/change-password/route.ts"), /revokeAllSessions/);
  assert.match(read("app/api/admin-auth/logout/route.ts"), /revokeCurrentSession/);
  assert.match(read("proxy.ts"), /updateSession\(request\)/);
});
