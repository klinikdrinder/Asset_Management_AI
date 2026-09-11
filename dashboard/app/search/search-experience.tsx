"use client";
import { useCallback, useMemo, useState, type FormEvent } from "react";
import { getFirebaseClientAuth } from "../lib/firebase/client";
import { AssetThumbnail } from "../asset-thumbnail";
import { maskFilename } from "../lib";

// The differentiated search surface: it shows how the query was parsed, and for every result
// why it matched (per-channel contributions + evidence chips), which generic semantic search
// cannot. It calls POST /api/search directly from the browser and forwards the Firebase ID
// token so the request runs under the user's own RLS identity (no service role).

type Channel = { channel: string; representation: string | null; contribution: number | null; rank: number | null };
type WhyMatched = { score: number | null; channels: Channel[]; matchedConcepts: string[]; rrf: number | null } | null;
type Evidence = { code: string; label: string; state: string; confidence: number | null };
type Item = { id: string; filename: string; category: string; thumbnailUrl: string | null; matchPercent: number | null; whyMatched: WhyMatched; evidence: Evidence[] };
type ParsedIntent = { intent: string | null; resolved_query: string; media_type: string | null; requested_count: number | null; sort: string; hard: string[]; exclusions: string[]; strong: string[]; concepts: string[] };
type SearchResponse = { sessionId: string; queryId: string; parsedIntent: ParsedIntent; items: Item[]; total: number };

const pretty = (s: string) => s.toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
const stateClass = (s: string) => (s === "OBSERVED" ? "chipObserved" : s === "FALSE" ? "chipFalse" : "chipUnknown");

async function firebaseToken(): Promise<string | null> {
  try { return (await getFirebaseClientAuth().currentUser?.getIdToken()) ?? null; } catch { return null; }
}

export function SearchExperience() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"idle" | "searching" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [feedback, setFeedback] = useState<Record<string, string>>({});
  // Facets are aggregated from the current result set (media type + matched concepts). They stay
  // sparse until normalisation lands more structured concepts — the component is built now so it
  // fills in as the data improves. Selecting facets filters the shown results client-side.
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set());
  const [activeConcepts, setActiveConcepts] = useState<Set<string>>(new Set());
  const facets = useMemo(() => {
    const types = new Map<string, number>(), concepts = new Map<string, number>();
    for (const it of data?.items ?? []) { types.set(it.category, (types.get(it.category) ?? 0) + 1); for (const e of it.evidence) concepts.set(e.label, (concepts.get(e.label) ?? 0) + 1); }
    return { types: [...types.entries()], concepts: [...concepts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12) };
  }, [data]);
  const shown = (data?.items ?? []).filter((it) => (activeTypes.size === 0 || activeTypes.has(it.category)) && (activeConcepts.size === 0 || it.evidence.some((e) => activeConcepts.has(e.label))));
  const toggle = (set: Set<string>, val: string, setter: (s: Set<string>) => void) => { const next = new Set(set); if (next.has(val)) next.delete(val); else next.add(val); setter(next); };

  const runSearch = useCallback(async (event: FormEvent) => {
    event.preventDefault();
    const q = query.trim();
    if (!q) return;
    setStatus("searching"); setErrorMsg("");
    const token = await firebaseToken();
    try {
      const response = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ query: q }),
      });
      if (!response.ok) {
        setStatus("error");
        setErrorMsg(response.status === 401 ? "Your session has expired — please sign in again." : "Search is temporarily unavailable.");
        return;
      }
      setData(await response.json() as SearchResponse);
      setActiveTypes(new Set()); setActiveConcepts(new Set());
      setStatus("idle");
    } catch {
      setStatus("error"); setErrorMsg("Search could not be reached. Check your connection and try again.");
    }
  }, [query]);

  const sendFeedback = useCallback(async (assetId: string, feedbackType: "GOOD_MATCH" | "BAD_MATCH") => {
    if (!data) return;
    setFeedback((prev) => ({ ...prev, [assetId]: feedbackType }));
    const token = await firebaseToken();
    try {
      await fetch("/api/search/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ queryId: data.queryId, assetId, feedbackType }),
      });
    } catch { /* best-effort telemetry; leave the optimistic state */ }
  }, [data]);

  const intent = data?.parsedIntent;
  return (
    <div className="semanticSearch">
      <form className="semanticSearchForm" onSubmit={runSearch}>
        <input
          type="search" value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="Describe the media — e.g. 'FUE graft extraction on the crown, no on-screen text'"
          aria-label="Semantic search" maxLength={300}
        />
        <button type="submit" disabled={status === "searching"}>{status === "searching" ? "Searching…" : "Search"}</button>
      </form>
      <p className="pendingNote">Assets still awaiting clinical classification are hidden by access control and may not appear.</p>

      {status === "error" && <div className="secureError" role="alert"><b>Search unavailable</b><p>{errorMsg}</p></div>}

      {intent && (
        <section className="intentPanel" aria-label="How your search was read">
          <span className="intentLead">Read as</span>
          {intent.media_type && intent.media_type !== "ANY" && <span className="intentBadge">Type: {pretty(intent.media_type)}</span>}
          {intent.concepts.map((c) => <span className="intentBadge" key={`c-${c}`}>{pretty(c)}</span>)}
          {intent.hard.map((h) => <span className="intentBadge hard" key={`h-${h}`}>Must: {pretty(String(h))}</span>)}
          {intent.strong.map((s) => <span className="intentBadge" key={`s-${s}`}>Prefer: {pretty(String(s))}</span>)}
          {intent.exclusions.map((x) => <span className="intentBadge exclude" key={`x-${x}`}>Not: {pretty(String(x))}</span>)}
          {intent.sort && intent.sort !== "RELEVANCE" && <span className="intentBadge">Sort: {pretty(intent.sort)}</span>}
        </section>
      )}

      {status === "searching" && <section className="fileGrid" aria-hidden><span className="searchSkeleton" /><span className="searchSkeleton" /><span className="searchSkeleton" /></section>}

      {data && status !== "searching" && (
        data.items.length === 0
          ? <section className="emptyModern"><h2>No matches</h2><p>Try describing the media differently, or remove an exclusion.</p></section>
          : <>
            <section className="facetRail" aria-label="Refine results">
              {facets.types.length > 1 && <div className="facetGroup"><span className="facetLead">Type</span>{facets.types.map(([t, c]) => <button type="button" key={t} className={`facetChip${activeTypes.has(t) ? " active" : ""}`} onClick={() => toggle(activeTypes, t, setActiveTypes)}>{t} <em>{c}</em></button>)}</div>}
              {facets.concepts.length > 0 && <div className="facetGroup"><span className="facetLead">Concepts</span>{facets.concepts.map(([label, c]) => <button type="button" key={label} className={`facetChip${activeConcepts.has(label) ? " active" : ""}`} onClick={() => toggle(activeConcepts, label, setActiveConcepts)}>{label} <em>{c}</em></button>)}</div>}
            </section>
            {shown.length === 0 && <p className="facetEmpty">No results match the selected facets.</p>}
            <section className="resultList" aria-label="Search results">
              {shown.map((item) => (
                <article className="resultCard" key={item.id}>
                  <a className="resultThumb" href={`/library/files/${item.id}`} aria-label={`Open ${maskFilename(item.filename)}`}>
                    {item.thumbnailUrl && <AssetThumbnail key={item.thumbnailUrl} src={item.thumbnailUrl} alt="" />}
                    <span className={`largeType ${item.category}`}>{item.category === "video" ? "▶" : item.category === "document" ? "▤" : item.category === "image" ? "▧" : "?"}</span>
                    {item.matchPercent != null && <span className="matchBadge">{Math.round(item.matchPercent)}% match</span>}
                  </a>
                  <div className="resultBody">
                    <a href={`/library/files/${item.id}`}><h3>{maskFilename(item.filename)}</h3></a>

                    {item.evidence.length > 0 && (
                      <div className="evidenceRow" aria-label="Matched concepts">
                        {item.evidence.map((e) => (
                          <span className={`evidenceChip ${stateClass(e.state)}`} key={e.code} title={`${e.state}${e.confidence != null ? ` · ${Math.round(e.confidence * 100)}% confidence` : ""}`}>
                            {e.label}{e.confidence != null && <em> {Math.round(e.confidence * 100)}%</em>}
                          </span>
                        ))}
                      </div>
                    )}

                    {item.whyMatched && item.whyMatched.channels.length > 0 && (
                      <details className="whyPanel">
                        <summary>Why did this match?</summary>
                        <ul>
                          {item.whyMatched.channels.map((ch) => (
                            <li className="channelRow" key={ch.channel}>
                              <span className="channelName">{pretty(ch.channel)}</span>
                              <span className="channelMeter"><span className="channelFill" style={{ width: `${Math.round((ch.contribution ?? 0) * 100)}%` }} /></span>
                              {ch.rank != null && <span className="channelRank">#{ch.rank}</span>}
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}

                    <div className="feedbackRow" aria-label="Was this a good match?">
                      <button type="button" className={`thumbBtn${feedback[item.id] === "GOOD_MATCH" ? " chosen" : ""}`} onClick={() => sendFeedback(item.id, "GOOD_MATCH")} aria-pressed={feedback[item.id] === "GOOD_MATCH"}>👍 Good</button>
                      <button type="button" className={`thumbBtn${feedback[item.id] === "BAD_MATCH" ? " chosen" : ""}`} onClick={() => sendFeedback(item.id, "BAD_MATCH")} aria-pressed={feedback[item.id] === "BAD_MATCH"}>👎 Off</button>
                      {feedback[item.id] && <span className="feedbackThanks">Thanks</span>}
                    </div>
                  </div>
                </article>
              ))}
            </section>
            </>
      )}
    </div>
  );
}
