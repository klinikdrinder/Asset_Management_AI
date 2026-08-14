/* eslint-disable @next/next/no-img-element */
"use client";
import { useState } from "react";

// The grid never receives a Google Drive URL - only an internal
// /api/media/{assetId}/thumbnail (or dev equivalent) URL. This component
// only owns the loading/loaded/error presentation states around that
// request: the glyph behind it (rendered by the parent) is the loading
// placeholder and the permanent fallback for a genuine failed response.
// Give this a `key={src}` from the parent so a changed asset/thumbnail URL
// always starts a fresh request instead of keeping a stale failure.
export function AssetThumbnail({ src, alt }: { src: string; alt: string }) {
  const [state, setState] = useState<"loading" | "loaded" | "error">("loading");
  if (state === "error") return null;
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      decoding="async"
      className={`assetThumb${state === "loaded" ? " thumbLoaded" : ""}`}
      onLoad={() => setState("loaded")}
      onError={() => setState("error")}
    />
  );
}
