/**
 * Regenerates config/semantic-search/kdi_search_vocabulary_v1.json from the LIVE ontology.
 *
 * The query-side vocabulary used to be a hand-maintained list, so every ontology code had to be
 * registered twice and the two drifted (e.g. treatments had LASER/INJECTABLES/HIFU but the search
 * vocabulary did not, so those queries resolved to nothing). This makes the ontology the single
 * source: ontology-backed categories are (re)built from the DB; curated query-only categories and
 * any extra curated synonyms are preserved (strict superset — nothing existing is dropped).
 *
 * Run:  node --env-file=.env.local --import tsx scripts/generate_search_vocabulary.ts
 */
import {createClient} from "@supabase/supabase-js";
import {readFileSync, writeFileSync} from "node:fs";

const db = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!, {auth:{persistSession:false}});
const REGISTRY = "../config/semantic-search/kdi_search_vocabulary_v1.json";

// registry category -> ontology table (active rows) + the column holding the human-readable name.
const ONTOLOGY: {category:string; table:string; nameCol:string}[] = [
  {category:"TREATMENT",   table:"treatments",                       nameCol:"name"},
  {category:"ANATOMY",     table:"anatomy_terms",                    nameCol:"name"},
  {category:"ACTION",      table:"actions",                          nameCol:"name"},
  {category:"ENVIRONMENT", table:"locations",                        nameCol:"name"},
  {category:"RELATIONSHIP",table:"relationship_types",               nameCol:"name"},
  {category:"OBSERVATION", table:"clinical_observation_definitions", nameCol:"label"},
];

const humanize = (code:string) => code.replace(/_/g," ").toLowerCase().replace(/\s+/g," ").trim();
const norm = (s:string) => s.toLowerCase().replace(/\s+/g," ").trim();

/** union-merge surface forms case-insensitively, preserving existing order first. */
function mergeSurfaces(existing:string[]=[], incoming:string[]=[]): string[] {
  const out:string[] = [], seen = new Set<string>();
  for (const s of [...existing, ...incoming]) {
    const v = (s??"").trim(); if (!v) continue;
    const k = norm(v); if (seen.has(k)) continue;
    seen.add(k); out.push(v);
  }
  return out;
}

async function main(){
  const reg = JSON.parse(readFileSync(REGISTRY, "utf8"));
  const cats: Record<string,Record<string,string[]>> = reg.categories;
  const summary: Record<string,{added_codes:number; total_codes:number}> = {};

  // treatment_aliases -> extra surface forms per treatment code
  const [{data:tRows}, {data:aliasRows}] = await Promise.all([
    db.from("treatments").select("id,code").eq("is_active",true),
    db.from("treatment_aliases").select("treatment_id,alias").eq("is_active",true),
  ]);
  const codeById = new Map((tRows??[]).map((r:any)=>[r.id, r.code]));
  const aliasesByCode = new Map<string,string[]>();
  for (const a of aliasRows??[]) { const c = codeById.get(a.treatment_id); if(c){ (aliasesByCode.get(c)??aliasesByCode.set(c,[]).get(c)!).push(a.alias); } }

  const skipped: string[] = [];
  for (const {category, table, nameCol} of ONTOLOGY) {
    const {data, error} = await db.from(table).select(`code,${nameCol}`).eq("is_active",true);
    if (error) {
      // Some ontology tables aren't exposed to the PostgREST role (e.g. no grant). Preserve the
      // curated category verbatim and record the gap rather than failing or silently dropping it.
      skipped.push(`${category}<-${table} (${error.message})`);
      const keys = Object.keys(cats[category] ?? {});
      summary[category] = {added_codes: 0, total_codes: keys.length};
      continue;
    }
    const before = new Set(Object.keys(cats[category] ?? {}));
    const target = (cats[category] ??= {});
    for (const row of data??[]) {
      const code = String(row.code);
      const surfaces = mergeSurfaces(
        target[code],
        [ humanize(code), norm(String(row[nameCol] ?? "")), ...(category==="TREATMENT" ? (aliasesByCode.get(code)??[]) : []) ].filter(Boolean),
      );
      target[code] = surfaces;
    }
    const after = Object.keys(target);
    summary[category] = {added_codes: after.filter(c=>!before.has(c)).length, total_codes: after.length};
  }

  reg.generated_from = "live_ontology";
  reg.generated_note = "Ontology-backed categories rebuilt from DB (treatments/anatomy_terms/actions/locations/relationship_types/clinical_observation_definitions + treatment_aliases); curated categories and synonyms preserved. Regenerate via scripts/generate_search_vocabulary.ts.";
  writeFileSync(REGISTRY, JSON.stringify(reg, null, 2) + "\n");
  const totalCodes = new Set(Object.values(cats).flatMap(c=>Object.keys(c))).size;
  console.log("regenerated", REGISTRY);
  if (skipped.length) console.log("SKIPPED (not reachable, curated entries preserved):", skipped.join("; "));
  console.log("per-category:", JSON.stringify(summary, null, 0));
  console.log("total codes now:", totalCodes,
    "| LASER:", !!cats.TREATMENT?.LASER, "| INJECTABLES:", !!cats.TREATMENT?.INJECTABLES,
    "| HIFU:", !!cats.TREATMENT?.HIFU, "| ENERGY_BASED:", !!cats.TREATMENT?.ENERGY_BASED);
  console.log("LASER surfaces:", JSON.stringify(cats.TREATMENT?.LASER));
  console.log("INJECTABLES surfaces:", JSON.stringify(cats.TREATMENT?.INJECTABLES));
}
main().catch(e=>{console.error("FATAL",e);process.exit(1);});
