/* eslint-disable @next/next/no-img-element */
"use client";

import { FormEvent, useRef, useState } from "react";
import type { MediaAsset, MediaPage } from "../../types/media";

type View = "search" | "all" | "images" | "videos" | "documents" | "admin";
export type PreviewUser = { email: string; role: string; status: string };
type Catalog = { all: MediaPage; images: MediaPage; videos: MediaPage; documents: MediaPage };
type SearchResponse = MediaPage & { error?: string; resolvedQuery?: string };

const icons: Record<View | "help", string> = { search: "⌕", all: "▤", images: "▧", videos: "▷", documents: "▱", admin: "⚙", help: "?" };
const viewLabels: Record<Exclude<View, "admin">, string> = { search: "AI Search", all: "All Files", images: "Images", videos: "Videos", documents: "Documents" };
const formatBytes = (size: number | null) => size == null ? "Size unavailable" : size >= 1e9 ? `${(size / 1e9).toFixed(1)} GB` : size >= 1e6 ? `${(size / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1e3))} KB`;
const displayRole = (role: string) => role.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

function AssetType({ asset }: { asset: MediaAsset }) {
  return <>{asset.category[0].toUpperCase() + asset.category.slice(1)} · {(asset.extension || "File").toUpperCase()} · {formatBytes(asset.sizeBytes)}</>;
}

function PreviewModal({ asset, close }: { asset: MediaAsset; close: () => void }) {
  return <dialog className="kdiPreviewModal" open aria-labelledby="kdi-preview-title">
    <div className="kdiPreviewCard">
      <header><div><small>MEDIA PREVIEW</small><h2 id="kdi-preview-title">{asset.filename}</h2><p><AssetType asset={asset} /></p></div><button onClick={close} aria-label="Close preview">×</button></header>
      <div className="kdiPreviewStage">{asset.category === "image" && asset.previewUrl ? <img src={asset.previewUrl} alt={asset.filename} /> : asset.category === "video" && asset.previewUrl ? <video src={asset.previewUrl} controls autoPlay={false} preload="metadata">Video preview unavailable.</video> : <div>Preview is not available for this file type.</div>}</div>
      <footer><button onClick={close}>Back to results</button><button disabled title="Downloads are disabled in the local read-only preview">Download disabled</button></footer>
    </div>
  </dialog>;
}

function ResultCard({ asset, open }: { asset: MediaAsset; open: () => void }) {
  return <article className="kdiResultCard">
    <button className={`kdiResultThumb ${asset.category}`} onClick={open} disabled={!asset.canPreview} aria-label={`Preview ${asset.filename}`}>
      {asset.thumbnailUrl ? <img src={asset.thumbnailUrl} alt="" loading="lazy" /> : <span>{asset.category === "video" ? "▶" : asset.category === "image" ? "IMAGE" : "FILE"}</span>}
      {asset.category === "video" && <i>Video</i>}
    </button>
    <div className="kdiResultBody"><h3>{asset.filename}</h3><p className="kdiBasicMeta"><AssetType asset={asset} /></p><p className="kdiDescription">{asset.shortCaption || `Registered ${asset.category} from ${asset.sourceFolder}.`}</p></div>
    <div className="kdiResultActions"><button onClick={open} disabled={!asset.canPreview}>Preview</button><button disabled title="Downloads are disabled in this local preview">Download</button></div>
  </article>;
}

function Results({ page, search, open }: { page: MediaPage; search?: boolean; open: (asset: MediaAsset) => void }) {
  if (!page.items.length) return <section className="kdiEmpty"><span>⌕</span><h2>{search ? "No strong matches found." : "No files are registered in this category."}</h2><p>{search ? "Try describing the person, treatment, setting or action differently." : "Files will appear here when they are registered."}</p></section>;
  return <><div className="kdiResultCount">{page.total.toLocaleString()} results found</div><section className="kdiResults" aria-label="Media results">{page.items.map((asset) => <ResultCard key={asset.id} asset={asset} open={() => open(asset)} />)}</section><div className="kdiShowing">Showing {page.items.length.toLocaleString()} of {page.total.toLocaleString()} results</div></>;
}

function Browse({ view, page, open }: { view: Exclude<View, "search" | "admin">; page: MediaPage; open: (asset: MediaAsset) => void }) {
  return <div className="kdiPage"><header className="kdiPageHeading"><div><h1>{viewLabels[view]}</h1><p>Browse real registered KDI media.</p></div><span>{page.total.toLocaleString()} files</span></header><div className="kdiBrowseTools"><label><span>Search filenames</span><input placeholder="Search by filename" disabled title="Use AI Search for natural-language requests" /></label><label><span>Sort</span><select disabled defaultValue="newest"><option value="newest">Newest first</option></select></label></div><Results page={page} open={open} /></div>;
}

function Admin({ catalog, users, open, goAll }: { catalog: Catalog; users: PreviewUser[]; open: (asset: MediaAsset) => void; goAll: () => void }) {
  return <div className="kdiPage kdiAdmin"><header className="kdiPageHeading"><div><h1>Admin Panel</h1><p>Manage your media library, files and users.</p></div></header>
    <section className="kdiAdminSection"><div><h2>Upload Files</h2><p>Upload new files to the media library.</p></div><div className="kdiUploadBox"><span>⇧</span><b>Drag and drop files here</b><small>Secure uploads remain available through the protected production admin workflow.</small><button disabled>Upload Files</button></div></section>
    <section className="kdiAdminSection"><div><h2>Manage Files</h2><p>View, edit or manage files in the library.</p></div><div className="kdiTableWrap"><table><thead><tr><th>File Name</th><th>Type</th><th>Size</th><th>Uploaded On</th><th>Actions</th></tr></thead><tbody>{catalog.all.items.slice(0, 5).map((asset) => <tr key={asset.id}><td>{asset.filename}</td><td>{asset.category}</td><td>{formatBytes(asset.sizeBytes)}</td><td>{asset.modifiedAt ? new Date(asset.modifiedAt).toLocaleDateString("en-MY") : "—"}</td><td><button onClick={() => open(asset)} disabled={!asset.canPreview}>Preview</button><button disabled>Edit metadata</button></td></tr>)}</tbody></table></div><button className="kdiOutlineButton" onClick={goAll}>View All Files</button></section>
    <section className="kdiAdminSection"><div className="kdiSectionHead"><div><h2>Manage Users</h2><p>Invite users and control their access.</p></div><button disabled>Invite User</button></div><div className="kdiTableWrap"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Access Status</th><th>Actions</th></tr></thead><tbody>{users.map((user) => <tr key={user.email}><td>{user.email.split("@")[0].replace(/[._-]+/g, " ")}</td><td>{user.email}</td><td>{displayRole(user.role)}</td><td><span className={`kdiStatus ${user.status.toLowerCase().replaceAll(" ", "-")}`}>{user.status}</span></td><td><button disabled>Manage</button></td></tr>)}</tbody></table></div>{!users.length && <p className="kdiTableEmpty">No user records are available.</p>}</section>
  </div>;
}

export function LocalPreviewClient({ catalog, users, adminPreview }: { catalog: Catalog; users: PreviewUser[]; adminPreview: boolean }) {
  const [view, setView] = useState<View>(adminPreview ? "admin" : "search"), [selected, setSelected] = useState<MediaAsset | null>(null), [query, setQuery] = useState(""), [results, setResults] = useState<MediaPage | null>(null), [searching, setSearching] = useState(false), [error, setError] = useState(false), [menu, setMenu] = useState(false);
  const request = useRef<AbortController | null>(null);
  const navigate = (next: View) => { setView(next); setMenu(false); history.replaceState(null, "", next === "search" ? "/dev/library-preview" : `/dev/library-preview#${next}`); };
  async function submit(event: FormEvent) {
    event.preventDefault(); const actualQuery = query.trim(); if (!actualQuery || searching) return;
    request.current?.abort(); request.current = new AbortController(); setSearching(true); setError(false); setResults(null);
    try { const response = await fetch("/api/dev/library-preview/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: actualQuery }), signal: request.current.signal }); const body = await response.json() as SearchResponse; if (!response.ok) throw new Error(body.error || "Search failed"); setResults(body); }
    catch (reason) { if ((reason as Error).name !== "AbortError") setError(true); }
    finally { setSearching(false); }
  }
  const page = view === "all" ? catalog.all : view === "images" ? catalog.images : view === "videos" ? catalog.videos : catalog.documents;
  return <div className="kdiPreviewShell">
    <aside className={menu ? "open" : ""}><div className="kdiLogo"><span>KDI</span><b>KDI Media Library</b></div><nav aria-label="Library navigation"><button className={view === "search" ? "active" : ""} onClick={() => navigate("search")}><i>{icons.search}</i>AI Search</button>{(["all", "images", "videos", "documents"] as const).map((item) => <button key={item} className={view === item ? "active" : ""} onClick={() => navigate(item)}><i>{icons[item]}</i>{viewLabels[item]}</button>)}</nav><div className="kdiAsideBottom">{adminPreview && <button onClick={() => navigate("admin")} className={view === "admin" ? "active" : ""}><i>{icons.admin}</i>Admin Panel</button>}<button><i>{icons.help}</i>Help</button><small>Local read-only preview</small></div></aside>
    {menu && <button className="kdiScrim" onClick={() => setMenu(false)} aria-label="Close menu" />}
    <main><header className="kdiHeader"><button className="kdiMenu" onClick={() => setMenu(true)} aria-label="Open menu">☰</button><a onClick={() => navigate("search")}>KDI Media Library</a><div className="kdiUser"><span>{adminPreview ? "KA" : "KS"}</span><div><b>{adminPreview ? "KDI Admin" : "KDI Staff"}</b><small>{adminPreview ? "Administrator" : "Staff"}</small></div><button aria-label="Account menu">⌄</button></div></header>
      {view === "search" ? <div className="kdiSearchPage"><section className="kdiSearchHero"><h1>Find the file you need</h1><p>Search using natural language. Get exact results.</p><form onSubmit={submit}><label><span className="srOnly">Describe the file you need</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Describe the photo or video you are looking for" maxLength={300} /></label><button disabled={searching || !query.trim()}>{searching ? "Searching…" : "Search"}</button></form><small>Try: male patient discussing hairline design</small></section><section className="kdiSearchOutput">{error ? <div className="kdiEmpty error" role="alert"><h2>Search is temporarily unavailable.</h2><p>Please try again.</p></div> : searching ? <div className="kdiLoading" role="status"><i />Searching the media library…</div> : results ? <Results page={results} search open={setSelected} /> : <div className="kdiWelcome"><span>⌕</span><h2>Describe what you need</h2><p>Search by person, treatment, setting or action.</p></div>}</section></div> : view === "admin" ? <Admin catalog={catalog} users={users} open={setSelected} goAll={() => navigate("all")} /> : <Browse view={view} page={page} open={setSelected} />}
      {selected && <PreviewModal asset={selected} close={() => setSelected(null)} />}
    </main>
  </div>;
}
