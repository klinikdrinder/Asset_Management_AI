/* eslint-disable @next/next/no-img-element */
"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import { isReviewed, type ReviewAsset, type ReviewValidation } from "../../lib/semantic-review/contract";

type Fields = Pick<ReviewAsset, "content_type" | "treatment" | "subject" | "doctor_name" | "ai_description" | "short_caption">;
type RequiredErrors = Partial<Record<"content_type" | "ai_description" | "short_caption", string>>;
type SaveMode = "save" | "save-and-next";

const editableFields = (asset: ReviewAsset): Fields => ({
  content_type: asset.content_type,
  treatment: asset.treatment,
  subject: asset.subject,
  doctor_name: asset.doctor_name,
  ai_description: asset.ai_description,
  short_caption: asset.short_caption,
});

function requiredErrors(fields: Fields): RequiredErrors {
  const errors: RequiredErrors = {};
  if (!fields.content_type.trim()) errors.content_type = "Content type is required.";
  if (!fields.ai_description.trim()) errors.ai_description = "Description is required.";
  if (!fields.short_caption.trim()) errors.short_caption = "Short caption is required.";
  return errors;
}

export function SemanticReviewClient({ initialAssets, initialValidation, contentTypes }: { initialAssets: ReviewAsset[]; initialValidation: ReviewValidation; contentTypes: string[] }) {
  const firstPending = Math.max(5, initialAssets.findIndex((asset, index) => index >= 5 && !asset.reviewed_by));
  const [assets, setAssets] = useState(initialAssets);
  const [selected, setSelected] = useState(firstPending);
  const [draft, setDraft] = useState(() => editableFields(initialAssets[firstPending]));
  const [errors, setErrors] = useState<RequiredErrors>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [mounted, setMounted] = useState(false);
  const [interactiveError, setInteractiveError] = useState("");
  const [validation, setValidation] = useState(initialValidation);
  const [validationOpen, setValidationOpen] = useState(false);
  const [showSeeds, setShowSeeds] = useState(false);
  const [pendingSelection, setPendingSelection] = useState<number | null>(null);

  const asset = assets[selected];
  const candidates = assets.slice(5);
  const reviewed = useMemo(() => candidates.filter(isReviewed).length, [candidates]);
  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(editableFields(asset)), [asset, draft]);
  const isSeed = selected < 5;

  useEffect(() => {
    queueMicrotask(() => setMounted(true));
    const reportError = () => setInteractiveError("A browser runtime error occurred. Refresh the page and try again.");
    window.addEventListener("error", reportError);
    window.addEventListener("unhandledrejection", reportError);
    return () => { window.removeEventListener("error", reportError); window.removeEventListener("unhandledrejection", reportError); };
  }, []);

  function update<K extends keyof Fields>(key: K, value: Fields[K]) {
    setDraft(current => ({ ...current, [key]: value }));
    if (key === "content_type" || key === "ai_description" || key === "short_caption") setErrors(current => ({ ...current, [key]: undefined }));
    setMessage("");
  }

  function selectAsset(index: number) {
    setSelected(index);
    setDraft(editableFields(assets[index]));
    setErrors({});
    setMessage("");
  }

  function requestSelection(index: number) {
    if (index < 0 || index >= assets.length || index === selected) return;
    if (dirty) setPendingSelection(index);
    else selectAsset(index);
  }

  function discardChanges() {
    if (pendingSelection == null) return;
    const destination = pendingSelection;
    setPendingSelection(null);
    selectAsset(destination);
  }

  async function saveCurrentAsset(mode: SaveMode) {
    const nextErrors = requiredErrors(draft);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) { setMessage("Please complete the required fields."); return false; }
    setSaving(true);
    setMessage("");
    try {
      const response = await fetch("/api/dev/semantic-review", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset_id: asset.asset_id, fields: draft }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.error ? `Unable to save: ${body.error}` : "Review save failed. Check the development server.");
      if (!body?.ok || !body?.asset) throw new Error("Review save failed. Check the development server.");
      const updated = assets.map(item => item.asset_id === asset.asset_id ? body.asset as ReviewAsset : item);
      setAssets(updated);
      setDraft(editableFields(body.asset));
      setMessage("✓ Saved");
      if (mode === "save-and-next" && selected < assets.length - 1) {
        const nextIndex = selected + 1;
        setSelected(nextIndex);
        setDraft(editableFields(updated[nextIndex]));
        setErrors({});
      }
      return true;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Review save failed. Check the development server.");
      return false;
    } finally {
      setSaving(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const mode: SaveMode = submitter?.value === "save-and-next" ? "save-and-next" : "save";
    void saveCurrentAsset(mode);
  }

  async function validateAll() {
    setMessage("");
    try {
      const response = await fetch("/api/dev/semantic-review", { method: "POST" });
      const body = await response.json().catch(() => null);
      if (!response.ok || !body) throw new Error(body?.error || "Review validation failed. Check the development server.");
      setValidation(body);
      setValidationOpen(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Review validation failed. Check the development server.");
    }
  }

  return <main className="reviewV2">
    <header className="reviewV2Header">
      <div><h1>KDI Semantic Review</h1><p>Human review only · No AI processing</p></div>
      <div className="reviewV2Progress"><span>Reviewed {reviewed} / 15</span><progress value={reviewed} max={15} /></div>
      <div className="reviewV2HeaderActions"><small>Review UI v2</small><span className={interactiveError ? "error" : mounted ? "ready" : "starting"}>{interactiveError ? "Interactive UI: ERROR" : mounted ? "Interactive UI: READY" : "Interactive UI: STARTING"}</span><button type="button" disabled={saving || !mounted} onClick={() => void validateAll()}>Validate All</button></div>
    </header>

    <div className="reviewV2Workspace">
      <aside className="reviewV2Queue">
        <header><b>File queue</b><span>{15 - reviewed} remaining</span></header>
        <div className="reviewV2QueueScroll">
          {candidates.map((item, offset) => { const index = offset + 5; const current = index === selected; const complete = isReviewed(item); return <button type="button" key={item.asset_id} className={current ? "current" : ""} onClick={() => requestSelection(index)}><i aria-hidden="true">{complete ? "✓" : current ? "●" : "○"}</i><b title={item.filename}>{item.filename}</b><small>{item.media_type}</small></button>; })}
          <section className="reviewV2Seeds"><button type="button" aria-expanded={showSeeds} onClick={() => setShowSeeds(value => !value)}>Existing seeds (5) <span>{showSeeds ? "−" : "+"}</span></button>{showSeeds && assets.slice(0, 5).map((item, index) => <button type="button" className="seed" key={item.asset_id} onClick={() => requestSelection(index)}><i>✓</i><b title={item.filename}>{item.filename}</b><small>read-only</small></button>)}</section>
        </div>
      </aside>

      <section className="reviewV2Preview">
        <header><div><b title={asset.filename}>{asset.filename}</b><span>{asset.media_type === "image" ? "Image" : "Video"} · {isSeed ? "Existing seed" : `Asset ${selected - 4} of 15`}</span></div>{!isSeed && <nav><button type="button" disabled={selected === 5} onClick={() => requestSelection(selected - 1)}>← Previous</button><button type="button" disabled={selected === 19} onClick={() => requestSelection(selected + 1)}>Next →</button></nav>}</header>
        <div className="reviewV2Media">{asset.media_type === "image" ? <img src={`/api/dev/library/media/${asset.asset_id}/preview`} alt={asset.filename} /> : <video src={`/api/dev/library/media/${asset.asset_id}/preview`} controls preload="metadata">Video preview unavailable.</video>}</div>
      </section>

      <form className="reviewV2Form" onSubmit={submit} noValidate>
        <header><div><b>{isSeed ? "Completed seed" : "Review details"}</b><span>{isSeed ? "Read-only benchmark record" : `Reviewer: ${asset.reviewed_by || "Nusaiba"}`}</span></div>{message && <p role="status" className={message.includes("failed") || message.startsWith("Unable") ? "error" : ""}>{message}</p>}</header>
        <div className="reviewV2Fields">
          <label>Content type <em>*</em><select value={draft.content_type} disabled={isSeed || saving} aria-invalid={Boolean(errors.content_type)} onChange={event => update("content_type", event.target.value)}><option value="">Select content type</option>{contentTypes.map(type => <option key={type}>{type}</option>)}</select>{errors.content_type && <span className="fieldError">{errors.content_type}</span>}</label>
          <label>Treatment <small>Optional</small><input value={draft.treatment} disabled={isSeed || saving} onChange={event => update("treatment", event.target.value)} /></label>
          <label>Subject <small>Optional</small><input value={draft.subject} disabled={isSeed || saving} onChange={event => update("subject", event.target.value)} /></label>
          <label>Doctor name <small>Optional</small><input value={draft.doctor_name} disabled={isSeed || saving} onChange={event => update("doctor_name", event.target.value)} /></label>
          <label>Description <em>*</em><textarea rows={6} value={draft.ai_description} disabled={isSeed || saving} aria-invalid={Boolean(errors.ai_description)} onChange={event => update("ai_description", event.target.value)} />{errors.ai_description && <span className="fieldError">{errors.ai_description}</span>}</label>
          <label>Short caption <em>*</em><input value={draft.short_caption} disabled={isSeed || saving} aria-invalid={Boolean(errors.short_caption)} onChange={event => update("short_caption", event.target.value)} />{errors.short_caption && <span className="fieldError">{errors.short_caption}</span>}</label>
        </div>
        {!isSeed && <footer className="reviewV2Actions"><button type="button" className="tertiary" disabled={saving || selected === 19} onClick={() => requestSelection(selected + 1)}>Skip</button><button type="submit" name="mode" value="save" disabled={saving || !mounted}>Save</button><button type="submit" name="mode" value="save-and-next" className="primary" disabled={saving || !mounted}>{saving ? "Saving…" : "Save & Next"}</button></footer>}
      </form>
    </div>

    {pendingSelection != null && <div className="reviewV2ModalBackdrop" role="presentation"><section className="reviewV2Modal" role="dialog" aria-modal="true" aria-labelledby="unsaved-title"><h2 id="unsaved-title">You have unsaved changes.</h2><p>Discard these changes before moving to another file?</p><div><button type="button" onClick={() => setPendingSelection(null)}>Stay</button><button type="button" className="danger" onClick={discardChanges}>Discard changes</button></div></section></div>}
    {validationOpen && <div className="reviewV2ModalBackdrop" role="presentation"><section className="reviewV2Modal validation" role="dialog" aria-modal="true" aria-labelledby="validation-title"><header><div><h2 id="validation-title">Benchmark validation</h2><p>Dry-run only. No records were imported.</p></div><button type="button" aria-label="Close validation" onClick={() => setValidationOpen(false)}>×</button></header><dl><div><dt>Reviewed</dt><dd>{validation.new_reviewed} / 15</dd></div><div><dt>Pending</dt><dd>{validation.pending}</dd></div><div><dt>Valid</dt><dd>{validation.valid}</dd></div><div><dt>Invalid</dt><dd>{validation.invalid}</dd></div><div><dt>Ready for manual import</dt><dd>{validation.ready_for_manual_import ? "YES" : "NO"}</dd></div></dl>{!validation.ready_for_manual_import && <div className="validationPending"><b>Still needs review</b><ul>{validation.entries.filter(entry => entry.status !== "complete").map(entry => <li key={entry.asset_id}><span>{entry.filename}</span><small>{entry.errors.length ? entry.errors.join(" · ") : "Pending review"}</small></li>)}</ul></div>}<footer><button type="button" onClick={() => setValidationOpen(false)}>Close</button></footer></section></div>}
  </main>;
}
