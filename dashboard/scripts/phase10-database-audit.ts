import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";

function loadEnv(file: string): Record<string, string> {
  try {
    return Object.fromEntries(readFileSync(file, "utf8").replace(/^\uFEFF/, "").split(/\r?\n/).flatMap((line) => {
      const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
      return match ? [[match[1], match[2].trim().replace(/^(['"])(.*)\1$/, "$2")]] : [];
    }));
  } catch { return {}; }
}

const fileEnv = loadEnv(path.join(process.cwd(), ".env.local"));
const parentEnv = loadEnv(path.resolve(process.cwd(), "..", ".env.local"));
const env = { ...parentEnv, ...fileEnv, ...process.env };
const url = fileEnv.NEXT_PUBLIC_SUPABASE_URL || env.NEXT_PUBLIC_SUPABASE_URL;
const token = [fileEnv.SUPABASE_DASHBOARD_ACCESS_TOKEN, parentEnv.SUPABASE_DASHBOARD_ACCESS_TOKEN, process.env.SUPABASE_DASHBOARD_ACCESS_TOKEN].find((value) => value?.startsWith("sbp_"));
if (!url || !token) throw new Error("Supabase management configuration unavailable");
const projectRef = new URL(url).hostname.split(".")[0];

async function sql<T = unknown>(query: string): Promise<T> {
  const response = await fetch(`https://api.supabase.com/v1/projects/${projectRef}/database/query`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!response.ok) throw new Error(`Database query failed (${response.status}): ${(await response.text()).slice(0, 1000)}`);
  return response.json() as Promise<T>;
}

const requestedTables = [
  "assets", "asset_ai_profiles", "asset_scenes", "asset_events", "asset_keyframes", "scene_people", "person_appearances",
  "scene_treatments", "scene_anatomy", "scene_actions", "scene_relationships", "clinical_observations", "scene_environment",
  "scene_cinematography", "scene_composition", "asset_transcript_chunks", "ocr_observations", "scene_narratives",
  "asset_search_documents", "scene_search_documents", "scene_embeddings", "keyframe_embeddings", "transcript_embeddings",
  "asset_visual_embeddings", "asset_embeddings", "search_sessions", "search_queries", "search_results", "search_feedback",
  "asset_access_control", "semantic_analysis_runs", "semantic_layer_definitions", "asset_semantic_layers", "semantic_assertions",
  "semantic_assertion_evidence", "semantic_review_sessions", "semantic_review_decisions", "semantic_review_revisions",
  "gold_standard_sets", "gold_standard_assets", "gold_standard_assertions", "asset_search_concepts", "semantic_narratives",
  "narrative_claims", "narrative_claim_evidence", "application_users", "app_users", "source_files", "asset_sources", "asset_destinations",
];
const quotedNames = requestedTables.map((name) => `'${name.replaceAll("'", "''")}'`).join(",");

const migrationRoots = [path.resolve(process.cwd(), "..", "supabase", "migrations"), path.join(process.cwd(), "supabase", "migrations")];
const discoveredMigrationFiles = migrationRoots.flatMap((root) => readdirSync(root, { withFileTypes: true })
  .filter((entry) => entry.isFile() && entry.name.endsWith(".sql"))
  .map((entry) => {
    const content = readFileSync(path.join(root, entry.name), "utf8");
    const match = entry.name.match(/^(\d+)_?(.*)\.sql$/);
    return { root: path.relative(process.cwd(), root) || ".", file: entry.name, version: match?.[1] ?? entry.name, name: match?.[2] ?? "", sha256: createHash("sha256").update(content).digest("hex"), bytes: Buffer.byteLength(content) };
  })).sort((a, b) => a.file.localeCompare(b.file));
const migrationFiles = [...new Map(discoveredMigrationFiles.sort((a,b) => a.bytes-b.bytes).map((file) => [file.file,file])).values()]
  .sort((a,b) => a.file.localeCompare(b.file));

const [migrationColumns, liveMigrations, tables, foreignKeys, indexes, policies, preservationCounts, server] = await Promise.all([
  sql(`select column_name,data_type from information_schema.columns where table_schema='supabase_migrations' and table_name='schema_migrations' order by ordinal_position`),
  sql(`select to_jsonb(m) as migration from supabase_migrations.schema_migrations m order by version`),
  sql(`select c.relname as table_name, c.relrowsecurity as rls_enabled, coalesce(s.n_live_tup,0)::bigint as estimated_rows,
    (select jsonb_agg(jsonb_build_object('column',a.attname,'type',pg_catalog.format_type(a.atttypid,a.atttypmod),'nullable',not a.attnotnull) order by a.attnum)
       from pg_attribute a where a.attrelid=c.oid and a.attnum>0 and not a.attisdropped) as columns,
    (select jsonb_agg(pg_get_constraintdef(k.oid)) from pg_constraint k where k.conrelid=c.oid and k.contype='p') as primary_key
   from pg_class c join pg_namespace n on n.oid=c.relnamespace left join pg_stat_user_tables s on s.relid=c.oid
   where n.nspname='public' and c.relkind in ('r','p') and c.relname in (${quotedNames}) order by c.relname`),
  sql(`select tc.table_name,tc.constraint_name,kcu.column_name,ccu.table_name as foreign_table_name,ccu.column_name as foreign_column_name
    from information_schema.table_constraints tc join information_schema.key_column_usage kcu using(constraint_catalog,constraint_schema,constraint_name)
    join information_schema.constraint_column_usage ccu using(constraint_catalog,constraint_schema,constraint_name)
    where tc.table_schema='public' and tc.constraint_type='FOREIGN KEY' and tc.table_name in (${quotedNames}) order by tc.table_name,tc.constraint_name,kcu.ordinal_position`),
  sql(`select tablename as table_name,indexname,indexdef from pg_indexes where schemaname='public' and tablename in (${quotedNames}) order by tablename,indexname`),
  sql(`select tablename as table_name,policyname,permissive,roles,cmd,qual,with_check from pg_policies where schemaname='public' and tablename in (${quotedNames}) order by tablename,policyname`),
  sql(`select t.table_name,case when to_regclass('public.'||t.table_name) is null then null else (xpath('/row/c/text()',query_to_xml(format('select count(*) c from public.%I',t.table_name),false,true,'')))[1]::text::bigint end as row_count
    from (values ${["assets","asset_visual_embeddings","asset_embeddings","asset_ai_profiles","asset_search_documents","scene_search_documents","asset_scenes","asset_keyframes","asset_transcript_chunks","ocr_observations","scene_narratives","asset_access_control","application_users","app_users","source_files","asset_sources","asset_destinations"].map(n=>`('${n}')`).join(",")}) t(table_name) order by t.table_name`),
  sql(`select current_database() database_name,current_setting('server_version') server_version,now() audited_at`),
]);

const live = (liveMigrations as Array<{ migration: Record<string, unknown> }>).map((row) => row.migration);
const liveVersions = new Set(live.map((row) => String(row.version)));
const repoVersions = new Set(migrationFiles.map((row) => row.version));
const duplicateRepoVersions = [...repoVersions].filter((version) => migrationFiles.filter((row) => row.version === version).length > 1);
const reconciliation = {
  matched: migrationFiles.filter((row) => liveVersions.has(row.version)).map((row) => row.version),
  live_only: live.filter((row) => !repoVersions.has(String(row.version))),
  repo_only: migrationFiles.filter((row) => !liveVersions.has(row.version)),
  content_mismatch: migrationFiles.filter((row) => !liveVersions.has(row.version)).map((row) => ({ version: row.version, file: row.file, classification: "NOT_COMPARABLE_LIVE_HISTORY_ABSENT" })),
  ordering_mismatch: duplicateRepoVersions.map((version) => ({ version, files: migrationFiles.filter((row) => row.version === version).map((row) => row.file) })),
  status: "DATABASE_SCHEMA_DEPLOYMENT_BLOCKED_BY_MIGRATION_DRIFT",
  note: "Content comparison is only possible when live migration statements are retained; schema equivalence must be verified before history repair.",
};
const report = { generated_at: new Date().toISOString(), project_ref: projectRef, server, migration_columns: migrationColumns, repository_migrations: migrationFiles, live_migrations: live, reconciliation, tables, foreign_keys: foreignKeys, indexes, policies, preservation_counts: preservationCounts };
const outputDir = path.join(process.cwd(), "reports", "semantic-search", "database");
mkdirSync(outputDir, { recursive: true });
writeFileSync(path.join(outputDir, "migration_reconciliation.json"), `${JSON.stringify(report, null, 2)}\n`);
writeFileSync(path.join(outputDir, "production_counts_before.json"), `${JSON.stringify({ generated_at: report.generated_at, counts: preservationCounts }, null, 2)}\n`);
const tableRows = tables as Array<{ table_name:string; rls_enabled:boolean; estimated_rows:number; columns:Array<{column:string}>; primary_key:unknown }>;
const fkRows = foreignKeys as Array<{table_name:string}>;
const indexRows = indexes as Array<{table_name:string}>;
const inventory = tableRows.map((table) => {
  const columns = table.columns.map((column) => column.column);
  return {
    table: table.table_name, purpose: "Existing production semantic/search/domain table; see column contract", row_count: table.estimated_rows,
    primary_key: table.primary_key, foreign_keys: fkRows.filter((fk) => fk.table_name === table.table_name), rls: table.rls_enabled,
    indexes: indexRows.filter((index) => index.table_name === table.table_name),
    version_support: columns.some((name) => /version|analysis_run_id/.test(name)),
    evidence_support: columns.some((name) => /evidence|keyframe|transcript|ocr/.test(name)),
    provenance_support: columns.some((name) => /provenance|source_fingerprint|source_type/.test(name)),
    semantic_state_support: columns.includes("semantic_state"), human_override_support: columns.some((name) => /review|override|gold/.test(name)), columns,
  };
});
writeFileSync(path.join(outputDir, "schema_inventory.json"), `${JSON.stringify({ generated_at: report.generated_at, tables: inventory }, null, 2)}\n`);
console.log(JSON.stringify({ generated_at: report.generated_at, repository_migrations: migrationFiles.length, live_migrations: live.length, matched: reconciliation.matched.length, live_only: reconciliation.live_only.length, repo_only: reconciliation.repo_only.length, tables_found: (tables as unknown[]).length }, null, 2));
