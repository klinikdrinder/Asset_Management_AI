import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const repository = readFileSync("app/lib/media/repository.ts", "utf8");
test("media query supports bounded pagination and required sorts", () => {
  assert.match(repository, /PAGE_SIZES = \[25, 50, 100\]/);
  for (const sort of ["newest", "oldest", "smallest", "largest"]) assert.match(repository, new RegExp(`\\"${sort}\\"`));
  assert.match(repository, /Math\.max\(1/);
});
test("media repository is authenticated, RLS-backed, counted, and server paginated", () => {
  assert.match(repository, /server-only/); assert.match(repository, /requireStaffOrAdmin/); assert.match(repository, /liveRest/);
  assert.match(repository, /Prefer: "count=exact"/); assert.match(repository, /offset=\$\{offset\}/); assert.match(repository, /limit=\$\{query\.pageSize\}/);
  assert.doesNotMatch(repository, /SUPABASE_SERVICE_ROLE_KEY|createServiceClient/);
});
test("media repository filters filename category and extension on the server", () => {
  assert.match(repository, /file_name\.ilike/); assert.match(repository, /categoryRestFilter/); assert.match(repository, /file_extension=ilike/);
});
