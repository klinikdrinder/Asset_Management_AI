export type V3Intent = {
  queryType: "NEW_SEARCH" | "REFINEMENT" | "COUNT_CHANGE" | "NEXT_RESULTS" | "FILTER_CHANGE";
  resolvedQuery: string;
  requestedCount: number;
  countExplicit: boolean;
  filters: Record<string, string>;
  excludedAssetIds: string[];
};

export type V3Context = Pick<V3Intent, "resolvedQuery" | "filters" | "requestedCount"> & {
  returnedAssetIds?: string[];
};

const MAX_RESULTS = 50;
const media = [[/\b(videos?|footage|clips?)\b/i, "video"], [/\b(images?|photos?|pictures?)\b/i, "image"]] as const;
const anatomy = [[/\b(front(?:al)? hairline|front hairline|hairline)\b/i,"FRONTAL_HAIRLINE"],[/\bfrontal scalp\b/i,"FRONTAL_SCALP"],[/\bscalp\b/i,"SCALP"],[/\bcheeks?\b/i,"CHEEK"],[/\bjawline\b/i,"JAWLINE"],[/\bneck\b/i,"NECK"]] as const;
const actions = [[/\bpoint(?:ing|s|ed)?\b/i,"POINTING"],[/\bexamin(?:e|es|ed|ing)\b/i,"EXAMINING"],[/\bconsult(?:ation|ing)?\b/i,"CONSULTING"],[/\bimplant(?:ing|ation)?\b/i,"IMPLANTING_GRAFTS"],[/\binject(?:ing|ion)?\b/i,"INJECTING"],[/\bclean(?:sing|se|ing)?\b/i,"CLEANSING"]] as const;
const treatments = [[/\b(FUE implantation|graft implantation)\b/i,"FUE_IMPLANTATION"],[/\b(FUE|follicular unit extraction|hair transplant)\b/i,"HAIR_TRANSPLANT_FUE"],[/\b(hairline design|hairline planning|frontal design)\b/i,"FUE_HAIRLINE_DESIGN"]] as const;

function first(query: string, values: readonly (readonly [RegExp,string])[]) {
  return values.find(([pattern]) => pattern.test(query))?.[1];
}

export function interpretV3Query(raw: string, previous?: V3Context): V3Intent {
  const query = raw.trim().replace(/\s+/g," ").slice(0,300);
  const next = /\b(next|more)\s+(\d+)?\b/i.test(query);
  const refinement = /^(only|remove|exclude|without|show me only)\b/i.test(query);
  // A bare number may describe the subject (for example, "over 30 years old").
  // It is a result count only when the user explicitly uses a count verb.
  const countMatch = query.match(/\b(?:show me|show|find|give me|next)\s+(\d{1,3})\b/i);
  const countExplicit = Boolean(countMatch);
  const requestedCount = Math.max(1,Math.min(MAX_RESULTS,countMatch ? Number(countMatch[1]) : previous?.requestedCount ?? 5));
  const filters: Record<string,string> = {...(previous?.filters ?? {})};
  const mt=first(query,media); if(mt) filters.media_type=mt;
  if(/\b(remove|exclude|without)\s+(procedure|procedures|procedure footage)\b/i.test(query)) filters.excluded_content_type="PROCEDURE";
  else if(/\bprocedure(?: footage)?\b/i.test(query)) filters.content_type="PROCEDURE";
  if(/\bconsultation(?: room)?\b/i.test(query)) { filters.scene_type="CONSULTATION"; filters.environment="consultation"; }
  if(/\bclinic\b/i.test(query)) filters.environment="clinic";
  if(/\b(close[- ]?ups?|closeups?)\b/i.test(query)) filters.shot_type="CLOSEUP";
  if(/\bvertical\b/i.test(query)) filters.content_type="B_ROLL";
  if(/\bdoctor|clinician\b/i.test(query)) filters.role="CLINICIAN_LIKE";
  if(/\bpatient\b/i.test(query)) filters.role="PATIENT_LIKE";
  const an=first(query,anatomy); if(an) filters.anatomy=an;
  const action=first(query,actions); if(action) filters.action=action;
  const treatment=first(query,treatments); if(treatment) filters.treatment=treatment;
  const ext=query.match(/\b(?:\.)(jpe?g|png|mp4|mov)\b/i); if(ext) filters.extension=ext[1].toLowerCase();
  return {
    queryType: next ? "NEXT_RESULTS" : refinement ? "REFINEMENT" : countExplicit && previous && query.split(" ").length<5 ? "COUNT_CHANGE" : "NEW_SEARCH",
    resolvedQuery: (next || refinement) && previous?.resolvedQuery ? previous.resolvedQuery : query,
    requestedCount,
    countExplicit,
    filters,
    excludedAssetIds: next ? [...new Set(previous?.returnedAssetIds ?? [])] : [],
  };
}

export const V3_RANKING = Object.freeze({
  structured: 0.30, visualScene: 0.20, visualAsset: 0.18,
  lexicalAsset: 0.12, lexicalScene: 0.08, visualKeyframe: 0.07, filename: 0.05,
  minimumRelevance: 0.08, defaultResults: 5, maximumResults: MAX_RESULTS,
});
