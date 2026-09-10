import { createHash } from "node:crypto";

export const BENCHMARK_EVALUATOR_VERSION = "kdi_query_parser_evaluator_v2";
export type TemporalExpectation = {
  year?: { operator?: string; value: number };
  timestamp?: { seconds: number; approximate?: boolean };
  duration?: { min_seconds?: number | null; max_seconds?: number | null; min_inclusive?: boolean | null; max_inclusive?: boolean | null };
};
export type CountExpectation = { values: number[]; conflict?: boolean };
export type BenchmarkExpectation = {
  result_count?: CountExpectation;
  non_result_numbers?: number[];
  media_type?: string;
  extensions?: string[];
  numeric?: Record<string, number | null>;
  temporal?: TemporalExpectation;
  positive?: string[];
  negative?: string[];
  modalities?: string[];
  conflict?: string;
  unresolved?: boolean;
};

export const BENCHMARK_EVALUATOR_FINGERPRINT = createHash("sha256").update([
  BENCHMARK_EVALUATOR_VERSION,
  "canonical-query-schema-v1_1",
  "typed-temporal-normalization-v2",
  "occurrence-based-result-count-metrics-v2",
].join("\n")).digest("hex");

export function normalizeActual(plan: any) {
  return {
    count: {
      values: (plan.result_request.requested_count_occurrences ?? []).map((x: any) => x.value),
      requested: plan.result_request.requested_count,
    },
    media_type: plan.media.media_type,
    extensions: plan.media.extensions,
    numeric: plan.numeric,
    temporal: {
      year: plan.temporal.year ? { operator: plan.temporal.year.operator ?? "EXACT", value: plan.temporal.year.value } : undefined,
      timestamp: plan.temporal.timestamp ? { seconds: plan.temporal.timestamp.timestamp_seconds, approximate: !!plan.temporal.timestamp.approximate } : undefined,
      duration: plan.temporal.duration ? {
        min_seconds: plan.temporal.duration.duration_min_seconds ?? null,
        max_seconds: plan.temporal.duration.duration_max_seconds ?? null,
        min_inclusive: plan.temporal.duration.min_inclusive ?? null,
        max_inclusive: plan.temporal.duration.max_inclusive ?? null,
      } : undefined,
    },
    positive: plan.semantic.positive_concepts.map((x: any) => x.canonical_code).filter(Boolean),
    negative: plan.semantic.negative_concepts.map((x: any) => x.canonical_code).filter(Boolean),
    modalities: plan.textual.modalities,
    conflicts: plan.parser_metadata.conflicts.map((x: any) => x.conflict_type),
    unresolved: plan.semantic.unresolved_concepts.length > 0,
    schema_valid: plan.validation.status === "VALID",
  };
}

export function evaluatePlan(expected: BenchmarkExpectation, plan: any) {
  const actual = normalizeActual(plan), differences: Array<{field:string;expected:any;actual:any;critical:boolean}>=[];
  const diff=(field:string,e:any,a:any,critical=true)=>differences.push({field,expected:e,actual:a,critical});
  if(expected.result_count){const e=expected.result_count.values,a=actual.count.values;if(JSON.stringify(e)!==JSON.stringify(a))diff("result_count.occurrences",e,a);if(expected.result_count.conflict&&!actual.conflicts.includes("COUNT_CONFLICT"))diff("conflict.COUNT_CONFLICT",true,false)}
  if(expected.media_type&&actual.media_type!==expected.media_type)diff("media_type",expected.media_type,actual.media_type);
  if(expected.extensions&&JSON.stringify(expected.extensions)!==JSON.stringify(actual.extensions))diff("extensions",expected.extensions,actual.extensions);
  for(const[k,v]of Object.entries(expected.numeric??{}))if(actual.numeric[k]!==v)diff(`numeric.${k}`,v,actual.numeric[k]);
  if(expected.temporal?.year&&actual.temporal.year?.value!==expected.temporal.year.value)diff("temporal.year",expected.temporal.year,actual.temporal.year);
  if(expected.temporal?.timestamp){if(actual.temporal.timestamp?.seconds!==expected.temporal.timestamp.seconds)diff("temporal.timestamp",expected.temporal.timestamp,actual.temporal.timestamp);else if(expected.temporal.timestamp.approximate!==undefined&&actual.temporal.timestamp.approximate!==expected.temporal.timestamp.approximate)diff("temporal.timestamp.approximate",expected.temporal.timestamp.approximate,actual.temporal.timestamp.approximate)}
  if(expected.temporal?.duration){for(const[k,v]of Object.entries(expected.temporal.duration))if(v!==undefined&&(actual.temporal.duration as any)?.[k]!==v)diff(`temporal.duration.${k}`,v,(actual.temporal.duration as any)?.[k]);}
  for(const code of expected.positive??[])if(!actual.positive.includes(code))diff(`positive.${code}`,true,false);
  for(const code of expected.negative??[])if(!actual.negative.includes(code))diff(`negative.${code}`,true,false);
  for(const modality of expected.modalities??[])if(!actual.modalities.includes(modality))diff(`modality.${modality}`,true,false);
  if(expected.conflict&&!actual.conflicts.includes(expected.conflict))diff(`conflict.${expected.conflict}`,true,false);
  if(expected.unresolved&&!actual.unresolved)diff("unresolved",true,false);
  const nonResult=new Set(expected.non_result_numbers??[]),falseResultCount=actual.count.values.filter((x:number)=>nonResult.has(x)).length;
  const expectedCounts=expected.result_count?.values??[],missedExplicitResultCount=expectedCounts.filter(x=>!actual.count.values.includes(x)).length;
  return {passed:differences.length===0,differences,false_result_count:falseResultCount,missed_explicit_result_count:missedExplicitResultCount,schema_valid:actual.schema_valid,actual};
}

export function validateExpectation(expected: BenchmarkExpectation) {
  const errors:string[]=[];
  if(expected.result_count&&(!Array.isArray(expected.result_count.values)||expected.result_count.values.some(x=>!Number.isInteger(x)||x<1)))errors.push("INVALID_RESULT_COUNT");
  if(expected.temporal?.year&&!Number.isInteger(expected.temporal.year.value))errors.push("INVALID_YEAR");
  if(expected.temporal?.timestamp&&expected.temporal.timestamp.seconds<0)errors.push("INVALID_TIMESTAMP");
  if(expected.temporal?.duration&&expected.temporal.duration.min_seconds!=null&&expected.temporal.duration.max_seconds!=null&&expected.temporal.duration.min_seconds>expected.temporal.duration.max_seconds)errors.push("INVALID_DURATION_RANGE");
  if(expected.media_type&&!['VIDEO','IMAGE','ANY'].includes(expected.media_type))errors.push("INVALID_MEDIA_TYPE");
  return errors;
}
