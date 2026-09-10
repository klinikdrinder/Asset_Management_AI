import {createHash} from "node:crypto";
import registry from "../../config/semantic-search/kdi_search_vocabulary_v1.json";

/**
 * The one canonical natural-language to canonical-concept mapping for the whole search pipeline.
 *
 * Before this registry, concept aliases lived inside the parser configuration, so each search
 * generation could drift into its own vocabulary. The registry is now the single source: the parser
 * resolves concepts from it, and the query expander expands the codes it produces. It is a strict
 * superset of the aliases the parser previously carried, so no existing resolution is lost.
 *
 * Query-side only. Nothing here alters semantic truth, and a named clinical procedure stays
 * reachable only from explicit procedure wording - generic gloves, instrument, scalp or contact
 * wording never resolves to a named procedure.
 */
export const SEARCH_VOCABULARY_VERSION = registry.search_vocabulary_version as string;

export type VocabularyCategories = Record<string, Record<string, string[]>>;

export const SEARCH_VOCABULARY = registry.categories as VocabularyCategories;

export const SEARCH_VOCABULARY_FINGERPRINT = createHash("sha256")
  .update(JSON.stringify(registry.categories))
  .digest("hex");

/** Every canonical concept code the vocabulary can resolve. */
export function vocabularyConceptCodes(): string[] {
  return [...new Set(Object.values(SEARCH_VOCABULARY).flatMap((codes) => Object.keys(codes)))].sort();
}

/** Resolves an exact surface form to its category and canonical code, or null. */
export function resolveVocabularyTerm(term: string): {category: string; code: string} | null {
  const needle = term.trim().toLowerCase();
  if (!needle) return null;
  for (const [category, codes] of Object.entries(SEARCH_VOCABULARY))
    for (const [code, terms] of Object.entries(codes))
      if (terms.some((value) => value.toLowerCase() === needle)) return {category, code};
  return null;
}

/** Surface forms registered for a canonical concept code. */
export function vocabularyTermsFor(code: string): string[] {
  for (const codes of Object.values(SEARCH_VOCABULARY))
    if (codes[code]) return [...codes[code]];
  return [];
}
