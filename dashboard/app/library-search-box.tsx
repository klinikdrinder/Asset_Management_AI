"use client";

import { useState } from "react";
import { activeFilterLabels, stateToSearchParams, type ConversationalSearchState } from "./lib/media/conversation";
import type { MediaQuery } from "./types/media";

export function LibrarySearchBox({ parsed, conversation, action = "/library" }: {
  parsed: MediaQuery;
  nlq?: string;
  conversation?: ConversationalSearchState;
  action?: string;
}) {
  const [isSearching, setIsSearching] = useState(false);
  const labels = conversation ? activeFilterLabels(conversation) : [];
  const persisted = conversation ? stateToSearchParams(conversation) : {};
  return <div className="conversationalSearch">
    <form className="libraryFilters" action={action} method="get" onSubmit={() => setIsSearching(true)}>
      {Object.entries(persisted).map(([name, value]) => <input type="hidden" name={name} value={value} key={name} />)}
      <input type="search" name="refine" placeholder={conversation?.semanticQuery ? "Refine your search…" : "Describe the photo or video you're looking for…"} aria-label="Natural-language search" maxLength={300} />
      <input name="query" defaultValue={parsed.search} placeholder="Search by filename…" aria-label="Search by filename" />
      <input name="extension" defaultValue={parsed.extension} placeholder="Extension" aria-label="Filter by extension" />
      <select name="sort" defaultValue={parsed.sort} aria-label="Sort files">
        <option value="newest">Newest first</option><option value="oldest">Oldest first</option>
        <option value="smallest">Smallest first</option><option value="largest">Largest first</option>
      </select>
      <select name="pageSize" defaultValue={parsed.pageSize} aria-label="Files per page"><option>25</option><option>50</option><option>100</option></select>
      <button type="submit" disabled={isSearching}>{isSearching ? "Searching…" : "Apply"}</button>
      <a href={action}>Start over</a>
    </form>
    {conversation?.semanticQuery && <p className="searchSummary"><b>Search:</b> {conversation.semanticQuery}</p>}
    {labels.length > 0 && <div className="activeSearchFilters" aria-label="Active interpreted filters"><b>Active filters:</b>{labels.map((label) => <span key={label}>{label}</span>)}</div>}
    {process.env.NODE_ENV === "development" && conversation && <details className="searchDebug"><summary>Interpreted search state</summary><pre>{JSON.stringify(conversation, null, 2)}</pre></details>}
  </div>;
}
