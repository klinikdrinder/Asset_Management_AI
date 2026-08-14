import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";
import type { ReviewAsset, ReviewValidation } from "../app/lib/semantic-review/contract";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://127.0.0.1:3000/dev/semantic-review" });
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  HTMLElement: dom.window.HTMLElement,
  HTMLButtonElement: dom.window.HTMLButtonElement,
  Node: dom.window.Node,
  Event: dom.window.Event,
  SubmitEvent: dom.window.SubmitEvent,
  MutationObserver: dom.window.MutationObserver,
  getComputedStyle: dom.window.getComputedStyle,
  IS_REACT_ACT_ENVIRONMENT: true,
});
Object.defineProperty(globalThis, "navigator", { value: dom.window.navigator, configurable: true });

const manifest = JSON.parse(readFileSync("../data/semantic_manual_benchmark_20.json", "utf8")) as { assets: ReviewAsset[] };
const pendingAssets = manifest.assets.map((asset,index)=>index<5?asset:{...asset,content_type:"",treatment:"",subject:"",doctor_name:"",ai_description:"",short_caption:"",reviewed_by:"",reviewed_at:"",description_provider:undefined,description_model:undefined,description_version:undefined});
const initialValidation: ReviewValidation = { existing_complete: 5, new_reviewed: 0, pending: 15, valid: 0, invalid: 0, ready_for_manual_import: false, entries: pendingAssets.slice(5).map(asset => ({ asset_id: asset.asset_id, filename: asset.filename, status: "incomplete", errors: [] })) };
const contentTypes = ["Other", "Clinic Environment"];
const saved = (asset: ReviewAsset) => ({ ...asset, content_type: "Other", ai_description: "Fixture description.", short_caption: "Fixture caption.", reviewed_by: "Nusaiba", reviewed_at: "2026-08-11T13:00:00+08:00" });

test("mounted client validates, saves, advances, validates all, and protects dirty navigation", async () => {
  const React = await import("react");
  const { cleanup, render, screen, waitFor } = await import("@testing-library/react");
  const userEvent = (await import("@testing-library/user-event")).default;
  const { SemanticReviewClient } = await import("../app/dev/semantic-review/semantic-review-client");
  const requests: { method: string; body?: string }[] = [];
  let saveIndex = 5;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    const method = init?.method || "GET";
    requests.push({ method, body: typeof init?.body === "string" ? init.body : undefined });
    if (method === "POST") return new Response(JSON.stringify(initialValidation), { status: 200, headers: { "Content-Type": "application/json" } });
    const asset = saved(pendingAssets[saveIndex++]);
    return new Response(JSON.stringify({ ok: true, asset_id: asset.asset_id, reviewed: true, progress: { reviewed: saveIndex - 5, remaining: 20 - saveIndex }, asset }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  const user = userEvent.setup({ document: dom.window.document });
  render(React.createElement(SemanticReviewClient, { initialAssets: structuredClone(pendingAssets), initialValidation, contentTypes }));
  await screen.findByText("Interactive UI: READY");
  await user.click(screen.getByRole("button", { name: /^Save$/ }));
  assert.equal(requests.length, 0);
  assert.ok(screen.getByText("Content type is required."));
  assert.ok(screen.getByText("Description is required."));
  assert.ok(screen.getByText("Short caption is required."));
  await user.selectOptions(screen.getByLabelText(/Content type/), "Other");
  await user.type(screen.getByLabelText(/Description/), "Fixture description.");
  await user.type(screen.getByLabelText(/Short caption/), "Fixture caption.");
  await user.click(screen.getByRole("button", { name: /^Save$/ }));
  await screen.findByText("✓ Saved");
  assert.equal(requests[0].method, "PATCH");
  assert.equal(JSON.parse(requests[0].body!).asset_id, manifest.assets[5].asset_id);
  await user.click(screen.getByRole("button", { name: "Next →" }));
  await user.selectOptions(screen.getByLabelText(/Content type/), "Other");
  await user.type(screen.getByLabelText(/Description/), "Fixture description.");
  await user.type(screen.getByLabelText(/Short caption/), "Fixture caption.");
  await user.click(screen.getByRole("button", { name: "Save & Next" }));
  await waitFor(() => assert.ok(screen.getByText(/Asset 3 of 15/)));
  assert.equal(requests[1].method, "PATCH");
  await user.type(screen.getByLabelText(/Treatment/), "Unsaved fixture edit");
  await user.click(screen.getByRole("button", { name: "Next →" }));
  assert.ok(screen.getByRole("dialog", { name: "You have unsaved changes." }));
  await user.click(screen.getByRole("button", { name: "Stay" }));
  await user.click(screen.getByRole("button", { name: "Validate All" }));
  assert.ok(await screen.findByRole("dialog", { name: "Benchmark validation" }));
  assert.equal(requests[2].method, "POST");
  cleanup();
});

test("save API failure remains visible and does not advance", async () => {
  const React = await import("react");
  const { cleanup, render, screen } = await import("@testing-library/react");
  const userEvent = (await import("@testing-library/user-event")).default;
  const { SemanticReviewClient } = await import("../app/dev/semantic-review/semantic-review-client");
  globalThis.fetch = (async () => new Response(JSON.stringify({ ok: false, error: "fixture persistence failed" }), { status: 500, headers: { "Content-Type": "application/json" } })) as typeof fetch;
  const assets = structuredClone(pendingAssets);assets[5] = { ...assets[5], content_type: "Other", ai_description: "Fixture description.", short_caption: "Fixture caption." };
  const user = userEvent.setup({ document: dom.window.document });
  render(React.createElement(SemanticReviewClient, { initialAssets: assets, initialValidation, contentTypes }));
  await screen.findByText("Interactive UI: READY");
  await user.click(screen.getByRole("button", { name: "Save & Next" }));
  assert.ok(await screen.findByText("Unable to save: fixture persistence failed"));
  assert.ok(screen.getByText(/Asset 1 of 15/));
  cleanup();
});
