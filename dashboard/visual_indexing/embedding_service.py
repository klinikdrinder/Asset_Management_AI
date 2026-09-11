"""Warm query-embedding sidecar for KDI semantic search.

One long-running process that holds BOTH query encoders in memory so the Next.js
search path never spawns Python (it can't on Cloudflare Workers) and never pays a
cold model load per request:

  - intfloat/multilingual-e5-small  -> 384d text vectors ("query: " prefix, L2)
  - OpenCLIP ViT-B-32 text tower    -> 512d visual-space vectors (L2)

POST /embed {"texts": ["..."]} -> {"e5": [[384]...], "openclip": [[512]...], ...}

Deploy in ap-southeast-1 next to the DB; the Worker calls it over HTTP. Loopback
in dev (npm run search:embed-service). Cache is keyed on the normalised query
text, so repeated queries skip the model entirely. This service embeds QUERIES
only (no asset content leaves the box); it holds no credentials and does no I/O
beyond the model files already in the local HuggingFace cache.
"""
from __future__ import annotations

import glob
import math
import os
import threading
from collections import OrderedDict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .openclip_encoder import (
    OpenClipEncoder,
    MODEL_NAME as CLIP_MODEL,
    MODEL_PROVIDER as CLIP_PROVIDER,
    MODEL_VERSION as CLIP_VERSION,
    DIMENSIONS as CLIP_DIMS,
)

# Model identities MUST match what was written at index time; the retriever
# rejects vectors whose identity does not match (assertEmbeddingCompatibility).
E5_PROVIDER = "sentence_transformers"
E5_MODEL = "intfloat/multilingual-e5-small"
E5_MODEL_VERSION = "hf-main-pinned-runtime-v1"
E5_DIMS = 384

MAX_CHARS = 300
MAX_BATCH = 32
CACHE_CAPACITY = int(os.getenv("KDI_EMBED_CACHE", "2048"))


def _normalise(text: str) -> str:
    return " ".join(str(text).split())[:MAX_CHARS]


class _Lru:
    """Tiny thread-safe LRU keyed on normalised query text."""

    def __init__(self, capacity: int) -> None:
        self._cap = max(0, capacity)
        self._store: "OrderedDict[str, list[float]]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        if self._cap == 0:
            return None
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self.hits += 1
                return self._store[key]
            self.misses += 1
            return None

    def put(self, key: str, value: list[float]) -> None:
        if self._cap == 0:
            return
        with self._lock:
            self._store[key] = value
            self._store.move_to_end(key)
            while len(self._store) > self._cap:
                self._store.popitem(last=False)


class _E5Encoder:
    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        snaps = glob.glob(
            os.path.expanduser(
                "~/.cache/huggingface/hub/models--intfloat--multilingual-e5-small/snapshots/*"
            )
        )
        if not snaps:
            raise RuntimeError(f"LOCAL_MODEL_UNAVAILABLE: {E5_MODEL}")
        self._model = SentenceTransformer(sorted(snaps)[-1], local_files_only=True)
        self._lock = threading.Lock()

    def embed(self, normalised: list[str]) -> list[list[float]]:
        # e5 requires the "query: " prefix for query-side text. Serialised to
        # avoid BLAS thread contention with the CLIP tower on a shared CPU host.
        with self._lock:
            vectors = self._model.encode(
                ["query: " + t for t in normalised], normalize_embeddings=True
            ).tolist()
        for v in vectors:
            if len(v) != E5_DIMS or not all(math.isfinite(x) for x in v):
                raise RuntimeError("INVALID_E5_VECTOR")
        return vectors


app = FastAPI(docs_url=None, redoc_url=None, title="kdi-query-embeddings")

_e5: _E5Encoder | None = None
_clip: OpenClipEncoder | None = None
_clip_lock = threading.Lock()
_e5_cache = _Lru(CACHE_CAPACITY)
_clip_cache = _Lru(CACHE_CAPACITY)


def _get_e5() -> _E5Encoder:
    global _e5
    if _e5 is None:
        _e5 = _E5Encoder()
    return _e5


def _get_clip() -> OpenClipEncoder:
    global _clip
    if _clip is None:
        _clip = OpenClipEncoder()
    return _clip


def _embed_e5(normalised: list[str]) -> list[list[float]]:
    out: list[list[float] | None] = [_e5_cache.get(t) for t in normalised]
    misses = [i for i, v in enumerate(out) if v is None]
    if misses:
        fresh = _get_e5().embed([normalised[i] for i in misses])
        for i, vec in zip(misses, fresh):
            _e5_cache.put(normalised[i], vec)
            out[i] = vec
    return [v for v in out if v is not None]


def _embed_clip(normalised: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for t in normalised:
        cached = _clip_cache.get(t)
        if cached is None:
            with _clip_lock:
                cached = _get_clip().embed_text(t)
            _clip_cache.put(t, cached)
        out.append(cached)
    return out


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=MAX_BATCH)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "e5": {"provider": E5_PROVIDER, "model": E5_MODEL, "version": E5_MODEL_VERSION, "dimensions": E5_DIMS},
        "openclip": {"provider": CLIP_PROVIDER, "model": CLIP_MODEL, "version": CLIP_VERSION, "dimensions": CLIP_DIMS},
        "cache": {
            "capacity": CACHE_CAPACITY,
            "e5": {"hits": _e5_cache.hits, "misses": _e5_cache.misses},
            "openclip": {"hits": _clip_cache.hits, "misses": _clip_cache.misses},
        },
        "device": "cpu",
    }


@app.post("/embed")
def embed(request: EmbedRequest):
    normalised = [_normalise(t) for t in request.texts]
    if any(not t for t in normalised):
        raise HTTPException(422, "QUERY_EMBEDDING_EMPTY_TEXT")
    try:
        e5 = _embed_e5(normalised)
        openclip = _embed_clip(normalised)
    except Exception as exc:  # noqa: BLE001 - surface a stable error to the caller
        raise HTTPException(500, f"QUERY_EMBEDDING_FAILED:{exc}") from exc
    return {
        "e5": e5,
        "openclip": openclip,
        "provenance": {
            "e5": {"provider": E5_PROVIDER, "model": E5_MODEL, "model_version": E5_MODEL_VERSION,
                   "dimension": E5_DIMS, "preprocessing": "query: prefix + L2 normalization"},
            "openclip": {"provider": CLIP_PROVIDER, "model": CLIP_MODEL, "checkpoint": CLIP_VERSION,
                         "dimension": CLIP_DIMS, "preprocessing": "OpenCLIP tokenizer + L2 normalization"},
        },
    }
