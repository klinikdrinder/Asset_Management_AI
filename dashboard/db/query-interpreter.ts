import { createHash } from "node:crypto";
import baseConfig from "../../config/semantic-search/kdi_query_parser_v1_4.json";
import v2Config from "../../config/semantic-search/kdi_query_parser_v2.json";
import v3Config from "../../config/semantic-search/kdi_query_parser_v3.json";
import {SEARCH_VOCABULARY,SEARCH_VOCABULARY_VERSION} from "./search-vocabulary-registry";

const config = { ...baseConfig, ...v2Config, ...v3Config };

export const QUERY_PARSER_VERSION = config.query_parser_version,
  DETERMINISTIC_PARSER_VERSION = config.deterministic_parser_version,
  SEMANTIC_INTERPRETER_VERSION = config.semantic_interpreter_version,
  QUERY_SCHEMA_VERSION = config.query_schema_version,
  QUERY_CONFIGURATION_VERSION = config.configuration_version;
type ParseStatus = "MATCHED" | "AMBIGUOUS" | "NOT_FOUND" | "INVALID";
type NormalizationStatus = ParseStatus | "PARTIAL" | "UNRESOLVED";
type Language = "ENGLISH" | "MALAY" | "MIXED" | "UNKNOWN";
type Modality = "VISUAL" | "TRANSCRIPT" | "OCR" | "ANY";
type SurfaceStrength =
  | "EXPLICIT_ONLY"
  | "EXPLICIT_MUST"
  | "EXPLICIT_EXACT"
  | "EXPLICIT_EXCLUDE"
  | "NEUTRAL"
  | "PREFERENCE";
type Span = {
  raw_text: string;
  status: ParseStatus;
  rule_id: string;
  start_char: number;
  end_char: number;
};
export type Extraction<T> = Span & { value: T };
export type SemanticConcept = {
  concept_type: string;
  raw_text: string;
  canonical_code: string | null;
  normalization_status: NormalizationStatus;
  source: "DETERMINISTIC_PARSER" | "SEMANTIC_INTERPRETER";
  confidence: number | null;
  start_char: number | null;
  end_char: number | null;
  modality: Modality;
  surface_strength: SurfaceStrength;
  clause_id?: number;
  polarity?: "POSITIVE" | "NEGATIVE";
  marker?: string | null;
};
export type NumericOperator =
  | "EXACT"
  | "AT_LEAST"
  | "GREATER_THAN"
  | "AT_MOST"
  | "LESS_THAN"
  | "BETWEEN"
  | "APPROXIMATE";
type NumericType =
  | "RESULT_COUNT"
  | "AGE_EXACT"
  | "AGE_MIN"
  | "AGE_MAX"
  | "AGE_DECADE"
  | "GRAFT_COUNT_EXACT"
  | "GRAFT_COUNT_MIN"
  | "GRAFT_COUNT_MAX"
  | "TREATMENT_SESSION_COUNT"
  | "SESSION_ORDINAL"
  | "YEAR"
  | "DURATION"
  | "DURATION_MIN"
  | "DURATION_MAX"
  | "TIMESTAMP"
  | "CURRENCY_AMOUNT"
  | "UNCLASSIFIED";
export type NumericOccurrence = {
  value: number;
  raw_text: string;
  numeric_type: NumericType;
  status: ParseStatus;
  rule_id: string;
  start_char: number;
  end_char: number;
  unit?: string;
  approximate?: boolean;
  operator?: NumericOperator;
  min_value?: number | null;
  max_value?: number | null;
  inclusive_min?: boolean | null;
  inclusive_max?: boolean | null;
};
export type SemanticProviderOutput = {
  positive_concepts?: unknown;
  negative_concepts?: unknown;
  unresolved_concepts?: unknown;
  modalities?: unknown;
  transcript_phrases?: unknown;
  ocr_phrases?: unknown;
  preferences?: unknown;
  [key: string]: unknown;
};
export type SemanticContext = {
  original_query: string;
  remaining_semantic_text: string;
  consumed_spans: Array<{
    start_char: number;
    end_char: number;
    rule_id: string;
  }>;
  deterministic: DeterministicOutput;
  allowed_fields: string[];
};
export interface SemanticQueryInterpreter {
  readonly provider: string;
  readonly model: string;
  readonly modelVersion: string;
  readonly local: boolean;
  interpret(context: SemanticContext): Promise<SemanticProviderOutput>;
}
export type DeterministicOutput = {
  intent: "FIND_MEDIA" | "FIND_SIMILAR_MEDIA" | "REFINE_SEARCH" | "UNKNOWN";
  count: Extraction<number> | null;
  count_occurrences: Extraction<number>[];
  media_type: Extraction<"VIDEO" | "IMAGE" | "ANY"> | null;
  media_mentions: Extraction<"VIDEO" | "IMAGE" | "ANY">[];
  extensions: Extraction<string>[];
  numeric_occurrences: NumericOccurrence[];
  temporal: Record<string, any>;
  surface_markers: Array<{
    raw_text: string;
    surface_strength: SurfaceStrength;
    start_char: number;
    end_char: number;
  }>;
  sort: {
    sort:
      | "MOST_RELEVANT_FIRST"
      | "NEWEST_FIRST"
      | "OLDEST_FIRST"
      | "LARGEST_FIRST"
      | "SMALLEST_FIRST";
    source: "USER_EXPLICIT" | "SYSTEM_DEFAULT";
    raw_text: string | null;
  };
  detected_language: Language;
  conflicts: Array<Record<string, unknown>>;
  consumed_spans: Array<{
    start_char: number;
    end_char: number;
    rule_id: string;
  }>;
};
export type CanonicalQueryPlan = Readonly<{
  [key: string]: any;
  intent: string;
  original_query: string;
  result_request: any;
  media: any;
  semantic: {
    positive_concepts: SemanticConcept[];
    negative_concepts: SemanticConcept[];
    unresolved_concepts: SemanticConcept[];
  };
  temporal: any;
  numeric: any;
  textual: any;
  constraints: any;
  preferences: any[];
  ranking: any;
  conversation: any;
  retrieval_text: any;
  parser_metadata: {
    warnings: string[];
    conflicts: Array<Record<string, unknown>>;
    query_fingerprint: string;
    semantic_interpretation_status: string;
    [key: string]: unknown;
  };
  validation: any;
}>;

function stable(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  return `{${Object.entries(value as Record<string, unknown>)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${JSON.stringify(k)}:${stable(v)}`)
    .join(",")}}`;
}
export function canonicalSerialize(value: unknown) {
  return stable(value);
}
const sha = (s: string) => createHash("sha256").update(s).digest("hex");
export const QUERY_CONFIGURATION_FINGERPRINT = sha(stable(config));
const clean = (s: string) =>
  s
    .normalize("NFKC")
    .replace(/[‐‑‒–—]/g, "-")
    .replace(/\s+/g, " ")
    .trim();
const EN: Record<string, number> = {
  one: 1,
  two: 2,
  three: 3,
  four: 4,
  five: 5,
  six: 6,
  seven: 7,
  eight: 8,
  nine: 9,
  ten: 10,
  eleven: 11,
  twelve: 12,
  thirteen: 13,
  fourteen: 14,
  fifteen: 15,
  sixteen: 16,
  seventeen: 17,
  eighteen: 18,
  nineteen: 19,
  twenty: 20,
};
const MS: Record<string, number> = {
  satu: 1,
  dua: 2,
  tiga: 3,
  empat: 4,
  lima: 5,
  enam: 6,
  tujuh: 7,
  lapan: 8,
  sembilan: 9,
  sepuluh: 10,
};
const ORD: Record<string, number> = {
  first: 1,
  second: 2,
  third: 3,
  fourth: 4,
  fifth: 5,
  sixth: 6,
  pertama: 1,
  kedua: 2,
  ketiga: 3,
  keempat: 4,
  kelima: 5,
};
const numberValue = (s: string) =>
  /^\d[\d,]*(?:\.\d+)?$/.test(s)
    ? Number(s.replace(/,/g, ""))
    : (EN[s.toLowerCase()] ?? MS[s.toLowerCase()] ?? null);
const numberWord = `(?:\\d[\\d,]*(?:\\.\\d+)?|${[...Object.keys(EN), ...Object.keys(MS)].join("|")})`;
function extraction<T>(
  value: T,
  m: RegExpExecArray,
  rule_id: string,
  group = 1,
): Extraction<T> {
  const raw = m[group],
    start = (m.index ?? 0) + m[0].indexOf(raw);
  return {
    value,
    raw_text: raw,
    status: "MATCHED",
    rule_id,
    start_char: start,
    end_char: start + raw.length,
  };
}
function language(q: string): Language {
  const ms =
      /\b(cari|tunjuk|nak|mahu|tolong|doktor|pesakit|gambar|imej|klip|rakaman|tanpa|jangan|tidak|elakkan|sebelum|selepas|semasa|rawatan|sesi|suntikan|tulisan)\b/i.test(
        q,
      ),
    en =
      /\b(show|find|give|return|video|image|patient|doctor|with|before|after|clip|footage|only|must|prefer)\b/i.test(
        q,
      );
  return ms && en ? "MIXED" : ms ? "MALAY" : en ? "ENGLISH" : "UNKNOWN";
}
function mediaMentions(q: string) {
  const out: Extraction<"VIDEO" | "IMAGE" | "ANY">[] = [],
    r =
      /\b(videos?|vids?|clips?|footage|klip|rakaman|images?|photos?|photographs?|photographic\s+stills?|stills?|pictures?|gambar|imej|items?|files?|assets?|media|materials?|content|fail)\b/gi;
  let m: RegExpExecArray | null;
  while ((m = r.exec(q))) {
    const x = m[1].toLowerCase(),
      value: "VIDEO" | "IMAGE" | "ANY" =
        /^(video|vid|clip|footage|klip|rakaman)/.test(x)
          ? "VIDEO"
          : /^(image|photo|photograph|photographic|still|picture|gambar|imej)/.test(x)
            ? "IMAGE"
            : "ANY";
    out.push(extraction(value, m, "MEDIA_VOCABULARY"));
  }
  return out;
}
function countExtractions(q: string): Extraction<number>[] {
  const verbs =
      "(?:show(?: me)?|find(?: me)?|return|retrieve|get(?: me)?|list|display|pull(?: up)?|bring(?: up)?|fetch|provide|send|select|surface|give(?: me| us)?|top|best|need|want|tunjuk|cari|nak|mahu)",
    media =
      "(?:results?|matches|items?|files?|assets?|media|videos?|vids?|clips?|footage|images?|photos?|photographs?|pictures?|gambar|imej|klip|rakaman|fail)";
  const found: Extraction<number>[] = [];
  for (const source of [
    new RegExp(
      `\\b${verbs}\\s+(?:the\\s+)?(?:best\\s+)?(${numberWord})\\s+${media}\\b`,
      "gi",
    ),
    new RegExp(
      `\\b${verbs}\\s+(?:the\\s+)?(?:best\\s+)?(${numberWord})(?:\\s+(?!years?\\b|year-old\\b|grafts?\\b|seconds?\\b|minutes?\\b|percent\\b|RM\\b)[A-Za-z-]+){1,5}\\s+${media}\\b`,
      "gi",
    ),
    new RegExp(`\\b(?:top|best)\\s+(${numberWord})(?:\\s+${media})?\\b`, "gi"),
    new RegExp(
      `\\b(?:i\\s+)?(?:need|want)\\s+(${numberWord})\\s+${media}\\b`,
      "gi",
    ),
    new RegExp(`\\bexactly\\s+(${numberWord})\\s+(?:${media})\\b`, "gi"),
  ]) {
    let m: RegExpExecArray | null;
    while ((m = source.exec(q))) {
      const n = numberValue(m[1]);
      if (n != null) {
        const item = extraction(n, m, "RESULT_COUNT_APPROVED_GRAMMAR");
        if (!found.some((x) => x.start_char === item.start_char)) found.push(item);
      }
    }
  }
  const singularBest=/\b(?:show(?: me)?|give(?: me)?|return|find(?: me)?|get(?: me)?)\s+(?:the\s+)?best\s+(result|match|item|file|asset|video|clip|image|photo)\b/gi;
  let best:RegExpExecArray|null;
  while((best=singularBest.exec(q))){const item=extraction(1,best,"RESULT_COUNT_BEST_SINGULAR");if(!found.some(x=>x.start_char===item.start_char))found.push(item)}
  return found.sort((a,b)=>a.start_char-b.start_char);
}
function countExtraction(q: string) { return countExtractions(q)[0] ?? null; }
function addNum(
  out: NumericOccurrence[],
  used: Array<[number, number]>,
  q: string,
  raw: string,
  start: number,
  type: NumericType,
  rule: string,
  value: number,
  unit?: string,
  approximate = false,
  operator: NumericOperator = approximate ? "APPROXIMATE" : "EXACT",
) {
  const end = start + raw.length;
  if (used.some(([a, b]) => start < b && end > a)) return;
  used.push([start, end]);
  out.push({
    value,
    raw_text: q.slice(start, end),
    numeric_type: type,
    status: "MATCHED",
    rule_id: rule,
    start_char: start,
    end_char: end,
    unit,
    approximate,
    operator,
    min_value: type.endsWith("_MIN") ? value : null,
    max_value: type.endsWith("_MAX") ? value : null,
    inclusive_min: type.endsWith("_MIN") ? operator !== "GREATER_THAN" : null,
    inclusive_max: type.endsWith("_MAX") ? operator !== "LESS_THAN" : null,
  });
}
function classifyNumbers(q: string, counts: Extraction<number>[]) {
  const out: NumericOccurrence[] = [],
    used: Array<[number, number]> = [];
  for (const count of counts)
    addNum(
      out,
      used,
      q,
      count.raw_text,
      count.start_char,
      "RESULT_COUNT",
      count.rule_id,
      count.value,
    );
  let m: RegExpExecArray | null;
  const ranges: Array<[RegExp, NumericType, NumericType, string, string]> = [
    [
      new RegExp(
        `\\b(?:between\\s+)?(${numberWord})\\s*(?:to|and|hingga|-)\\s*(${numberWord})\\s*(?:years? old|year old|umur)\\b`,
        "gi",
      ),
      "AGE_MIN",
      "AGE_MAX",
      "AGE_RANGE",
      "years",
    ],
    [
      new RegExp(
        `\\b(?:age|aged|umur)\\s+(${numberWord})\\s*(?:to|hingga|-)\\s*(${numberWord})\\b`,
        "gi",
      ),
      "AGE_MIN",
      "AGE_MAX",
      "AGE_RANGE",
      "years",
    ],
    [
      new RegExp(
        `\\b(?:between\\s+|antara\\s+)?(${numberWord})\\s*(?:to|and|hingga|-)\\s*(${numberWord})\\s*grafts?\\b`,
        "gi",
      ),
      "GRAFT_COUNT_MIN",
      "GRAFT_COUNT_MAX",
      "GRAFT_RANGE",
      "grafts",
    ],
    [
      new RegExp(
        `\\b(?:between\\s+|antara\\s+)?(${numberWord})\\s*(?:to|and|hingga|-)\\s*(${numberWord})\\s*(seconds?|minutes?)\\b`,
        "gi",
      ),
      "DURATION_MIN",
      "DURATION_MAX",
      "DURATION_RANGE",
      "seconds",
    ],
  ];
  for (const [re, a, b, rule, unit] of ranges)
    while ((m = re.exec(q))) {
      const v1 = numberValue(m[1]),
        v2 = numberValue(m[2]),
        factor = m[3]?.toLowerCase().startsWith("minute") ? 60 : 1;
      if (v1 != null && v2 != null) {
        const s1 = m.index + m[0].indexOf(m[1]),
          s2 = m.index + m[0].lastIndexOf(m[2]);
        addNum(out, used, q, m[1], s1, a, rule, v1 * factor, unit);
        addNum(out, used, q, m[2], s2, b, rule, v2 * factor, unit);
        for (const occurrence of out.slice(-2)) {
          occurrence.operator = "BETWEEN";
          occurrence.min_value = v1 * factor;
          occurrence.max_value = v2 * factor;
          occurrence.inclusive_min = true;
          occurrence.inclusive_max = true;
        }
      }
    }
  const comparisons = new RegExp(
    `\\b(at least|no less than|more than|over|above|at most|no more than|under|below|less than|about|around|roughly|approximately|lebih kurang|bawah|atas)\\s+(${numberWord})\\s*(grafts?|years? old|sessions?|seconds?|minutes?)\\b`,
    "gi",
  );
  while ((m = comparisons.exec(q))) {
    const marker = m[1].toLowerCase(), raw = m[2], unitText = m[3].toLowerCase(), base = numberValue(raw);
    if (base == null) continue;
    const factor = unitText.startsWith("minute") ? 60 : 1, value = base * factor;
    const operator: NumericOperator = /^(at least|no less than)$/.test(marker)
      ? "AT_LEAST"
      : /^(more than|over|above|atas)$/.test(marker)
        ? "GREATER_THAN"
        : /^(at most|no more than)$/.test(marker)
          ? "AT_MOST"
          : /^(under|below|less than|bawah)$/.test(marker)
            ? "LESS_THAN"
            : "APPROXIMATE";
    const isMin = operator === "AT_LEAST" || operator === "GREATER_THAN";
    const isMax = operator === "AT_MOST" || operator === "LESS_THAN";
    const type: NumericType = unitText.startsWith("graft")
      ? isMin ? "GRAFT_COUNT_MIN" : isMax ? "GRAFT_COUNT_MAX" : "GRAFT_COUNT_EXACT"
      : unitText.startsWith("year")
        ? isMin ? "AGE_MIN" : isMax ? "AGE_MAX" : "AGE_EXACT"
        : unitText.startsWith("session")
          ? "TREATMENT_SESSION_COUNT"
          : isMin ? "DURATION_MIN" : isMax ? "DURATION_MAX" : "DURATION";
    addNum(out, used, q, raw, m.index + m[0].indexOf(raw), type, "TYPED_COMPARISON", value, unitText, operator === "APPROXIMATE", operator);
  }
  const inclusiveBounds = new RegExp(
    "\\b(?:a\\s+)?(?:graft\\s+quantity\\s+)?(no greater than|no less than)\\s+(" + numberWord + ")\\s*(grafts?)?\\b",
    "gi",
  );
  while ((m = inclusiveBounds.exec(q))) {
    const value = numberValue(m[2])!, isMin = m[1].toLowerCase() === "no less than";
    addNum(out, used, q, m[2], m.index + m[0].indexOf(m[2]), isMin ? "GRAFT_COUNT_MIN" : "GRAFT_COUNT_MAX", "GRAFT_INCLUSIVE_BOUND", value, "grafts", false, isMin ? "AT_LEAST" : "AT_MOST");
  }
  const patterns: Array<
    [
      RegExp,
      NumericType,
      string,
      (m: RegExpExecArray) => number,
      string?,
      boolean?,
    ]
  > = [
    [
      new RegExp(`\\b(${numberWord})[- ]year[- ]old\\b`, "gi"),
      "AGE_EXACT",
      "AGE_EXACT",
      (x) => numberValue(x[1])!,
      "years",
    ],
    [
      new RegExp(
        `\\b(?:(?:around|about)\\s+age|aged?|umur)\\s+(${numberWord})(?:\\s+years? old)?\\b`,
        "gi",
      ),
      "AGE_EXACT",
      "AGE_APPROX",
      (x) => numberValue(x[1])!,
      "years",
      true,
    ],
    [
      /\b(?:in (?:his|her|their)\s+)?(\d{2})s\b/gi,
      "AGE_DECADE",
      "AGE_DECADE",
      (x) => Number(x[1]),
      "decade",
    ],
    [
      new RegExp(
        `\\b(?:around|about|roughly|approximately|lebih kurang)?\\s*(${numberWord})\\s+grafts?\\b`,
        "gi",
      ),
      "GRAFT_COUNT_EXACT",
      "GRAFT_EXACT",
      (x) => numberValue(x[1])!,
      "grafts",
      true,
    ],
    [
      new RegExp(`\\b(${numberWord})\\s+(?:treatment\\s+)?sessions?\\b`, "gi"),
      "TREATMENT_SESSION_COUNT",
      "SESSION_COUNT",
      (x) => numberValue(x[1])!,
      "sessions",
    ],
    [
      new RegExp(`\\b(${numberWord})\\s+sesi\\b`, "gi"),
      "TREATMENT_SESSION_COUNT",
      "SESSION_COUNT_MS",
      (x) => numberValue(x[1])!,
      "sessions",
    ],
    [
      new RegExp(`\\bsession\\s+(${numberWord})\\b`, "gi"),
      "TREATMENT_SESSION_COUNT",
      "SESSION_TRAILING",
      (x) => numberValue(x[1])!,
      "sessions",
    ],
    [
      /\b(?:from|since|after|before|in|during|dated|captured in|recorded in|taken in)\s+((?:19|20)\d{2})\b/gi,
      "YEAR",
      "YEAR_TEMPORAL_CONTEXT",
      (x) => Number(x[1]),
      "year",
    ],
    [
      /\bRM\s*([\d,]+(?:\.\d+)?)\b/gi,
      "CURRENCY_AMOUNT",
      "CURRENCY",
      (x) => Number(x[1].replace(/,/g, "")),
      "MYR",
    ],
  ];
  for (const [re, type, rule, value, unit, approx] of patterns)
    while ((m = re.exec(q))) {
      const v = value(m);
      if (v != null)
        addNum(
          out,
          used,
          q,
          m[1],
          m.index + m[0].indexOf(m[1]),
          type,
          rule,
          v,
          unit,
          approx,
        );
    }
  const ord = new RegExp(
    `\\b(?:the\\s+)?(first|second|third|fourth|fifth|pertama|kedua|ketiga|keempat|kelima|\\d+(?:st|nd|rd|th))\\s+(?:treatment\\s+)?session\\b|\\bsesi\\s+(pertama|kedua|ketiga|keempat|kelima)\\b`,
    "gi",
  );
  while ((m = ord.exec(q))) {
    const raw = m[1] ?? m[2],
      v = ORD[raw.toLowerCase()] ?? Number(raw.replace(/\D/g, ""));
    addNum(
      out,
      used,
      q,
      raw,
      m.index + m[0].indexOf(raw),
      "SESSION_ORDINAL",
      "SESSION_ORDINAL",
      v,
      "ordinal",
    );
  }
  const sixthOrdinal = /\b(?:the\s+)?sixth\s+(?:treatment\s+)?session\b/gi;
  while ((m = sixthOrdinal.exec(q)))
    addNum(out, used, q, "sixth", m.index + m[0].indexOf("sixth"), "SESSION_ORDINAL", "SESSION_ORDINAL", 6, "ordinal");
  const dur = new RegExp(
    `\\b(under|below|less than|shorter than|over|above|more than|longer than|at least|at most|bawah|atas)\\s+(${numberWord})\\s*(seconds?|minutes?)\\b`,
    "gi",
  );
  const namedDuration = new RegExp(
    "\\b(no longer than|maximum|minimum)\\s+(" + numberWord + ")\\s*(seconds?|minutes?)\\b",
    "gi",
  );
  while ((m = namedDuration.exec(q))) {
    const value = numberValue(m[2])! * (m[3].toLowerCase().startsWith("minute") ? 60 : 1);
    addNum(out, used, q, m[2], m.index + m[0].indexOf(m[2]),
      m[1].toLowerCase() === "minimum" ? "DURATION_MIN" : "DURATION_MAX",
      "DURATION_NAMED_BOUND", value, "seconds", false,
      m[1].toLowerCase() === "minimum" ? "AT_LEAST" : "AT_MOST");
  }
  while ((m = dur.exec(q))) {
    const v =
      numberValue(m[2])! * (m[3].toLowerCase().startsWith("minute") ? 60 : 1);
    addNum(
      out,
      used,
      q,
      m[2],
      m.index + m[0].indexOf(m[2]),
      "DURATION",
      "DURATION_BOUND",
      v,
      "seconds",
    );
  }
  const clock = /\b(\d{1,2}):(\d{2})\b/g;
  while ((m = clock.exec(q)))
    addNum(
      out,
      used,
      q,
      m[0],
      m.index,
      "TIMESTAMP",
      "TIMESTAMP_CLOCK",
      Number(m[1]) * 60 + Number(m[2]),
      "seconds",
      /around|near|sekitar/i.test(q.slice(Math.max(0, m.index - 28), m.index)),
    );
  const ts = new RegExp(
    `\\b(?:around|near|at|sekitar)(?:\\s+the)?\\s+(${numberWord})(?:-|\\s*)second(?:s| mark)?(?:\\s+into)?\\b`,
    "gi",
  );
  while ((m = ts.exec(q)))
    addNum(
      out,
      used,
      q,
      m[1],
      m.index + m[0].indexOf(m[1]),
      "TIMESTAMP",
      "TIMESTAMP_SECONDS",
      numberValue(m[1])!,
      "seconds",
      true,
    );
  const reverseTimestamp = new RegExp(
    "\\b(?:around|near|at)(?:\\s+the)?\\s+(?:second|timestamp)\\s+(" + numberWord + ")\\b",
    "gi",
  );
  while ((m = reverseTimestamp.exec(q)))
    addNum(out, used, q, m[1], m.index + m[0].indexOf(m[1]), "TIMESTAMP", "TIMESTAMP_REVERSE_SECONDS", numberValue(m[1])!, "seconds", /around|near/i.test(m[0]));
  const all = new RegExp(`\\b${numberWord}\\b`, "gi");
  while ((m = all.exec(q))) {
    const v = numberValue(m[0]);
    if (v != null)
      addNum(
        out,
        used,
        q,
        m[0],
        m.index,
        "UNCLASSIFIED",
        "NUMERIC_UNCLASSIFIED",
        v,
      );
  }
  return out.sort((a, b) => a.start_char - b.start_char);
}
export function deterministicParse(raw: string): DeterministicOutput {
  const q = clean(raw),
    countOccurrences = countExtractions(q),
    count = countOccurrences[0] ?? null,
    mentions = mediaMentions(q),
    specific = mentions.filter((x) => x.value !== "ANY"),
    conflicts: Array<Record<string, unknown>> = [];
  let media = specific.at(-1) ?? mentions.at(-1) ?? null;
  const distinct = [...new Set(specific.map((x) => x.value))];
  if (distinct.length > 1 && /\bonly\b/i.test(q))
    conflicts.push({
      conflict_type: "MEDIA_TYPE_CONFLICT",
      values: distinct,
      precedence: "UNRESOLVED_USER_CONFLICT",
    });
  if (new Set(countOccurrences.map((x) => x.value)).size > 1)
    conflicts.push({
      conflict_type: "COUNT_CONFLICT",
      occurrences: countOccurrences,
      precedence: "UNRESOLVED_USER_CONFLICT",
    });
  const extensions: Extraction<string>[] = [],
    ext = /\b\.?((?:mp4|mov|jpe?g|png|webp))\b/gi;
  let m: RegExpExecArray | null;
  while ((m = ext.exec(q)))
    extensions.push(extraction(m[1].toUpperCase(), m, "EXPLICIT_EXTENSION"));
  const extensionFamilies = new Set(
    extensions.map((x) => (["MP4", "MOV"].includes(x.value) ? "VIDEO" : "IMAGE")),
  );
  if ((!media || media.value === "ANY") && extensionFamilies.size === 1) {
    const source = extensions[0];
    media = {
      ...source,
      value: [...extensionFamilies][0] as "VIDEO" | "IMAGE",
      rule_id: "EXTENSION_MEDIA_INFERENCE",
    };
  }
  if (media && media.value !== "ANY" && extensionFamilies.size && !extensionFamilies.has(media.value))
    conflicts.push({
      conflict_type: "EXTENSION_MEDIA_CONFLICT",
      media_type: media!.value,
      extensions: extensions.map((x) => x.value),
    });
  const numeric = classifyNumbers(q, countOccurrences),
    temporal: Record<string, any> = {};
  const year = numeric.find((x) => x.numeric_type === "YEAR");
  if (year)
    temporal.year = {
      value: year.value,
      raw_text: year.raw_text,
      status: "MATCHED",
    };
  const monthNames: Record<string, number> = {
    january: 1,
    february: 2,
    march: 3,
    april: 4,
    may: 5,
    june: 6,
    july: 7,
    august: 8,
    september: 9,
    october: 10,
    november: 11,
    december: 12,
  };
  const mr =
    /\bbetween\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+and\s+(january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+((?:19|20)\d{2}))?\b/i.exec(
      q,
    );
  if (mr)
    temporal.month_range = {
      start_month: monthNames[mr[1].toLowerCase()],
      end_month: monthNames[mr[2].toLowerCase()],
      year: mr[3] ? Number(mr[3]) : null,
      normalization_status: mr[3] ? "MATCHED" : "PARTIAL",
      raw_text: mr[0],
    };
  const singleMonth = new RegExp(
    `\\b(${Object.keys(monthNames).join("|")})(?:\\s+((?:19|20)\\d{2}))?\\b`,
    "i",
  ).exec(q);
  if (singleMonth && !mr)
    temporal.date = {
      month: monthNames[singleMonth[1].toLowerCase()],
      year: singleMonth[2] ? Number(singleMonth[2]) : null,
      normalization_status: singleMonth[2] ? "MATCHED" : "PARTIAL",
      raw_text: singleMonth[0],
    };
  const dmin = numeric.find((x) => x.numeric_type === "DURATION_MIN"),
    dmax = numeric.find((x) => x.numeric_type === "DURATION_MAX"),
    dbound = numeric.find((x) => x.numeric_type === "DURATION");
  if (dmin || dmax || dbound) {
    const prefix = dbound
        ? q.slice(Math.max(0, dbound.start_char - 20), dbound.start_char)
        : "",
      isMax = /under|below|less|shorter|at most|bawah/i.test(prefix);
    temporal.duration = {
      duration_min_seconds: dmin?.value ?? (dbound && !isMax ? dbound.value : null),
      duration_max_seconds: dmax?.value ?? (dbound && isMax ? dbound.value : null),
      status: "MATCHED",
    };
  }
  const ts = numeric.find((x) => x.numeric_type === "TIMESTAMP");
  if (ts)
    temporal.timestamp = {
      timestamp_seconds: ts.value,
      raw_text: ts.raw_text,
      approximate: ts.approximate ?? false,
      status: "MATCHED",
    };
  const surface_markers: DeterministicOutput["surface_markers"] = [],
    marker =
      /\b(only|must|exactly|has to|without|exclude|excluding|except|avoid|do not include|don't include|not showing|not with|preferably|ideally|if possible|would prefer|prefer|tanpa|jangan|tak nak|tidak|bukan|elakkan|jangan ada)\b/gi;
  while ((m = marker.exec(q))) {
    const w = m[1].toLowerCase(),
      strength: SurfaceStrength = /prefer|ideally|if possible/.test(w)
        ? "PREFERENCE"
        : w === "only"
          ? "EXPLICIT_ONLY"
          : /must|has to/.test(w)
            ? "EXPLICIT_MUST"
            : w === "exactly"
              ? "EXPLICIT_EXACT"
              : "EXPLICIT_EXCLUDE";
    surface_markers.push({
      raw_text: m[0],
      surface_strength: strength,
      start_char: m.index,
      end_char: m.index + m[0].length,
    });
  }
  let sort: DeterministicOutput["sort"] = {
    sort: "MOST_RELEVANT_FIRST",
    source: "SYSTEM_DEFAULT",
    raw_text: null,
  };
  const sm =
    /\b(most relevant|best matches|best|newest|latest|recent|oldest|largest|smallest)\b/i.exec(
      q,
    );
  if (sm) {
    const x = sm[1].toLowerCase();
    sort = {
      sort: /newest|latest|recent/.test(x)
        ? "NEWEST_FIRST"
        : x === "oldest"
          ? "OLDEST_FIRST"
          : x === "largest"
            ? "LARGEST_FIRST"
            : x === "smallest"
              ? "SMALLEST_FIRST"
              : "MOST_RELEVANT_FIRST",
      source: "USER_EXPLICIT",
      raw_text: sm[0],
    };
  }
  const similar =
    /\b(similar|resembling|more like|related footage|same kind)\b/i.test(q);
  return {
    intent: similar ? "FIND_SIMILAR_MEDIA" : "FIND_MEDIA",
    count,
    count_occurrences: countOccurrences,
    media_type: media,
    media_mentions: mentions,
    extensions,
    numeric_occurrences: numeric,
    temporal,
    surface_markers,
    sort,
    detected_language: language(q),
    conflicts,
    consumed_spans: [
      ...(count ? [count] : []),
      ...(media ? [media] : []),
      ...extensions,
    ].map((x) => ({
      start_char: x.start_char,
      end_char: x.end_char,
      rule_id: x.rule_id,
    })),
  };
}
// Concept vocabulary comes from the one canonical registry rather than this parser's own config,
// so parser, expander and retrieval all resolve concepts from a single source. The registry is a
// strict superset of the aliases previously embedded here.
const aliases = SEARCH_VOCABULARY as Record<
  string,
  Record<string, string[]>
>;
const levenshtein = (a: string, b: string) => {
  const d = Array.from({ length: a.length + 1 }, () =>
    Array(b.length + 1).fill(0),
  );
  for (let i = 0; i <= a.length; i++) d[i][0] = i;
  for (let j = 0; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++)
      d[i][j] = Math.min(
        d[i - 1][j] + 1,
        d[i][j - 1] + 1,
        d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
  return d[a.length][b.length];
};
const damerau = (a: string, b: string) => {
  const base = levenshtein(a, b);
  if (a.length !== b.length) return base;
  for (let i = 0; i < a.length - 1; i++) {
    if (
      a[i] === b[i + 1] &&
      a[i + 1] === b[i] &&
      a.slice(0, i) === b.slice(0, i) &&
      a.slice(i + 2) === b.slice(i + 2)
    )
      return 1;
  }
  return base;
};
const tokens = (q: string) =>
  [...q.matchAll(/[\p{L}\p{N}]+/gu)].map((m) => ({
    text: m[0].toLowerCase(),
    start: m.index!,
    end: m.index! + m[0].length,
  }));
function exactPhraseMatches(q: string, alias: string) {
  const qt = tokens(q),
    at = tokens(alias).map((x) => x.text),
    out: Array<{ start: number; end: number; partial: boolean }> = [];
  for (let i = 0; i <= qt.length - at.length; i++) {
    if (at.every((word, j) => qt[i + j].text === word))
      out.push({
        start: qt[i].start,
        end: qt[i + at.length - 1].end,
        partial: false,
      });
  }
  return out;
}
type Clause = { id: number; start: number; end: number; text: string };
function clauses(q: string): Clause[] {
  const boundary = /(?:[:,.!?;]+|\b(?:but|although|however|yet|while|though|except that|and then|then|nevertheless|tetapi|tapi|walaupun|namun)\b)/gi,
    out: Clause[] = [];
  let start = 0,
    id = 0,
    m: RegExpExecArray | null;
  while ((m = boundary.exec(q))) {
    if (m.index > start)
      out.push({ id: id++, start, end: m.index, text: q.slice(start, m.index) });
    start = m.index + m[0].length;
  }
  if (start < q.length) out.push({ id, start, end: q.length, text: q.slice(start) });
  return out.filter((x) => x.text.trim());
}
function semanticChunks(clause: Clause) {
  const cue = /\b(with|without|showing|featuring|containing|performing|doing|during|before|after)\b/gi,
    points = [0];
  let m: RegExpExecArray | null;
  while ((m = cue.exec(clause.text))) points.push(m.index);
  points.push(clause.text.length);
  return points.slice(0, -1).map((p, i) => {
    const raw=clause.text.slice(p,points[i+1]), leading=raw.length-raw.trimStart().length, text=raw.trim();
    return {clause_id:clause.id,start:clause.start+p+leading,end:clause.start+p+leading+text.length,text};
  }).filter((x) => x.text);
}
function surfaceAt(q: string, clauseStart: number, clauseEnd: number, start: number, end: number): SurfaceStrength {
  const before = q.slice(clauseStart, start).toLowerCase(),
    after = q.slice(end, clauseEnd).toLowerCase(),
    separatedPhrasal = /\b(?:leave|filter|keep)\b[^,.!?;]{0,64}$/.test(before) && /^[^,.!?;]{0,64}\bout\b/.test(after);
  if (
    separatedPhrasal || /\b(no|not|without|exclude|excluding|except|avoid|omit|remove|leave\s+out|filter\s+out|keep\s+out|do not include|don't include|anything except|not showing|not depicting|not containing|not with|tanpa|jangan(?: ada)?|tak nak|tidak|bukan|elakkan)\s+(?:(?:every|all|any|any kind of|every instance of)\s+)?(?:\w+\s+){0,4}$/.test(
      before,
    ) ||
    /^\s+(?:out\b|(?:but|tapi)?\s*(?:not wanted|dikecualikan))/.test(after)
  )
    return "EXPLICIT_EXCLUDE";
  if (/\b(if possible|preferably|ideally|prefer|would prefer)\b/.test(before))
    return "PREFERENCE";
  if (/\bonly\b/.test(before)) return "EXPLICIT_ONLY";
  if (/\b(must|has to|mesti)\b/.test(before) || /^\s*(must|has to|mesti)\b/.test(after))
    return "EXPLICIT_MUST";
  return "NEUTRAL";
}
const grammarWords = new Set("the a an of with without showing featuring containing performing doing during before after on at in procedure treatment visible view close up footage video videos image images photo photos picture pictures clip clips media must has to be is are should appear please show find return give me do not include avoid exclude excluding if possible but although tapi tetapi walaupun namun gambar imej rakaman klip selepas sebelum semasa rawatan jangan tiada tanpa tak nak ada".split(" "));
function safeFuzzyCandidates(chunk: ReturnType<typeof semanticChunks>[number], type: string, code: string, terms: string[]) {
  const ct = tokens(chunk.text).filter((x) => !grammarWords.has(x.text)), candidates: Array<{start:number;end:number;partial:true;score:number}> = [];
  for (const term of terms) {
    const at = tokens(term).map((x) => x.text);
    if (at.length < 2 || at.length > ct.length) continue;
    for (let offset = 0; offset <= ct.length - at.length; offset++) {
      const window = ct.slice(offset, offset + at.length),
        distances = at.map((word, i) => damerau(window[i].text, word)),
        score = distances.reduce((a, b) => a + b, 0);
      if (distances.every((x) => x <= 1) && score <= 2)
        candidates.push({ start: chunk.start + window[0].start, end: chunk.start + window.at(-1)!.end, partial: true, score });
    }
  }
  candidates.sort((a,b)=>a.start-b.start||a.score-b.score||b.end-b.start-(a.end-a.start));
  const selected: typeof candidates = [];
  for (const candidate of candidates)
    if (!selected.some((x) => candidate.start < x.end && candidate.end > x.start)) selected.push(candidate);
  return selected;
}
export class LocalOntologySemanticInterpreter
  implements SemanticQueryInterpreter
{
  readonly provider = "kdi_local_ontology_interpreter";
  readonly model = "kdi_semantic_lexicon_en";
  readonly modelVersion = "v2";
  readonly local = true;
  async interpret(context: SemanticContext) {
    const q = context.original_query,
      positive: SemanticConcept[] = [],
      negative: SemanticConcept[] = [],
      preferences: any[] = [];
    const unresolved: SemanticConcept[] = [];
    for (const clause of clauses(q))
      for (const chunk of semanticChunks(clause)) {
        const content = tokens(chunk.text).filter((x) => !grammarWords.has(x.text));
        const exact: Array<{ type: string; code: string; start: number; end: number; partial: boolean }> = [];
        for (const [type, codes] of Object.entries(aliases))
          for (const [code, terms] of Object.entries(codes))
            for (const term of terms)
              for (const found of exactPhraseMatches(chunk.text, term)) {
                const start = chunk.start + found.start,
                  end = chunk.start + found.end,
                  aliasTokens = tokens(term).length,
                  firstContent = content[0]?.start === found.start;
                // A lone known token buried inside an otherwise unknown phrase is not
                // independently promoted. Roles at the grammatical head remain valid.
                const explicitExclusion = surfaceAt(q, clause.start, clause.end, start, end) === "EXPLICIT_EXCLUDE",
                  explicitSelection = /\b(?:show|include|retain|keep|require|required|must|has to)\s+(?:the\s+|a\s+|an\s+)?$/i.test(q.slice(clause.start, start)),
                  relationQualified = /\b(?:in|inside|within|at|into|on)\s+(?:the\s+|a\s+|an\s+)?$/i.test(q.slice(clause.start,start)),
                  ageQualifiedRole = type === "ROLE" && /\b(?:aged?|\d+[- ]year[- ]old|\d+s|sessions?)\b/i.test(chunk.text),
                  coordinatedSemantic =
                    (type === "ROLE" && /\b(consult|examin|clean|inject|implant|draw|design|plan|mark|treat|work)\w*\b/i.test(chunk.text)) ||
                    (type === "ACTION" && /\b(doctor|clinician|physician|patient|staff|subject|presenter)\b/i.test(chunk.text)) ||
                    (type === "ANATOMY" && /\b(cleanse|cleansing|cleaning|wipe|wiping|inject|injecting|implant|implanting|draw|drawing|design|designing|plan|planning|mark|marking)\b/i.test(chunk.text));
                if (aliasTokens === 1 && content.length >= 3 && !firstContent && !explicitSelection && !relationQualified && !ageQualifiedRole && !coordinatedSemantic && !explicitExclusion)
                  continue;
                exact.push({ type, code, start, end, partial: false });
              }
        const accepted = exact.sort((a, b) => a.start - b.start || b.end - b.start - (a.end - a.start));
        for(const family of config.action_families??[])for(const source of family.patterns){const match=new RegExp(source,"i").exec(chunk.text);if(match&&!accepted.some(x=>x.type==="ACTION"&&x.code===family.code&&x.start===chunk.start+match.index))accepted.push({type:"ACTION",code:family.code,start:chunk.start+match.index,end:chunk.start+match.index+match[0].length,partial:false})}
        if (!accepted.length) {
          const fuzzy: Array<{ type: string; code: string; start: number; end: number; partial: boolean; score: number }> = [];
          for (const [type, codes] of Object.entries(aliases))
            for (const [code, terms] of Object.entries(codes))
              for (const found of safeFuzzyCandidates(chunk, type, code, terms))
                fuzzy.push({ type, code, ...found });
          fuzzy.sort((a, b) => a.start - b.start || a.score - b.score || b.end - b.start - (a.end - a.start));
          for (const candidate of fuzzy) {
            const competitors = fuzzy.filter((x) => x.start === candidate.start && x.end === candidate.end && (x.type !== candidate.type || x.code !== candidate.code));
            if (competitors.some((x) => x.score <= candidate.score + 1)) continue;
            if (accepted.some((x) => candidate.start < x.end && candidate.end > x.start)) continue;
            accepted.push(candidate);
          }
          const recoveredHairline = accepted.find((x) => x.type === "ACTION" && x.code === "DRAWING_HAIRLINE");
          if (recoveredHairline && !accepted.some((x) => x.type === "ANATOMY" && x.code === "FRONTAL_HAIRLINE"))
            accepted.push({ ...recoveredHairline, type: "ANATOMY", code: "FRONTAL_HAIRLINE" });
        }
        // Single-token role recovery never runs by proximity alone. It requires
        // compatible exact context and cannot replace an existing role meaning.
        if (!accepted.some((x) => x.type === "ROLE") && content.length > 1) {
          const contextSupported = /\b(consultation|clinic|procedure|treatment|patient|pesakit|doing|hairline|scalp)\b/i.test(chunk.text);
          if (contextSupported)
            for (const token of content)
              for (const term of aliases.ROLE.CLINICIAN)
                if (tokens(term).length === 1 && damerau(token.text, term.toLowerCase()) === 1)
                  accepted.push({ type: "ROLE", code: "CLINICIAN", start: chunk.start + token.start, end: chunk.start + token.end, partial: true });
        }
        for (const found of accepted) {
          const surface = surfaceAt(q, clause.start, clause.end, found.start, found.end),
            polarity = surface === "EXPLICIT_EXCLUDE" ? "NEGATIVE" : "POSITIVE",
            c: SemanticConcept = {
              concept_type: found.type,
              raw_text: q.slice(found.start, found.end),
              canonical_code: found.code,
              normalization_status: found.partial ? "PARTIAL" : "MATCHED",
              source: "SEMANTIC_INTERPRETER",
              confidence: null,
              start_char: found.start,
              end_char: found.end,
              modality: "VISUAL",
              surface_strength: surface,
              clause_id: clause.id,
              polarity,
              marker: surface === "NEUTRAL" ? null : surface,
            };
          const target = polarity === "NEGATIVE" ? negative : positive;
          if (!target.some((x) => x.concept_type === found.type && x.canonical_code === found.code && x.start_char! < c.end_char! && x.end_char! > c.start_char!)) target.push(c);
          if (surface === "PREFERENCE") preferences.push({ raw_text: c.raw_text, concept: found.code, surface_strength: "PREFERENCE" });
        }
        if (!accepted.length && content.length) unresolved.push({
          concept_type: "UNRESOLVED",
          raw_text: chunk.text,
          canonical_code: null,
          normalization_status: "UNRESOLVED",
          source: "SEMANTIC_INTERPRETER",
          confidence: null,
          start_char: chunk.start,
          end_char: chunk.end,
          modality: "ANY",
          surface_strength: "NEUTRAL",
          clause_id: clause.id,
          polarity: "POSITIVE",
          marker: null,
        });
      }
    const transcript: string[] = [],
      ocr: string[] = [],
      transcriptRe =
        /\b(?:doctor|patient|someone|clinician|audio|doktor|pesakit)?\s*(?:says?|says the words?|mentions?|talking about|speaks? about|spoken|sebut|cakap|bercakap)\s+(.+?)(?=$|\b(?:but|with|and|tapi|dan)\b)/gi,
      ocrRe =
        /\b(?:visible text|text visible|written on screen|text on screen|screen says|screen reads|words visible|text says|text saying|tulisan|tertulis|ada tulisan)(?:\s+(?:saying|reads?|is|perkataan))?\s*[:"']?\s*([\w-]+(?:\s+[\w-]+){0,4})?/gi;
    let m: RegExpExecArray | null;
    while ((m = transcriptRe.exec(q))) if (m[1]) transcript.push(clean(m[1]));
    while ((m = ocrRe.exec(q))) if (m[1]) ocr.push(clean(m[1]));
    const reverseOcr = /\b([A-Za-z0-9][A-Za-z0-9-]*(?:\s+[A-Za-z0-9-]+){0,3})\s+(?:is\s+)?(?:written|visible|displayed|appears)\s+(?:on\s+(?:the\s+)?screen)?\b/gi;
    while ((m = reverseOcr.exec(q))) if (m[1]) ocr.push(clean(m[1]));
    const brand = /\b(M-CURE|iGraft)\b/i.exec(q);
    if (brand && /\b(visible|written|screen|text|tulisan|tertulis)\b/i.test(q)) {
      // Prefer the explicit brand token over a greedy reverse-OCR capture such as
      // "show video with M-CURE". This keeps OCR literals precise and prevents UI grammar from
      // becoming part of the literal database predicate.
      for (let i=ocr.length-1;i>=0;i--)
        if (ocr[i].toLowerCase().includes(brand[1].toLowerCase())) ocr.splice(i,1);
      ocr.push(brand[1]);
    }
    const modalities: Modality[] = [
      ...(transcript.length ? ["TRANSCRIPT" as const] : []),
      ...(ocr.length ? ["OCR" as const] : []),
      ...(!transcript.length && !ocr.length ? ["VISUAL" as const] : []),
    ];
    const conflicts: Array<{ code: string; type: "CONCEPT_POLARITY_CONFLICT" }> = [];
    for (const p of positive)
      if (
        negative.some(
          (n) =>
            n.concept_type === p.concept_type &&
            n.canonical_code === p.canonical_code,
        )
      )
        conflicts.push({ code: p.canonical_code!, type: "CONCEPT_POLARITY_CONFLICT" });
    if (!positive.length && !negative.length && !transcript.length && !ocr.length && !unresolved.length)
      unresolved.push(
            {
              concept_type: "UNRESOLVED",
              raw_text: q,
              canonical_code: null,
              normalization_status: "UNRESOLVED",
              source: "SEMANTIC_INTERPRETER",
              confidence: null,
              start_char: 0,
              end_char: q.length,
              modality: "ANY",
              surface_strength: "NEUTRAL",
              clause_id: 0,
              polarity: "POSITIVE",
              marker: null,
            },
          );
    return {
      positive_concepts: positive,
      negative_concepts: negative,
      unresolved_concepts: unresolved,
      modalities,
      transcript_phrases: transcript,
      ocr_phrases: ocr,
      preferences,
      semantic_conflicts: conflicts,
    };
  }
}
function isConcept(v: unknown): v is SemanticConcept {
  if (!v || typeof v !== "object") return false;
  const x = v as any;
  return (
    typeof x.concept_type === "string" &&
    (typeof x.canonical_code === "string" || x.canonical_code === null) &&
    typeof x.raw_text === "string" &&
    [
      "MATCHED",
      "PARTIAL",
      "UNRESOLVED",
      "AMBIGUOUS",
      "NOT_FOUND",
      "INVALID",
    ].includes(x.normalization_status) &&
    ["VISUAL", "TRANSCRIPT", "OCR", "ANY"].includes(x.modality) &&
    (x.confidence === null ||
      (typeof x.confidence === "number" &&
        x.confidence >= 0 &&
        x.confidence <= 1))
  );
}
export function validateProviderOutput(raw: SemanticProviderOutput) {
  const allowed = new Set(config.provider_writable_fields),
    warnings: string[] = [],
    conflicts: Array<Record<string, unknown>> = [];
  for (const key of Object.keys(raw))
    if (!allowed.has(key) && key !== "semantic_conflicts") {
      warnings.push(`PROVIDER_FIELD_REJECTED:${key}`);
      conflicts.push({
        conflict_type: "PROVIDER_TRUST_BOUNDARY",
        provider_field: key,
        precedence: "BACKEND",
      });
    }
  const concepts = (key: string) => {
    const v = raw[key];
    if (v == null) return [];
    if (!Array.isArray(v) || !v.every(isConcept))
      throw new Error(`INVALID_PROVIDER_${key.toUpperCase()}`);
    return v as SemanticConcept[];
  };
  const strings = (key: string, values?: string[]) => {
    const v = raw[key];
    if (v == null) return [];
    if (
      !Array.isArray(v) ||
      !v.every((x) => typeof x === "string" && (!values || values.includes(x)))
    )
      throw new Error(`INVALID_PROVIDER_${key.toUpperCase()}`);
    return v as string[];
  };
  return {
    positive: concepts("positive_concepts"),
    negative: concepts("negative_concepts"),
    unresolved: concepts("unresolved_concepts"),
    modalities: strings("modalities", [
      "VISUAL",
      "TRANSCRIPT",
      "OCR",
      "ANY",
    ]) as Modality[],
    transcript: strings("transcript_phrases"),
    ocr: strings("ocr_phrases"),
    preferences: Array.isArray(raw.preferences) ? raw.preferences : [],
    warnings,
    conflicts,
    semanticConflicts: Array.isArray((raw as any).semantic_conflicts)
      ? (raw as any).semantic_conflicts
      : [],
  };
}
const deepFreeze = (x: any): any => {
  if (x && typeof x === "object" && !Object.isFrozen(x)) {
    Object.freeze(x);
    for (const v of Object.values(x)) deepFreeze(v);
  }
  return x;
};
export async function interpretQuery(
  original: string,
  provider: SemanticQueryInterpreter = new LocalOntologySemanticInterpreter(),
): Promise<CanonicalQueryPlan> {
  const q = clean(original),
    d = deterministicParse(q);
  let sem: any,
    status: "READY" | "DEGRADED" | "UNAVAILABLE" = "READY",
    warnings: string[] = [],
    conflicts = [...d.conflicts];
  try {
    const raw = await provider.interpret({
      original_query: q,
      remaining_semantic_text: q,
      consumed_spans: d.consumed_spans,
      deterministic: d,
      allowed_fields: config.provider_writable_fields,
    });
    sem = validateProviderOutput(raw);
    warnings.push(...sem.warnings);
    conflicts.push(
      ...sem.conflicts,
      ...sem.semanticConflicts.map((x: any) => ({
        conflict_type: "CONCEPT_POLARITY_CONFLICT",
        canonical_code: x.code,
        precedence: "PRESERVE_BOTH",
      })),
    );
  } catch (e) {
    status = "UNAVAILABLE";
    warnings.push(
      `SEMANTIC_PROVIDER_UNAVAILABLE:${e instanceof Error ? e.message : "unknown"}`,
    );
    sem = {
      positive: [],
      negative: [],
      unresolved: [
        {
          concept_type: "UNRESOLVED",
          raw_text: q,
          canonical_code: null,
          normalization_status: "UNRESOLVED",
          source: "SEMANTIC_INTERPRETER",
          confidence: null,
          start_char: 0,
          end_char: q.length,
          modality: "ANY",
          surface_strength: "NEUTRAL",
        },
      ],
      modalities: [],
      transcript: [],
      ocr: [],
      preferences: [],
    };
  }
  const min = config.result_count.minimum,
    max = config.result_count.maximum,
    countConflict = new Set(d.count_occurrences.map((x) => x.value)).size > 1,
    requested = countConflict ? null : d.count?.value ?? null,
    effective =
      countConflict
        ? "AMBIGUOUS"
        : requested == null
        ? config.result_count.system_default
        : Math.min(max, Math.max(min, requested)),
    countStatus =
      requested == null
        ? "NOT_FOUND"
        : requested !== effective
          ? "PARTIAL"
          : "MATCHED";
  if (requested !== null && requested !== effective)
    warnings.push("REQUESTED_COUNT_CLAMPED");
  const get = (type: NumericType) =>
    d.numeric_occurrences.find((x) => x.numeric_type === type)?.value ?? null;
  const getOccurrence = (type: NumericType) =>
    d.numeric_occurrences.find((x) => x.numeric_type === type) ?? null;
  const codes = sem.positive
      .map((x: SemanticConcept) => x.canonical_code)
      .filter(Boolean),
    semanticText =
      [
        ...new Set(
          codes.map((x: string) => x.toLowerCase().replace(/_/g, " ")),
        ),
      ].join(" ") || null,
    full = [...sem.ocr, ...sem.transcript].join(" ") || null;
  const plan: any = {
    query_schema_version: QUERY_SCHEMA_VERSION,
    intent: d.intent,
    original_query: q,
    result_request: {
      requested_count: requested,
      system_default_count: config.result_count.system_default,
      effective_count: effective,
      requested_count_raw: d.count?.raw_text ?? null,
      normalization_status: countStatus,
      extraction: d.count,
      requested_count_occurrences: d.count_occurrences,
    },
    media: {
      media_type: d.media_type?.value ?? "ANY",
      media_type_extraction: d.media_type,
      extensions: d.extensions.map((x) => x.value),
      extension_extractions: d.extensions,
    },
    semantic: {
      positive_concepts: sem.positive,
      negative_concepts: sem.negative,
      unresolved_concepts: sem.unresolved,
    },
    temporal: d.temporal,
    numeric: {
      occurrences: d.numeric_occurrences,
      age_exact: get("AGE_EXACT"),
      age_min: get("AGE_MIN"),
      age_max: get("AGE_MAX"),
      age_decade: get("AGE_DECADE"),
      graft_count_exact: get("GRAFT_COUNT_EXACT"),
      graft_count_min: get("GRAFT_COUNT_MIN"),
      graft_count_max: get("GRAFT_COUNT_MAX"),
      graft_count_inclusive_min: getOccurrence("GRAFT_COUNT_MIN")?.inclusive_min ?? null,
      graft_count_inclusive_max: getOccurrence("GRAFT_COUNT_MAX")?.inclusive_max ?? null,
      age_inclusive_min: getOccurrence("AGE_MIN")?.inclusive_min ?? null,
      age_inclusive_max: getOccurrence("AGE_MAX")?.inclusive_max ?? null,
      treatment_session_count: get("TREATMENT_SESSION_COUNT"),
      session_ordinal: get("SESSION_ORDINAL"),
      currency_amount: get("CURRENCY_AMOUNT"),
    },
    textual: {
      transcript: {
        required_terms: sem.transcript,
        raw_phrases: sem.transcript,
      },
      ocr: { required_terms: sem.ocr, raw_phrases: sem.ocr },
      modalities: sem.modalities,
    },
    constraints: { surface_markers: d.surface_markers },
    preferences: sem.preferences,
    ranking: d.sort,
    conversation: {
      reference_asset_identifier: null,
      reference_status:
        d.intent === "FIND_SIMILAR_MEDIA" ? "UNRESOLVED" : "NOT_APPLICABLE",
    },
    retrieval_text: {
      visual_semantic_query: semanticText,
      text_semantic_query:
        [semanticText, full].filter(Boolean).join(" ") || null,
      full_text_query: full,
    },
    parser_metadata: {
      query_parser_version: QUERY_PARSER_VERSION,
      deterministic_parser_version: DETERMINISTIC_PARSER_VERSION,
      semantic_interpreter_version: SEMANTIC_INTERPRETER_VERSION,
      query_schema_version: QUERY_SCHEMA_VERSION,
      configuration_version: QUERY_CONFIGURATION_VERSION,
      configuration_fingerprint: QUERY_CONFIGURATION_FINGERPRINT,
      semantic_provider: provider.provider,
      semantic_provider_model: provider.model,
      semantic_provider_model_version: provider.modelVersion,
      semantic_interpretation_status: status,
      detected_language: d.detected_language,
      validation_status: "VALID",
      warnings,
      conflicts,
      query_fingerprint: "",
    },
    validation: { status: "VALID", errors: [] },
  };
  const fpBase = structuredClone(plan);
  fpBase.parser_metadata.query_fingerprint = "";
  plan.parser_metadata.query_fingerprint = sha(stable(fpBase));
  return deepFreeze(plan);
}
