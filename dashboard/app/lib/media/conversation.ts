export type ConversationalSort = "relevance" | "newest" | "oldest" | "smallest" | "largest";
export type SearchMediaType = "image" | "video" | "document" | "other" | null;

export type ConversationalSearchState = {
  semanticQuery: string;
  mediaType: SearchMediaType;
  treatment: string | null;
  subject: string | null;
  doctorName: string | null;
  contentType: string | null;
  excludedContentTypes: string[];
  extension: string | null;
  sort: ConversationalSort;
};

export type SearchOperation =
  | "START_NEW_SEARCH"
  | "REFINE_SEMANTIC_QUERY"
  | "ADD_FILTER"
  | "REMOVE_FILTER"
  | "CHANGE_MEDIA_TYPE"
  | "CHANGE_SORT"
  | "RESET_SEARCH";

export type SearchIntent = {
  operation: SearchOperation;
  state: ConversationalSearchState;
  interpreted: string[];
  provider: string;
};

export interface QueryInterpreter {
  readonly providerName: string;
  interpret(input: string, previous: ConversationalSearchState): Promise<SearchIntent>;
}

export const EMPTY_CONVERSATIONAL_SEARCH: ConversationalSearchState = {
  semanticQuery: "",
  mediaType: null,
  treatment: null,
  subject: null,
  doctorName: null,
  contentType: null,
  excludedContentTypes: [],
  extension: null,
  sort: "relevance",
};

const clean = (value: string, max = 300) => value.trim().replace(/\s+/g, " ").slice(0, max);
const contains = (value: string, pattern: RegExp) => pattern.test(value.toLowerCase());

export class DeterministicQueryInterpreter implements QueryInterpreter {
  readonly providerName = "deterministic-v1";

  async interpret(input: string, previous: ConversationalSearchState): Promise<SearchIntent> {
    const text = clean(input);
    const lower = text.toLowerCase();
    if (!text) return { operation: "REFINE_SEMANTIC_QUERY", state: previous, interpreted: [], provider: this.providerName };
    if (/^(start over|reset search|clear (all|everything))\.?$/.test(lower)) {
      return { operation: "RESET_SEARCH", state: { ...EMPTY_CONVERSATIONAL_SEARCH }, interpreted: ["Search reset"], provider: this.providerName };
    }

    const state: ConversationalSearchState = { ...previous, excludedContentTypes: [...previous.excludedContentTypes] };
    const interpreted: string[] = [];
    let operation: SearchOperation = previous.semanticQuery ? "ADD_FILTER" : "START_NEW_SEARCH";
    let commandOnly = false;

    if (contains(lower, /\b(only videos?|videos? only)\b/)) { state.mediaType = "video"; interpreted.push("Videos"); operation = "CHANGE_MEDIA_TYPE"; commandOnly = true; }
    else if (contains(lower, /\b(only (images?|photos?)|(images?|photos?) only)\b/)) { state.mediaType = "image"; interpreted.push("Images"); operation = "CHANGE_MEDIA_TYPE"; commandOnly = true; }
    else if (contains(lower, /\b(include (photos?|images?) too|all media|videos? and (photos?|images?))\b/)) { state.mediaType = null; interpreted.push("All media"); operation = "REMOVE_FILTER"; commandOnly = true; }

    if (contains(lower, /\b(newest|latest)( first| ones?)?\b/)) { state.sort = "newest"; interpreted.push("Newest first"); operation = "CHANGE_SORT"; commandOnly = true; }
    else if (contains(lower, /\boldest( first| ones?)?\b/)) { state.sort = "oldest"; interpreted.push("Oldest first"); operation = "CHANGE_SORT"; commandOnly = true; }

    if (contains(lower, /\b(clear|remove|without) (the )?doctor( filter)?\b/)) { state.doctorName = null; interpreted.push("Doctor filter removed"); operation = "REMOVE_FILTER"; commandOnly = true; }
    else if (contains(lower, /\b(with|only ones? with|by) (datuk )?dr\.? inder\b|\bdatuk dr\.? inder\b/)) { state.doctorName = "Datuk Dr Inder"; interpreted.push("Datuk Dr Inder"); commandOnly = previous.semanticQuery.length > 0; }

    if (contains(lower, /\b(no|not|without) testimonials?\b/)) {
      if (!state.excludedContentTypes.includes("Patient Testimonial")) state.excludedContentTypes.push("Patient Testimonial");
      interpreted.push("Exclude Patient Testimonial"); operation = "ADD_FILTER"; commandOnly = true;
    } else if (contains(lower, /\b(include|allow) testimonials?\b/)) {
      state.excludedContentTypes = state.excludedContentTypes.filter((value) => value !== "Patient Testimonial");
      interpreted.push("Testimonials included"); operation = "REMOVE_FILTER"; commandOnly = true;
    }

    if (contains(lower, /\b(long hair fue|igraft)\b/)) { state.treatment = "iGraft Long Hair FUE"; interpreted.push(state.treatment); }
    else if (contains(lower, /\b(fue|hair transplant)\b/) && !commandOnly) { state.treatment = "FUE Hair Transplant"; interpreted.push(state.treatment); }
    if (contains(lower, /\b(female patients?|woman|women)\b/) && !commandOnly) { state.subject = "Female patient"; interpreted.push(state.subject); }
    else if (contains(lower, /\bmale patients?|man\b/) && !commandOnly) { state.subject = "Male patient"; interpreted.push(state.subject); }
    if (contains(lower, /\bconsultation\b/) && !commandOnly) { state.contentType = "Consultation"; interpreted.push(state.contentType); }
    else if (contains(lower, /\btestimonial\b/) && !contains(lower, /\b(no|not|without) testimonials?\b/) && !commandOnly) { state.contentType = "Patient Testimonial"; interpreted.push(state.contentType); }

    if (!commandOnly) {
      state.semanticQuery = text;
      operation = previous.semanticQuery ? "REFINE_SEMANTIC_QUERY" : "START_NEW_SEARCH";
    }
    return { operation, state, interpreted: [...new Set(interpreted)], provider: this.providerName };
  }
}

export function activeFilterLabels(state: ConversationalSearchState): string[] {
  return [
    state.subject,
    state.treatment,
    state.mediaType ? `${state.mediaType[0].toUpperCase()}${state.mediaType.slice(1)}s` : null,
    state.doctorName,
    state.contentType,
    ...state.excludedContentTypes.map((value) => `Not ${value}`),
    state.sort !== "relevance" ? `${state.sort[0].toUpperCase()}${state.sort.slice(1)} first` : null,
  ].filter((value): value is string => Boolean(value));
}

export function stateFromSearchParams(input: Record<string, string | undefined>): ConversationalSearchState {
  const media = ["image", "video", "document", "other"].includes(input.cs_media ?? "") ? input.cs_media as Exclude<SearchMediaType, null> : null;
  const sort = ["relevance", "newest", "oldest", "smallest", "largest"].includes(input.cs_sort ?? "") ? input.cs_sort as ConversationalSort : "relevance";
  return {
    semanticQuery: clean(input.cs_q ?? input.nlq ?? ""), mediaType: media,
    treatment: clean(input.cs_treatment ?? "", 120) || null,
    subject: clean(input.cs_subject ?? "", 120) || null,
    doctorName: clean(input.cs_doctor ?? "", 120) || null,
    contentType: clean(input.cs_content ?? "", 120) || null,
    excludedContentTypes: clean(input.cs_exclude ?? "", 240).split("|").filter(Boolean).slice(0, 10),
    extension: clean(input.extension ?? "", 12) || null, sort,
  };
}

export function stateToSearchParams(state: ConversationalSearchState): Record<string, string> {
  const result: Record<string, string> = {};
  if (state.semanticQuery) result.cs_q = state.semanticQuery;
  if (state.mediaType) result.cs_media = state.mediaType;
  if (state.treatment) result.cs_treatment = state.treatment;
  if (state.subject) result.cs_subject = state.subject;
  if (state.doctorName) result.cs_doctor = state.doctorName;
  if (state.contentType) result.cs_content = state.contentType;
  if (state.excludedContentTypes.length) result.cs_exclude = state.excludedContentTypes.join("|");
  if (state.sort !== "relevance") result.cs_sort = state.sort;
  return result;
}

export function effectiveSemanticQuery(state: ConversationalSearchState): string {
  return clean([state.semanticQuery, state.treatment, state.subject, state.doctorName, state.contentType].filter(Boolean).join(". "));
}
