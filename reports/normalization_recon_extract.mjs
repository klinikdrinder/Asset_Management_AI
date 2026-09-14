// READ-ONLY normalization reconnaissance extractor.
// Runs SELECT-only SQL via the Supabase Management API and writes CSVs.
// No writes, no DDL, no migrations. Safe to re-run.
import { readFileSync, writeFileSync } from 'node:fs';

const ref = 'wcqqjpndlwsvatjuqnol';
const env = readFileSync(new URL('../dashboard/.env.local', import.meta.url), 'utf8');
const token = env.match(/SUPABASE_DASHBOARD_ACCESS_TOKEN=(\S+)/)[1];

async function q(sql) {
  const r = await fetch(`https://api.supabase.com/v1/projects/${ref}/database/query`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: sql }),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

const csv = (v) => {
  if (v === null || v === undefined) return '';
  const s = String(v);
  return '"' + s.replace(/"/g, '""') + '"';
};
const toCsv = (rows, cols) =>
  [cols.join(','), ...rows.map((row) => cols.map((c) => csv(row[c])).join(','))].join('\r\n') + '\r\n';

// Shared CTEs: placeholder rows in the six ontology-backed layers + normalized ontology terms.
const BASE = `
WITH vt AS (
  SELECT layer_id, value_text, count(*) n, replace(lower(value_text),'''','') vc
  FROM semantic_assertions
  WHERE active AND canonical_concept_code = layer_id
    AND layer_id IN ('ANATOMY','ACTIONS_EVENTS','CLINICAL_VISUAL_OBSERVATIONS','TREATMENT_PROCEDURE','RELATIONSHIPS','ENVIRONMENT')
    AND value_text IS NOT NULL
  GROUP BY 1,2
),
onto AS (
  SELECT 'ANATOMY' layer_id, code, replace(lower(name),'''','') nc FROM anatomy_terms
  UNION ALL SELECT 'ACTIONS_EVENTS', code, replace(lower(name),'''','') FROM actions
  UNION ALL SELECT 'CLINICAL_VISUAL_OBSERVATIONS', code,
    replace(lower(regexp_replace(label,' visible| visual| visibility| definition','','gi')),'''','') FROM clinical_observation_definitions
  UNION ALL SELECT 'TREATMENT_PROCEDURE', code, replace(lower(name),'''','') FROM treatments
  UNION ALL SELECT 'TREATMENT_PROCEDURE', t.code, replace(lower(a.alias),'''','')
    FROM treatment_aliases a JOIN treatments t ON t.id=a.treatment_id
  UNION ALL SELECT 'RELATIONSHIPS', code, replace(lower(name),'''','') FROM relationship_types
  UNION ALL SELECT 'ENVIRONMENT', code, replace(lower(name),'''','') FROM locations
),
matched AS (
  SELECT DISTINCT vt.layer_id, vt.value_text FROM vt JOIN onto o ON o.layer_id=vt.layer_id
   AND (vt.vc=o.nc OR vt.vc ~* ('\\y'||o.nc||'\\y') OR word_similarity(o.nc,vt.vc)>=0.6)
)`;

const candSql = `${BASE}
SELECT vt.layer_id, vt.value_text, vt.n AS occurrences, o.code AS proposed_code,
  CASE WHEN vt.vc=o.nc THEN 'exact'
       WHEN vt.vc ~* ('\\y'||o.nc||'\\y') THEN 'containment'
       ELSE 'trigram' END AS match_method,
  round(word_similarity(o.nc, vt.vc)::numeric,3) AS similarity_score
FROM vt JOIN onto o ON o.layer_id=vt.layer_id
 AND (vt.vc=o.nc OR vt.vc ~* ('\\y'||o.nc||'\\y') OR word_similarity(o.nc,vt.vc)>=0.6)
ORDER BY vt.layer_id, vt.n DESC, vt.value_text, similarity_score DESC;`;

// Unmapped = every distinct placeholder value with no candidate, across ALL 18 layers.
// layer_has_ontology flags whether the layer even has a normalization target.
const unmappedSql = `${BASE}
, allvt AS (
  SELECT layer_id, value_text, count(*) n
  FROM semantic_assertions
  WHERE active AND canonical_concept_code = layer_id AND value_text IS NOT NULL
  GROUP BY 1,2
)
SELECT a.layer_id, a.value_text, a.n AS occurrences,
  (a.layer_id IN ('ANATOMY','ACTIONS_EVENTS','CLINICAL_VISUAL_OBSERVATIONS','TREATMENT_PROCEDURE','RELATIONSHIPS','ENVIRONMENT')) AS layer_has_ontology
FROM allvt a
LEFT JOIN matched m ON m.layer_id=a.layer_id AND m.value_text=a.value_text
WHERE m.value_text IS NULL
ORDER BY a.n DESC, a.layer_id, a.value_text;`;

const cand = await q(candSql);
writeFileSync(new URL('./mapping_candidates.csv', import.meta.url),
  toCsv(cand, ['layer_id', 'value_text', 'occurrences', 'proposed_code', 'match_method', 'similarity_score']));
console.log('mapping_candidates.csv rows:', cand.length);

const unm = await q(unmappedSql);
writeFileSync(new URL('./unmapped.csv', import.meta.url),
  toCsv(unm, ['layer_id', 'value_text', 'occurrences', 'layer_has_ontology']));
console.log('unmapped.csv rows:', unm.length);
