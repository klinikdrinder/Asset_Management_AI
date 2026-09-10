/**
 * Deprecated versioned path. It is an alias, not a search authority: it re-exports the canonical
 * handler verbatim, so an old client hitting /api/search/v3 executes exactly the same code as
 * /api/search. No separate parser, retrieval, ranking or fallback exists behind this path.
 *
 * Classification: MIGRATED. Remove once no deployed client references the versioned URL.
 */
export { POST } from "../route";
