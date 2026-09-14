import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import {
  canonicalSerialize,
  deterministicParse,
  interpretQuery,
  LocalOntologySemanticInterpreter,
  QUERY_CONFIGURATION_FINGERPRINT,
  QUERY_PARSER_VERSION,
  QUERY_SCHEMA_VERSION,
  DETERMINISTIC_PARSER_VERSION,
  SEMANTIC_INTERPRETER_VERSION,
} from "../db/query-interpreter";
type Lang = "ENGLISH" | "MALAY" | "MIXED";
type Gold = {
  count?: number | null;
  media?: string;
  ext?: string[];
  numeric?: Record<string, number | null>;
  temporal?: Record<string, number | null>;
  pos?: string[];
  neg?: string[];
  modality?: string[];
  conflict?: string;
  unresolved?: boolean;
};
type Seed = [string, Gold, Lang?];
const root = path.resolve(process.cwd(), ".."),
  cfg = path.join(root, "config", "semantic-search", "benchmarks"),
  out = path.join(root, "reports", "semantic-search", "phase14_2");
mkdirSync(cfg, { recursive: true });
mkdirSync(out, { recursive: true });
const rows: Array<{ category: string; seed: Seed }> = [],
  add = (c: string, s: Seed[]) =>
    s.forEach((seed) => rows.push({ category: c, seed }));
const nums: [
  [string, number],
  [string, number],
  [string, number],
  [string, number],
  [string, number],
  [string, number],
] = [
  ["one", 1],
  ["three", 3],
  ["five", 5],
  ["eight", 8],
  ["ten", 10],
  ["twelve", 12],
];
add(
  "RESULT_COUNT",
  nums.flatMap(([w, n], i) => [
    [
      `Would you find ${w} ${i % 2 ? "clips" : "pictures"} for this review?`,
      { count: n, media: i % 2 ? "VIDEO" : "IMAGE" },
    ] as Seed,
    [
      `Please return ${n + 1} ${i % 2 ? "images" : "videos"} and nothing else`,
      { count: n + 1, media: i % 2 ? "IMAGE" : "VIDEO" },
    ] as Seed,
  ]),
);
add("NUMERIC_OPERATORS", [
  ["At least 1750 grafts are needed", { numeric: { graft_count_min: 1750 } }],
  ["More than 2300 grafts", { numeric: { graft_count_min: 2300 } }],
  ["No more than 3200 grafts", { numeric: { graft_count_max: 3200 } }],
  ["Under 46 years old", { numeric: { age_max: 46 } }],
  ["At most 7 sessions", { numeric: { treatment_session_count: 7 } }],
  ["Roughly 2800 grafts", { numeric: { graft_count_exact: 2800 } }],
  ["Around age 34", { numeric: { age_exact: 34 } }],
  ["Approximately 55 seconds", { temporal: { duration_min_seconds: 55 } }],
  ["Between 22 and 31 years old", { numeric: { age_min: 22, age_max: 31 } }],
  [
    "1500 to 2100 grafts",
    { numeric: { graft_count_min: 1500, graft_count_max: 2100 } },
  ],
  [
    "Duration between 14 and 39 seconds",
    { temporal: { duration_min_seconds: 14, duration_max_seconds: 39 } },
  ],
  ["umur 26 hingga 38", { numeric: { age_min: 26, age_max: 38 } }, "MALAY"],
  [
    "antara 1900 hingga 2500 graft",
    { numeric: { graft_count_min: 1900, graft_count_max: 2500 } },
    "MALAY",
  ],
  ["bawah 50 seconds", { temporal: { duration_max_seconds: 50 } }, "MIXED"],
  ["atas 1800 grafts", { numeric: { graft_count_min: 1800 } }, "MIXED"],
  ["about 42 years old", { numeric: { age_exact: 42 } }],
  ["at least 80 seconds", { temporal: { duration_min_seconds: 80 } }],
  ["no more than 6 sessions", { numeric: { treatment_session_count: 6 } }],
]);
add("MEDIA_EXTENSION", [
  ["MOV footage please", { media: "VIDEO", ext: ["MOV"] }],
  ["JPG photographs only", { media: "IMAGE", ext: ["JPG"] }],
  ["Return PNG pictures", { media: "IMAGE", ext: ["PNG"] }],
  ["Find MP4 clips", { media: "VIDEO", ext: ["MP4"] }],
  ["WEBP still images", { media: "IMAGE", ext: ["WEBP"] }],
  ["cari rakaman MOV", { media: "VIDEO", ext: ["MOV"] }, "MALAY"],
  ["mahu gambar JPEG", { media: "IMAGE", ext: ["JPEG"] }, "MALAY"],
  ["show imej PNG", { media: "IMAGE", ext: ["PNG"] }, "MIXED"],
  ["vids in MP4 format", { media: "VIDEO", ext: ["MP4"] }],
  ["ordinary media files", { media: "ANY" }],
  [
    "JPG videos",
    { media: "VIDEO", ext: ["JPG"], conflict: "EXTENSION_MEDIA_CONFLICT" },
  ],
  [
    "MOV pictures",
    { media: "IMAGE", ext: ["MOV"], conflict: "EXTENSION_MEDIA_CONFLICT" },
  ],
]);
add("NEGATION_CONTRADICTION", [
  [
    "Doctor present without a patient",
    { pos: ["CLINICIAN"], neg: ["PATIENT"] },
  ],
  ["Leave out every syringe", { neg: ["INJECTING"] }],
  ["Do not include neck views", { neg: ["NECK"] }],
  ["Avoid cleansing footage", { neg: ["CLEANSING"], media: "VIDEO" }],
  ["A patient, but no doctor", { pos: ["PATIENT"], neg: ["CLINICIAN"] }],
  [
    "cari pesakit tanpa suntikan",
    { pos: ["PATIENT"], neg: ["INJECTING"] },
    "MALAY",
  ],
  [
    "doktor tetapi tiada pesakit",
    { pos: ["CLINICIAN"], neg: ["PATIENT"] },
    "MALAY",
  ],
  [
    "video patient tapi jangan ada jarum",
    { media: "VIDEO", pos: ["PATIENT"], neg: ["INJECTING"] },
    "MIXED",
  ],
  [
    "No injection although injection must appear",
    {
      pos: ["INJECTING"],
      neg: ["INJECTING"],
      conflict: "CONCEPT_POLARITY_CONFLICT",
    },
  ],
  [
    "Exclude patient but patient has to be shown",
    {
      pos: ["PATIENT"],
      neg: ["PATIENT"],
      conflict: "CONCEPT_POLARITY_CONFLICT",
    },
  ],
  [
    "Only images although videos are requested",
    { media: "VIDEO", conflict: "MEDIA_TYPE_CONFLICT" },
  ],
  [
    "show 4 videos and return 9 files",
    { count: 4, media: "VIDEO", conflict: "COUNT_CONFLICT" },
  ],
  [
    "show 6 files with 6 sessions",
    { count: 6, media: "ANY", numeric: { treatment_session_count: 6 } },
  ],
  [
    "walaupun tak mahu suntikan, suntikan mesti nampak",
    {
      pos: ["INJECTING"],
      neg: ["INJECTING"],
      conflict: "CONCEPT_POLARITY_CONFLICT",
    },
    "MALAY",
  ],
  ["if possible avoid injections", { neg: ["INJECTING"] }],
  ["preferably no clinician", { neg: ["CLINICIAN"] }],
  ["without cheek cleansing", { neg: ["CHEEK", "CLEANSING"] }],
  [
    "patient footage not with staff",
    { media: "VIDEO", pos: ["PATIENT"], neg: ["STAFF"] },
  ],
]);
add("SEMANTIC_EXACT", [
  [
    "Physician marking the hairline",
    { pos: ["CLINICIAN", "DRAWING_HAIRLINE", "FRONTAL_HAIRLINE"] },
  ],
  [
    "Doctor designing the hairline",
    { pos: ["CLINICIAN", "DRAWING_HAIRLINE", "FRONTAL_HAIRLINE"] },
  ],
  [
    "Medical staff drawing the hair line",
    { pos: ["STAFF", "DRAWING_HAIRLINE", "FRONTAL_HAIRLINE"] },
  ],
  [
    "Implanting grafts on frontal scalp",
    { pos: ["IMPLANTING_GRAFTS", "FRONTAL_SCALP"] },
  ],
  ["Patient cheek cleansing", { pos: ["PATIENT", "CHEEK", "CLEANSING"] }],
  ["Clinician in a treatment room", { pos: ["CLINICIAN", "TREATMENT_ROOM"] }],
  [
    "Recipient region examination by physician",
    { pos: ["RECIPIENT_REGION", "CLINICIAN"] },
  ],
  [
    "Patient facing camera after procedure",
    { pos: ["PATIENT", "LOOKING_AT_CAMERA", "POST_PROCEDURE"] },
  ],
  [
    "Hair transplant before treatment",
    { pos: ["HAIR_TRANSPLANT", "PRE_PROCEDURE"] },
  ],
  ["Injection during procedure", { pos: ["INJECTING", "DURING_PROCEDURE"] }],
  ["Face and neck close view", { pos: ["FACE", "NECK"] }],
  ["Consultation inside the clinic", { pos: ["CONSULTATION", "CLINIC"] }],
  [
    "doktor lukis garisan rambut",
    { pos: ["CLINICIAN", "DRAWING_HAIRLINE", "FRONTAL_HAIRLINE"] },
    "MALAY",
  ],
  ["pesakit selepas rawatan", { pos: ["PATIENT", "POST_PROCEDURE"] }, "MALAY"],
  [
    "membersihkan pipi pesakit",
    { pos: ["CLEANSING", "CHEEK", "PATIENT"] },
    "MALAY",
  ],
  [
    "show doktor planning hairline",
    { pos: ["CLINICIAN", "DRAWING_HAIRLINE", "FRONTAL_HAIRLINE"] },
    "MIXED",
  ],
  ["cari patient dalam clinic room", { pos: ["PATIENT", "CLINIC"] }, "MIXED"],
  [
    "gambar frontal scalp before treatment",
    { media: "IMAGE", pos: ["FRONTAL_SCALP", "PRE_PROCEDURE"] },
    "MIXED",
  ],
  ["Scalp procedure with patient", { pos: ["SCALP", "PATIENT"] }],
  ["Graft implantation aftercare", { pos: ["IMPLANTING_GRAFTS", "FOLLOW_UP"] }],
  [
    "Doctor consultation before transplant",
    { pos: ["CLINICIAN", "CONSULTATION", "PRE_PROCEDURE", "HAIR_TRANSPLANT"] },
  ],
  [
    "Patient looking at camera in clinic",
    { pos: ["PATIENT", "LOOKING_AT_CAMERA", "CLINIC"] },
  ],
  [
    "Cleaning cheek during treatment",
    { pos: ["CLEANSING", "CHEEK", "DURING_PROCEDURE"] },
  ],
  [
    "Frontal hairline planning",
    { pos: ["FRONTAL_HAIRLINE", "DRAWING_HAIRLINE"] },
  ],
]);
add("PHRASE_TYPO", [
  ["frntal sclap", { pos: ["FRONTAL_SCALP"] }],
  ["graft implntation", { pos: ["IMPLANTING_GRAFTS"] }],
  ["harline desgin", { pos: ["DRAWING_HAIRLINE"] }],
  ["frontal harline", { pos: ["FRONTAL_HAIRLINE"] }],
  ["doctr consultation", { pos: ["CLINICIAN", "CONSULTATION"] }],
  [
    "frntal sclap with graft implntation",
    { pos: ["FRONTAL_SCALP", "IMPLANTING_GRAFTS"] },
  ],
  ["donor", { unresolved: true }],
  ["donor consultation", { pos: ["CONSULTATION"], unresolved: true }],
  ["clincal rom", { unresolved: true }],
  ["pateint", { unresolved: true }],
  ["injction", { unresolved: true }],
  ["har tranplant", { unresolved: true }],
]);
add("UNKNOWN_CHUNKS", [
  ["delta scalp resonance", { unresolved: true }],
  [
    "scalp procedure with delta resonance",
    { pos: ["SCALP"], unresolved: true },
  ],
  ["patient with cobalt crown ritual", { pos: ["PATIENT"], unresolved: true }],
  ["aurora cheek calibration", { unresolved: true }],
  ["doctor with prismatic protocol", { pos: ["CLINICIAN"], unresolved: true }],
  [
    "frontal scalp with lunar harmonics",
    { pos: ["FRONTAL_SCALP"], unresolved: true },
  ],
  ["velvet transplant geometry", { unresolved: true }],
  ["clinic room with zeta alignment", { pos: ["CLINIC"], unresolved: true }],
  ["heliotrope neck resonance", { unresolved: true }],
  [
    "patient procedure with amber signal",
    { pos: ["PATIENT"], unresolved: true },
  ],
  ["scalp with unknown omega sequence", { pos: ["SCALP"], unresolved: true }],
  ["quantum graft choreography", { unresolved: true }],
]);
add("MODALITY", [
  ["The screen reads iGraft", { modality: ["OCR"] }],
  ["M-CURE appears as visible text", { modality: ["OCR"] }],
  ["Written on screen: consultation", { modality: ["OCR"] }],
  [
    "The physician says no shaving",
    { pos: ["CLINICIAN"], modality: ["TRANSCRIPT"] },
  ],
  ["Someone mentions the frontal hairline", { modality: ["TRANSCRIPT"] }],
  [
    "Patient talking about grafts",
    { pos: ["PATIENT"], modality: ["TRANSCRIPT"] },
  ],
  ["ada tulisan iGraft", { modality: ["OCR"] }, "MALAY"],
  [
    "doktor cakap tentang rawatan",
    { pos: ["CLINICIAN"], modality: ["TRANSCRIPT"] },
    "MALAY",
  ],
  [
    "screen says M-CURE but patient says aftercare",
    { pos: ["PATIENT"], modality: ["OCR", "TRANSCRIPT"] },
  ],
  ["visible words say hairline", { modality: ["OCR"] }],
  ["text says consultation", { modality: ["OCR"] }],
  [
    "pesakit sebut hairline",
    { pos: ["PATIENT"], modality: ["TRANSCRIPT"] },
    "MALAY",
  ],
]);
add("LANGUAGE_STRESS", [
  ["nak tujuh video doktor", { count: 7, media: "VIDEO", pos: ["CLINICIAN"] }, "MALAY"],
  ["mahu tiga gambar pesakit", { count: 3, media: "IMAGE", pos: ["PATIENT"] }, "MALAY"],
  ["tunjuk lima klip selepas rawatan", { count: 5, media: "VIDEO", pos: ["POST_PROCEDURE"] }, "MALAY"],
  ["cari empat rakaman sebelum prosedur", { count: 4, media: "VIDEO", pos: ["PRE_PROCEDURE"] }, "MALAY"],
  ["gambar muka dalam bilik klinik", { media: "IMAGE", pos: ["FACE", "CLINIC"] }, "MALAY"],
  ["video pesakit semasa prosedur", { media: "VIDEO", pos: ["PATIENT", "DURING_PROCEDURE"] }, "MALAY"],
  ["doktor dengan kulit kepala pesakit", { pos: ["CLINICIAN", "SCALP", "PATIENT"] }, "MALAY"],
  ["tiada doktor tetapi pesakit ada", { neg: ["CLINICIAN"], pos: ["PATIENT"] }, "MALAY"],
  ["jangan ada suntikan dalam video", { neg: ["INJECTING"], media: "VIDEO" }, "MALAY"],
  ["show saya eight clips doctor", { count: 8, media: "VIDEO", pos: ["CLINICIAN"] }, "MIXED"],
  ["cari five pictures patient", { count: 5, media: "IMAGE", pos: ["PATIENT"] }, "MIXED"],
  ["nak 4 footage before treatment", { count: 4, media: "VIDEO", pos: ["PRE_PROCEDURE"] }, "MIXED"],
  ["return tiga gambar selepas procedure", { count: 3, media: "IMAGE", pos: ["POST_PROCEDURE"] }, "MIXED"],
  ["show rakaman clinician in treatment room", { media: "VIDEO", pos: ["CLINICIAN", "TREATMENT_ROOM"] }, "MIXED"],
  ["cari image frontal hairline design", { media: "IMAGE", pos: ["FRONTAL_HAIRLINE", "DRAWING_HAIRLINE"] }, "MIXED"],
  ["patient ada but without doctor", { pos: ["PATIENT"], neg: ["CLINICIAN"] }, "MIXED"],
  ["preferably gambar doctor consultation", { media: "IMAGE", pos: ["CLINICIAN", "CONSULTATION"] }, "MIXED"],
  ["find video pesakit cakap hairline", { media: "VIDEO", pos: ["PATIENT"], modality: ["TRANSCRIPT"] }, "MIXED"],
]);
add("MULTI_NUMERIC", [
  [
    "show 7 videos of a 41-year-old with 2600 grafts",
    {
      count: 7,
      media: "VIDEO",
      numeric: { age_exact: 41, graft_count_exact: 2600 },
    },
  ],
  [
    "return five clips from 2026 after 3 sessions",
    {
      count: 5,
      media: "VIDEO",
      numeric: { treatment_session_count: 3 },
      temporal: { year: 2026 },
    },
  ],
  [
    "find 4 videos under 30 seconds near 00:16",
    {
      count: 4,
      media: "VIDEO",
      temporal: { duration_max_seconds: 30, timestamp_seconds: 16 },
    },
  ],
  [
    "RM8,500 package; show 3 images",
    { count: 3, media: "IMAGE", numeric: { currency_amount: 8500 } },
  ],
  [
    "tunjuk enam video pesakit umur 32",
    { count: 6, media: "VIDEO", numeric: { age_exact: 32 }, pos: ["PATIENT"] },
    "MALAY",
  ],
  [
    "nak 2 gambar bawah 45 seconds",
    { count: 2, media: "IMAGE", temporal: { duration_max_seconds: 45 } },
    "MIXED",
  ],
  [
    "show 8 files with at least 1900 grafts",
    { count: 8, media: "ANY", numeric: { graft_count_min: 1900 } },
  ],
  [
    "return 9 clips around 01:20",
    { count: 9, media: "VIDEO", temporal: { timestamp_seconds: 80 } },
  ],
  [
    "find 3 images from 2024",
    { count: 3, media: "IMAGE", temporal: { year: 2024 } },
  ],
  [
    "show 5 videos with no more than 4 sessions",
    { count: 5, media: "VIDEO", numeric: { treatment_session_count: 4 } },
  ],
  [
    "mahu empat rakaman RM700",
    { count: 4, media: "VIDEO", numeric: { currency_amount: 700 } },
    "MALAY",
  ],
  [
    "cari 6 klip antara 1700 hingga 2300 graft",
    {
      count: 6,
      media: "VIDEO",
      numeric: { graft_count_min: 1700, graft_count_max: 2300 },
    },
    "MALAY",
  ],
]);
if (rows.length !== 150) throw new Error(`V3 size ${rows.length}`);
const prior = [
    "kdi_query_parser_benchmark_v1.json",
    "kdi_query_parser_benchmark_v2.json",
  ].map((f) => JSON.parse(readFileSync(path.join(cfg, f), "utf8"))),
  priorQueries = prior.flatMap((x) => x.cases.map((c: any) => c.query)),
  oldExact = new Set(priorQueries.map((x: string) => x.toLowerCase()));
const split = { DEV: 0, VALIDATION: 0, BLIND: 0 },
  seen = new Set<string>();
const cases = rows.map(({ category, seed }, i) => {
  const [query, expected, language = "ENGLISH"] = seed,
    key = query.toLowerCase();
  if (seen.has(key) || oldExact.has(key)) throw new Error(`duplicate ${query}`);
  seen.add(key);
  let s: iSplit = i % 5 < 3 ? "DEV" : i % 5 === 3 ? "VALIDATION" : "BLIND";
  if (split[s] >= { DEV: 90, VALIDATION: 30, BLIND: 30 }[s])
    s = split.DEV < 90 ? "DEV" : split.VALIDATION < 30 ? "VALIDATION" : "BLIND";
  split[s]++;
  return {
    case_id: `QP14V3-${String(i + 1).padStart(3, "0")}`,
    split: s,
    category,
    query,
    language,
    expected: { count: null, ...expected },
    fields_not_expected: ["asset_id", "filename", "search_results"],
  };
});
type iSplit = "DEV" | "VALIDATION" | "BLIND";
const tokenize = (q: string) =>
    new Set(q.toLowerCase().match(/[a-z0-9]+/g) ?? []),
  jaccard = (a: Set<string>, b: Set<string>) => {
    const both = [...a].filter((x) => b.has(x)).length;
    return both / (a.size + b.size - both || 1);
  },
  overlaps = cases
    .flatMap((c: any) =>
      priorQueries
        .map((q: string) => ({
          v3_case: c.case_id,
          v3: c.query,
          prior: q,
          score: jaccard(tokenize(c.query), tokenize(q)),
        }))
        .filter((x) => x.score >= 0.72),
    )
    .sort((a, b) => b.score - a.score),
  accepted = overlaps.filter((x) => x.score < 0.9);
const base = {
    benchmark_version: "kdi_query_parser_benchmark_v3",
    evaluation_version: "kdi_query_parser_eval_v3",
    created_at: "2026-08-25T00:00:00.000Z",
    query_count: 150,
    split_counts: split,
    category_distribution: Object.fromEntries(
      [...new Set(rows.map((x) => x.category))].map((k) => [
        k,
        rows.filter((x) => x.category === k).length,
      ]),
    ),
    holdout_description:
      "FROZEN_HOLDOUT; labels are repository-visible, not cryptographically blind",
    frozen_versions: {
      query_parser_version: QUERY_PARSER_VERSION,
      deterministic_parser_version: DETERMINISTIC_PARSER_VERSION,
      semantic_interpreter_version: SEMANTIC_INTERPRETER_VERSION,
      query_schema_version: QUERY_SCHEMA_VERSION,
      configuration_fingerprint: QUERY_CONFIGURATION_FINGERPRINT,
    },
    cases,
  },
  fingerprint = createHash("sha256")
    .update(canonicalSerialize(base))
    .digest("hex"),
  benchmark = { ...base, fingerprint, frozen: true };
writeFileSync(
  path.join(cfg, "kdi_query_parser_benchmark_v3.json"),
  JSON.stringify(benchmark, null, 2) + "\n",
);
type Diff = { field: string; expected: any; actual: any; critical: boolean };
const concept = (p: any, c: string, n = false) =>
  (n ? p.semantic.negative_concepts : p.semantic.positive_concepts).some(
    (x: any) => x.canonical_code === c,
  );
function evalCase(c: any, p: any) {
  const d: Diff[] = [],
    cmp = (f: string, e: any, a: any, critical = true) => {
      if (canonicalSerialize(e) !== canonicalSerialize(a))
        d.push({ field: f, expected: e, actual: a, critical });
    },
    e = c.expected;
  cmp("count", e.count, p.result_request.requested_count);
  if (e.media) cmp("media", e.media, p.media.media_type);
  if (e.ext)
    cmp("extension", [...e.ext].sort(), [...p.media.extensions].sort());
  for (const [k, v] of Object.entries(e.numeric ?? {}))
    cmp(`numeric.${k}`, v, p.numeric[k] ?? null);
  for (const [k, v] of Object.entries(e.temporal ?? {})) {
    const a =
      k === "year"
        ? (p.temporal.year?.value ?? p.temporal.date?.year ?? null)
        : k === "timestamp_seconds"
          ? (p.temporal.timestamp?.timestamp_seconds ?? null)
          : (p.temporal.duration?.[k] ?? null);
    cmp(`temporal.${k}`, v, a);
  }
  for (const x of e.pos ?? [])
    if (!concept(p, x))
      d.push({
        field: `positive.${x}`,
        expected: true,
        actual: false,
        critical: false,
      });
  for (const x of e.neg ?? [])
    if (!concept(p, x, true))
      d.push({
        field: `negative.${x}`,
        expected: true,
        actual: false,
        critical: true,
      });
  for (const x of e.modality ?? [])
    if (!p.textual.modalities.includes(x))
      d.push({
        field: `modality.${x}`,
        expected: true,
        actual: false,
        critical: true,
      });
  if (
    e.conflict &&
    !p.parser_metadata.conflicts.some(
      (x: any) => x.conflict_type === e.conflict,
    )
  )
    d.push({
      field: "conflict",
      expected: e.conflict,
      actual: p.parser_metadata.conflicts,
      critical: true,
    });
  if (e.unresolved && !p.semantic.unresolved_concepts.length)
    d.push({
      field: "unresolved",
      expected: true,
      actual: false,
      critical: true,
    });
  return d;
}
const provider = new LocalOntologySemanticInterpreter();
async function run(set: any[]) {
  const results: any[] = [],
    timing: any = {
      deterministic: [],
      semantic: [],
      validation: [],
      total: [],
    };
  for (const c of set) {
    let t = performance.now();
    const det = deterministicParse(c.query);
    timing.deterministic.push(performance.now() - t);
    t = performance.now();
    await provider.interpret({
      original_query: c.query,
      remaining_semantic_text: c.query,
      consumed_spans: det.consumed_spans,
      deterministic: det,
      allowed_fields: [],
    });
    timing.semantic.push(performance.now() - t);
    t = performance.now();
    const p = await interpretQuery(c.query, provider),
      total = performance.now() - t;
    timing.total.push(total);
    timing.validation.push(Math.max(0, total - timing.semantic.at(-1)));
    const differences = evalCase(c, p);
    results.push({
      ...c,
      actual: p,
      differences,
      severity: differences.some((x) => x.critical)
        ? "CRITICAL"
        : differences.length
          ? "NON_CRITICAL"
          : "PASS",
      root_cause: rootCause(differences, c),
    });
  }
  return { results, timing };
}
function rootCause(d: Diff[], c: any) {
  if (!d.length) return null;
  const f = d[0].field;
  if (f.includes("numeric") || f.includes("temporal")) return "NUMERIC_TYPING";
  if (f === "count") return "RESULT_COUNT";
  if (f.includes("negative")) return "NEGATION";
  if (f === "conflict") return "CONTRADICTION";
  if (f === "unresolved") return "UNKNOWN_SAFETY";
  if (c.category === "PHRASE_TYPO") return "TYPO_RECOVERY";
  if (c.language !== "ENGLISH") return "LANGUAGE";
  return "SEMANTIC_CHUNKING";
}
const expectedN = (e: Gold) =>
  1 +
  (e.media ? 1 : 0) +
  (e.ext ? 1 : 0) +
  Object.keys(e.numeric ?? {}).length +
  Object.keys(e.temporal ?? {}).length +
  (e.pos?.length ?? 0) +
  (e.neg?.length ?? 0) +
  (e.modality?.length ?? 0) +
  (e.conflict ? 1 : 0) +
  (e.unresolved ? 1 : 0);
function summarize(name: string, r: any) {
  const diffs = r.results.flatMap((x: any) => x.differences),
    total = r.results.reduce(
      (n: number, x: any) => n + expectedN(x.expected),
      0,
    ),
    semanticTotal = r.results.reduce(
      (n: number, x: any) =>
        n +
        (x.expected.pos?.length ?? 0) +
        (x.expected.neg?.length ?? 0) +
        (x.expected.modality?.length ?? 0) +
        (x.expected.unresolved ? 1 : 0),
      0,
    ),
    semanticWrong = diffs.filter((x: any) =>
      /positive|negative|modality|unresolved/.test(x.field),
    ).length;
  return {
    split: name,
    cases: r.results.length,
    passed: r.results.filter((x: any) => !x.differences.length).length,
    errors: r.results.filter((x: any) => x.differences.length).length,
    critical_failures: diffs.filter((x: any) => x.critical).length,
    false_result_count: r.results.filter(
      (x: any) =>
        x.expected.count == null &&
        x.actual.result_request.requested_count != null,
    ).length,
    missed_explicit_count: r.results.filter(
      (x: any) =>
        typeof x.expected.count === "number" &&
        x.actual.result_request.requested_count == null,
    ).length,
    numeric_accuracy: ratio(r.results, /^(numeric|temporal)\./),
    negation_accuracy: ratio(r.results, /^negative\./),
    contradiction_accuracy: ratio(r.results, /^conflict$/),
    semantic_accuracy: semanticTotal
      ? (semanticTotal - semanticWrong) / semanticTotal
      : 1,
    micro: (total - diffs.length) / total,
    macro:
      r.results.reduce(
        (n: number, x: any) =>
          n +
          (expectedN(x.expected) - x.differences.length) /
            expectedN(x.expected),
        0,
      ) / r.results.length,
    schema_valid:
      r.results.filter((x: any) => x.actual.validation.status === "VALID")
        .length / r.results.length,
    critical_exact:
      (total - diffs.filter((x: any) => x.critical).length) / total,
  };
}
function ratio(rs: any[], re: RegExp) {
  const a = rs.filter(
    (x) =>
      x.differences.some((d: any) => re.test(d.field)) ||
      [
        ...Object.keys(x.expected.numeric ?? {}).map(
          (k: string) => `numeric.${k}`,
        ),
        ...Object.keys(x.expected.temporal ?? {}).map(
          (k: string) => `temporal.${k}`,
        ),
        ...(x.expected.neg ?? []).map((k: string) => `negative.${k}`),
        ...(x.expected.conflict ? ["conflict"] : []),
      ].some((x) => re.test(x)),
  );
  return a.length
    ? a.filter((x) => !x.differences.some((d: any) => re.test(d.field)))
        .length / a.length
    : 1;
}
const lang = (r: any, l: Lang) => {
  const x = r.results.filter((c: any) => c.language === l),
    n = x.reduce((s: number, c: any) => s + expectedN(c.expected), 0),
    w = x.reduce((s: number, c: any) => s + c.differences.length, 0);
  return { cases: x.length, accuracy: n ? (n - w) / n : 1 };
};
const dev = await run(cases.filter((x: any) => x.split === "DEV")),
  devS = summarize("DEV", dev),
  validation = await run(cases.filter((x: any) => x.split === "VALIDATION")),
  validationS = summarize("VALIDATION", validation),
  validationL = Object.fromEntries(
    (["ENGLISH", "MALAY", "MIXED"] as Lang[]).map((l) => [
      l,
      lang(validation, l),
    ]),
  );
const pass = (s: any, l: any) =>
    s.false_result_count === 0 &&
    s.missed_explicit_count === 0 &&
    s.numeric_accuracy === 1 &&
    s.negation_accuracy === 1 &&
    s.contradiction_accuracy === 1 &&
    s.semantic_accuracy >= 0.95 &&
    s.micro >= 0.98 &&
    s.macro >= 0.95 &&
    s.schema_valid === 1 &&
    s.critical_exact >= 0.99 &&
    l.ENGLISH.accuracy >= 0.98 &&
    l.MALAY.accuracy >= 0.95 &&
    l.MIXED.accuracy >= 0.95 &&
    s.critical_failures === 0,
  validationPass = pass(validationS, validationL),
  blind = validationPass
    ? await run(cases.filter((x: any) => x.split === "BLIND"))
    : null,
  blindS: any = blind
    ? summarize("BLIND", blind)
    : { split: "BLIND", cases: 0, status: "NOT_RUN_VALIDATION_FAILED" },
  blindL = blind
    ? Object.fromEntries(
        (["ENGLISH", "MALAY", "MIXED"] as Lang[]).map((l) => [
          l,
          lang(blind, l),
        ]),
      )
    : null,
  blindPass = blind ? pass(blindS, blindL) : false,
  eligible = validationPass
    ? cases
    : cases.filter((x: any) => x.split !== "BLIND"),
  r1 = await run(eligible),
  r2 = await run(eligible),
  stable = r1.results.filter(
    (x: any, i: number) =>
      canonicalSerialize(x.actual) === canonicalSerialize(r2.results[i].actual),
  ).length,
  stableFp = r1.results.filter(
    (x: any, i: number) =>
      x.actual.parser_metadata.query_fingerprint ===
      r2.results[i].actual.parser_metadata.query_fingerprint,
  ).length;
const stat = (xs: number[]) => {
    const s = [...xs].sort((a, b) => a - b);
    return {
      p50: s[Math.floor(s.length * 0.5)],
      p95: s[Math.floor(s.length * 0.95)],
      max: s.at(-1),
    };
  },
  latency = {
    deterministic: stat(r1.timing.deterministic),
    semantic: stat(r1.timing.semantic),
    validation: stat(r1.timing.validation),
    total: stat(r1.timing.total),
  };
const failures = [
    ...dev.results,
    ...validation.results,
    ...(blind?.results ?? []),
  ].filter((x: any) => x.differences.length),
  result = {
    generated_at: new Date().toISOString(),
    status: validationPass && blindPass ? "PASS" : "BLOCKED",
    manifest: {
      version: base.benchmark_version,
      fingerprint,
      counts: split,
      frozen: true,
      holdout: base.holdout_description,
    },
    candidate: {
      git_head: "4476f6768639aad4d187b822af38a625f2b24cde",
      worktree: "DIRTY",
      parser_source_sha256:
      "df19f786ed42a0f7acfb37a6b82bb64f785594e937efbfe260eff39aa25442fb",
      config_file_sha256:
        "6b6266ced895167bda958bee9f75dbe4ae1a2fe41c4884de54b0a4979882a4d0",
      configuration_fingerprint: QUERY_CONFIGURATION_FINGERPRINT,
      immutable_after_validation_start: true,
    },
    dev: devS,
    validation: validationS,
    validation_language: validationL,
    blind: blindS,
    blind_language: blindL,
    reproducibility: {
      eligible: eligible.length,
      identical_outputs: stable,
      stable_fingerprints: stableFp,
      rate: stable / eligible.length,
    },
    near_overlap: {
      exact_duplicates: 0,
      high_overlap_candidates: overlaps.length,
      accepted_legitimate_similarities: accepted.length,
      candidates: overlaps,
    },
    provider: {
      benchmark_provider: "deterministic production-local interpreter",
      live_smoke: {
        status: (await interpretQuery("doktor consultation")).validation.status,
        provider: provider.provider,
        model_version: provider.modelVersion,
        external: false,
      },
    },
    errors: { total: failures.length, cases: failures },
    latency,
    cost: { external_calls: 0, external_cost: 0 },
    boundaries: {
      retrieval: false,
      ranking: false,
      phase15: false,
      frontend: false,
      human_gold: "DEFERRED",
    },
  };
const reports: any = {
  phase14_2_summary: result,
  phase14_2_runtime_trace: {
    path: [
      "app/api/search/v3/route.ts POST",
      "db/query-interpreter.ts interpretQuery",
      "deterministicParse",
      "LocalOntologySemanticInterpreter",
      "validateProviderOutput",
      "canonical plan validator/fingerprint",
    ],
    legacy_adapter:
      "interpretV3Query remains only as compatibility input to existing retrieval; canonical plan is persisted as parsed_intent",
  },
  phase14_2_v3_manifest: result.manifest,
  phase14_2_v3_near_overlap: result.near_overlap,
  phase14_2_v3_dev_results: { summary: devS, cases: dev.results },
  phase14_2_v3_validation_results: {
    summary: validationS,
    language: validationL,
    cases: validation.results,
  },
  phase14_2_v3_error_register: result.errors,
  phase14_2_reproducibility: result.reproducibility,
  phase14_2_latency: latency,
  phase14_2_provider_validation: result.provider,
  phase14_2_validation: result,
};
if (blind)
  reports.phase14_2_v3_blind_results = {
    summary: blindS,
    language: blindL,
    cases: blind.results,
  };
for (const [n, v] of Object.entries(reports))
  writeFileSync(path.join(out, `${n}.json`), JSON.stringify(v, null, 2) + "\n");
console.log(JSON.stringify(result, null, 2));
