import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path: string) => readFileSync(path, "utf8");

test("production launcher activates only a verified pointer target", () => {
  const launcher = read("../scripts/start-kdi-media-library.cmd");
  assert.match(launcher, /current-release\.txt/);
  assert.match(launcher, /\.kdi-candidate-verified\.json/);
  assert.match(launcher, /npm\.cmd start/);
});

test("candidate build and deployment keep staging and production ports separate", () => {
  const build = read("../scripts/build-kdi-candidate.ps1");
  const deploy = read("../scripts/deploy-kdi-candidate.ps1");
  assert.match(build, /3001/);
  assert.doesNotMatch(build, /Stop-ScheduledTask|LocalPort 3000/);
  assert.match(build, /LocalPort \$StagingPort/);
  assert.match(deploy, /FileMode\]::CreateNew/);
  assert.match(deploy, /previous-release\.txt/);
  assert.match(deploy, /rollback/i);
  assert.match(deploy, /production-runtime\.json/);
  assert.match(deploy, /child\.Name -ne "node\.exe"/);
  assert.match(deploy, /child\.ParentProcessId -ne \[int\]\$state\.supervisorPid/);
  assert.match(deploy, /Test-MutexFree/);
  assert.match(deploy, /Stop-ProductionCleanly/);
  assert.match(deploy, /if \(\[int\]\$state\.childPid -gt 0\)/);
  const rollback = read("../scripts/rollback-kdi-release.ps1");
  assert.match(rollback, /if \(\[int\]\$state\.childPid -gt 0\)/);
});

test("health endpoint reports only a generic result", () => {
  const health = read("app/api/health/route.ts");
  assert.match(health, /createServiceClient/);
  assert.match(health, /status: "ok"/);
  assert.doesNotMatch(health, /SUPABASE_SERVICE_ROLE_KEY|error\.message|console\./);
});
