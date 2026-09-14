"""Bounded, resumable production semantic rollout for frozen ordinals 31-130.

Live kdi_search_ready_assets_v1 state is authoritative.  Local evidence and validated Claude
responses are reused; deterministic run/unit identities make persistence retries idempotent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "dashboard"))
OUT = ROOT / "reports/semantic-search/rollout/100"
LOCAL_CHECKPOINT = OUT / "production-rollout-local-checkpoint.json"
FULL_LOCAL_CHECKPOINT = ROOT / "reports/semantic-search/rollout/full/local-preparation-checkpoint.json"
FULL_LOCAL_WORK = ROOT / "reports/semantic-search/rollout/full/local-work"
FULL_LOCAL_WORK = ROOT / "reports/semantic-search/rollout/full/local-work"
STATE = OUT / "production-bulk-state.json"
CACHE = OUT / "claude-stage-cache"
FINAL = OUT / "production-bulk-final-audit.json"
RUN_NAMESPACE = uuid.UUID("0f2c6d84-9b37-4c1e-8a55-71d0e6b4f3a2")
SYSTEMIC = {"CLAUDE_CONFIGURATION", "SCOPE_VIOLATION", "CANONICAL_INVARIANT"}
# Resolved in main() once the environment is loaded.
PROVIDER_NAME = "claude"
PROVIDER_MODEL = ""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_env() -> None:
    chosen = os.environ.get("KDI_SEMANTIC_PROVIDER")
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local", override=False)
    if chosen:
        os.environ["KDI_SEMANTIC_PROVIDER"] = chosen
    os.environ.setdefault("KDI_EXTERNAL_AI_ENABLED", "true")
    if not os.environ.get("KDI_SEMANTIC_PROVIDER"):
        os.environ["KDI_SEMANTIC_PROVIDER"] = "claude"


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def paged(table, columns="*", *, filters=()):
    rows, start, size = [], 0, 1000
    while True:
        query = table.select(columns)
        for method, args in filters:
            query = getattr(query, method)(*args)
        batch = query.range(start, start + size - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < size:
            return rows
        start += size


def frozen_cohort(start: int, end: int) -> dict[int, dict[str, Any]]:
    if start < 31 or end > 881 or start > end:
        raise RuntimeError("SCOPE_VIOLATION: invalid frozen production ordinal range")
    source = LOCAL_CHECKPOINT if end <= 130 else FULL_LOCAL_CHECKPOINT
    data = json.loads(source.read_text(encoding="utf-8"))
    raw_assets = data.get("assets", [])
    values = list(raw_assets.values()) if isinstance(raw_assets, dict) else list(raw_assets)
    assets = sorted((x for x in values if x.get("ordinal") is not None and start <= int(x["ordinal"]) <= end),
                    key=lambda x: int(x["ordinal"]))
    expected = end - start + 1
    if len(assets) != expected or [int(x["ordinal"]) for x in assets] != list(range(start, end + 1)):
        raise RuntimeError(f"SCOPE_VIOLATION: frozen local cohort is not exactly ordinals {start}-{end}")
    if len({x["asset_id"] for x in assets}) != expected:
        raise RuntimeError("SCOPE_VIOLATION: duplicate asset in frozen cohort")
    if any(x.get("checkpoint") not in {"WAITING_EXTERNAL_AI_APPROVAL", "LOCAL_EVIDENCE_COMPLETE"} for x in assets):
        raise RuntimeError("LOCAL_EVIDENCE_NOT_READY")
    return {int(x["ordinal"]): x for x in assets}


def live_ready(client, ids: set[str]) -> set[str]:
    # Keep PostgREST URLs bounded; a single 881-UUID `in` filter exceeds common gateway limits.
    values = sorted(ids)
    rows = []
    for offset in range(0, len(values), 50):
        rows.extend(paged(client.table("kdi_search_ready_assets_v1"), "asset_id,search_ready",
                          filters=(("in_", ("asset_id", values[offset:offset + 50])),)))
    return {str(x["asset_id"]) for x in rows if x.get("search_ready") is True}


class CachedBoundedProvider:
    def __init__(self, semaphore: threading.Semaphore, cache_lock: threading.Lock):
        from kdi_media.semantic_provider_factory import build_semantic_provider
        self.inner = build_semantic_provider()
        self.semaphore = semaphore
        self.cache_lock = cache_lock
        self.usage: list[dict[str, Any]] = []
        self.retry_events: list[dict[str, Any]] = []

    def analyze(self, **kwargs):
        images = list(kwargs.get("images") or [])
        if kwargs.get("image_bytes"):
            images.insert(0, kwargs["image_bytes"])
        digest = hashlib.sha256()
        digest.update(str(kwargs["asset_id"]).encode())
        digest.update(str(kwargs.get("request_type", "asset")).encode())
        digest.update(str(kwargs.get("evidence_text", "")).encode())
        for image in images:
            digest.update(hashlib.sha256(image).digest())
        path = CACHE / kwargs["asset_id"] / (digest.hexdigest() + ".json")
        with self.cache_lock:
            if path.is_file():
                value = json.loads(path.read_text(encoding="utf-8"))
                self.usage.append({"asset_id": kwargs["asset_id"], "request_type": kwargs.get("request_type"),
                                   "cached": True})
                return value
        with self.semaphore:
            value = self.inner.analyze(**kwargs)
        with self.cache_lock:
            atomic_json(path, value)
        self.usage.extend(self.inner.usage[len(self.usage):])
        self.retry_events.extend(self.inner.retry_events)
        return value


class Runtime:
    def __init__(self, cohort, api_n: int, embedding_n: int, db_n: int):
        from sentence_transformers import SentenceTransformer
        from visual_indexing.openclip_encoder import OpenClipEncoder
        snapshots = sorted((Path.home() / ".cache/huggingface/hub/models--intfloat--multilingual-e5-small/snapshots").glob("*"))
        if not snapshots:
            raise RuntimeError("LOCAL_E5_MODEL_MISSING")
        self.e5 = SentenceTransformer(str(snapshots[-1]), local_files_only=True)
        self.clip = OpenClipEncoder()
        self.cohort = cohort
        self.api_sem = threading.Semaphore(api_n)
        self.embedding_sem = threading.Semaphore(embedding_n)
        self.db_sem = threading.Semaphore(db_n)
        self.e5_lock = threading.Lock()
        self.clip_lock = threading.Lock()
        self.cache_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.stop = threading.Event()
        self.usage_limit: str | None = None

    def text(self, value: str) -> list[float]:
        with self.embedding_sem, self.e5_lock:
            return [float(x) for x in self.e5.encode(value, normalize_embeddings=True)]

    def visual(self, path: str) -> list[float]:
        from PIL import Image
        with self.embedding_sem, self.clip_lock, Image.open(path) as image:
            return [float(x) for x in self.clip.embed_image(image)]


def evidence_for(record):
    from kdi_media.production_indexer import SceneEvidence, VideoEvidence
    by_scene = {}
    for frame in record.get("keyframes", []):
        by_scene.setdefault(int(frame["scene_index"]), []).append(str(frame["path"]))
    transcripts = {}
    for chunk in record.get("transcript_chunks", []):
        for scene in record.get("scenes", []):
            if scene["start_seconds"] - 1e-6 <= chunk["start"] and chunk["end"] <= scene["end_seconds"] + 1e-6:
                transcripts.setdefault(int(scene["scene_index"]), []).append(chunk["text"])
                break
    scenes = [SceneEvidence(int(s["scene_index"]), float(s["start_seconds"]), float(s["end_seconds"]),
                            by_scene.get(int(s["scene_index"]), []),
                            list(record.get("ocr_texts", {}).get(str(s["scene_index"]), [])),
                            transcripts.get(int(s["scene_index"]), [])) for s in record.get("scenes", [])]
    return VideoEvidence(record["asset_id"], record["filename"], record.get("technical_probe", {}), scenes,
                         bool(record.get("audio_stream")), "AUDIO_PRESENT" if record.get("audio_stream") else "NO_AUDIO",
                         str(record.get("transcript_state", "UNKNOWN")), bool(record.get("ocr_evaluated")),
                         int(record.get("ocr_observations", 0)))


def media_for(record: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """Returns an already-prepared image/document visual without repeating local preparation."""
    asset_dir = (FULL_LOCAL_WORK / str(record["asset_id"])).resolve()
    source = (asset_dir / str(record["filename"])).resolve()
    if asset_dir not in source.parents or not source.is_file() or not source.stat().st_size:
        raise RuntimeError("LOCAL_PREPARED_MEDIA_MISSING")
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != str(record["checksum"]):
        raise RuntimeError("LOCAL_PREPARED_MEDIA_CHECKSUM_MISMATCH")
    visual_path = source
    if str(record.get("media_type", "")).upper() == "DOCUMENT":
        pages = list(record.get("page_images") or [])
        if not pages:
            raise RuntimeError("LOCAL_PREPARED_DOCUMENT_PAGES_MISSING")
        visual_path = Path(str(pages[0]["path"])).resolve()
        if not visual_path.is_file():
            raise RuntimeError("LOCAL_PREPARED_DOCUMENT_PAGE_MISSING")
        raw = visual_path.read_bytes()
    metadata = {
        "asset_id": record["asset_id"], "filename": record["filename"],
        "media_type": record.get("media_type"), "mime_type": record.get("mime_type"),
        "checksum": record["checksum"], "source_fingerprint": record["checksum"],
        "technical": record.get("technical_probe", {}),
        "ocr_evaluated": bool(record.get("ocr_evaluated")),
        "ocr_observations": int(record.get("ocr_observations", 0)),
        "ocr_texts": record.get("ocr_texts_by_scene", {}),
        "visual_path": str(visual_path),
    }
    return raw, metadata


def media_for(record: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """Returns an already-prepared image/document visual without repeating local preparation."""
    asset_dir = (FULL_LOCAL_WORK / str(record["asset_id"])).resolve()
    source = (asset_dir / str(record["filename"])).resolve()
    if asset_dir not in source.parents or not source.is_file() or not source.stat().st_size:
        raise RuntimeError("LOCAL_PREPARED_MEDIA_MISSING")
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != str(record["checksum"]):
        raise RuntimeError("LOCAL_PREPARED_MEDIA_CHECKSUM_MISMATCH")
    visual_path = source
    if str(record.get("media_type", "")).upper() == "DOCUMENT":
        pages = list(record.get("page_images") or [])
        if not pages:
            raise RuntimeError("LOCAL_PREPARED_DOCUMENT_PAGES_MISSING")
        visual_path = Path(str(pages[0]["path"])).resolve()
        if not visual_path.is_file():
            raise RuntimeError("LOCAL_PREPARED_DOCUMENT_PAGE_MISSING")
        raw = visual_path.read_bytes()
    metadata = {
        "asset_id": record["asset_id"], "filename": record["filename"],
        "media_type": record.get("media_type"), "mime_type": record.get("mime_type"),
        "checksum": record["checksum"], "source_fingerprint": record["checksum"],
        "technical": record.get("technical_probe", {}),
        "ocr_evaluated": bool(record.get("ocr_evaluated")),
        "ocr_observations": int(record.get("ocr_observations", 0)),
        "ocr_texts": record.get("ocr_texts_by_scene", {}),
        "visual_path": str(visual_path),
    }
    return raw, metadata


def cheap_ready(client, asset_id: str) -> tuple[bool, str]:
    ready = client.table("kdi_search_ready_assets_v1").select("asset_id,search_ready").eq("asset_id", asset_id).execute().data or []
    layers = client.table("asset_semantic_layers").select("layer_id,processing_status,active").eq(
        "asset_id", asset_id).eq("active", True).execute().data or []
    docs = client.table("search_document_builds").select("id").eq("asset_id", asset_id).eq(
        "document_type", "ASSET").eq("active", True).eq("stale", False).eq("status", "READY").execute().data or []
    emb = client.table("semantic_embeddings").select("id").eq("asset_id", asset_id).eq(
        "representation_type", "TEXT_ASSET").eq("active", True).eq("stale", False).execute().data or []
    ok = bool(ready and ready[0].get("search_ready") is True and len(layers) == 18 and
              all(x.get("processing_status") == "COMPLETE" for x in layers) and len(docs) == 1 and len(emb) == 1)
    return ok, f"ready={bool(ready and ready[0].get('search_ready'))},layers={len(layers)},asset_docs={len(docs)},text_asset={len(emb)}"


def process_one(runtime: Runtime, record: dict[str, Any], max_attempts: int) -> dict[str, Any]:
    from supabase import create_client
    from kdi_media.claude_code_provider import ClaudeCodeUsageLimitError
    from kdi_media.codex_cli_provider import CodexCliUsageLimitError
    from kdi_media.production_indexer import ProductionSemanticIndexer
    from kdi_media.supabase_production_adapter import CanonicalSemanticPersistenceAdapter, ManifestScope
    started = time.perf_counter()
    asset_id = record["asset_id"]
    result = {"ordinal": int(record["ordinal"]), "asset_id": asset_id, "filename": record["filename"]}
    for attempt in range(1, max_attempts + 1):
        if runtime.stop.is_set():
            if runtime.usage_limit:
                return {**result, "status": "WAITING_FOR_USAGE_RESET",
                        "stage": "CLAUDE_CODE_USAGE_LIMIT", "elapsed_seconds": 0.0}
            return {**result, "status": "BLOCKED", "stage": "SYSTEMIC_STOP"}
        try:
            client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
            if asset_id in live_ready(client, {asset_id}):
                return {**result, "status": "SKIPPED_READY", "elapsed_seconds": round(time.perf_counter()-started, 2)}
            provider = CachedBoundedProvider(runtime.api_sem, runtime.cache_lock)
            scope = ManifestScope(frozenset(x["asset_id"] for x in runtime.cohort.values()), frozenset())
            adapter = CanonicalSemanticPersistenceAdapter(client, scope, text_embedder=runtime.text, visual_embedder=runtime.visual)
            ev = evidence_for(record)
            adapter.evidence_source = lambda _aid, value=ev: value
            adapter.media_source = lambda _aid, value=record: media_for(value)
            adapter.media_source = lambda _aid, value=record: media_for(value)
            run_id = str(uuid.uuid5(RUN_NAMESPACE, f"{asset_id}:{record['checksum']}:kdi_production_indexer_v1"))
            with runtime.db_sem:
                adapter.begin_run({"id": run_id, "asset_id": asset_id, "run_type": "PRODUCTION_SEMANTIC_INDEXING",
                    "status": "RUNNING", "semantic_spec_version": "semantic_index_v1", "ontology_version": "KDI_SEMANTIC_V2",
                    "processor_version": "kdi_production_indexer_v1", "configuration_fingerprint": run_id,
                    "source_fingerprint": record["checksum"], "provider": PROVIDER_NAME, "model": PROVIDER_MODEL,
                    "metadata": {"ordinal": record["ordinal"], "scenes": len(ev.scenes), "keyframes": ev.keyframe_count}})
            outcome = ProductionSemanticIndexer(adapter, provider).index_asset_fully(asset_id)
            ok, detail = cheap_ready(client, asset_id)
            if outcome.get("status") == "SEARCH_READY" and ok:
                return {**result, **outcome, "attempts": attempt, "stage": "SEARCH_READY",
                        "claude_requests": sum(not x.get("cached", False) for x in provider.usage),
                        "rate_limit_retries": sum(x.get("status") == 429 for x in provider.retry_events),
                        "elapsed_seconds": round(time.perf_counter()-started, 2)}
            outcome_detail = str(outcome.get("detail", ""))
            if (PROVIDER_NAME == "codex_cli" and
                    ("Codex subscription allowance reached" in outcome_detail or
                     "hit your usage limit" in outcome_detail.lower())):
                # ProductionSemanticIndexer intentionally converts provider exceptions into an
                # outcome object. Restore the systemic quota signal at the queue boundary so it
                # is never retried or recorded as an asset semantic failure.
                runtime.usage_limit = outcome_detail
                runtime.stop.set()
                return {**result, "status": "WAITING_FOR_USAGE_RESET",
                        "stage": "CODEX_USAGE_LIMIT", "detail": outcome_detail,
                        "attempts": attempt,
                        "elapsed_seconds": round(time.perf_counter()-started, 2)}
            code = outcome.get("code", "READINESS_VALIDATION_FAILED")
            result.update(outcome)
            result.update({"stage": "READINESS", "detail": outcome.get("detail", detail), "attempts": attempt})
            if code in SYSTEMIC:
                runtime.stop.set()
                break
        except (ClaudeCodeUsageLimitError, CodexCliUsageLimitError) as exc:
            # The subscription allowance is exhausted. Stop issuing new inference, keep every
            # completed asset and cached response, and leave this asset cleanly retryable.
            runtime.usage_limit = str(exc)
            runtime.stop.set()
            return {**result, "status": "WAITING_FOR_USAGE_RESET", "stage": "CLAUDE_CODE_USAGE_LIMIT",
                    "detail": str(exc), "attempts": attempt,
                    "elapsed_seconds": round(time.perf_counter()-started, 2)}
        except Exception as exc:
            result.update({"status": "FAILED", "stage": "WORKER", "detail": str(exc), "attempts": attempt})
            if "authentication" in str(exc).lower() or "SCOPE_VIOLATION" in str(exc):
                runtime.stop.set()
                break
        if attempt < max_attempts:
            time.sleep(min(20.0, (2 ** (attempt - 1)) + (int(asset_id[-2:], 16) % 100) / 100))
    if getattr(runtime, "usage_limit", None):
        return {**result, "status": "WAITING_FOR_USAGE_RESET", "stage": "CLAUDE_CODE_USAGE_LIMIT",
                "elapsed_seconds": round(time.perf_counter()-started, 2)}
    return {**result, "status": "BLOCKED" if runtime.stop.is_set() else "FAILED",
            "elapsed_seconds": round(time.perf_counter()-started, 2)}


def audit(client, cohort, processed_ids, before_ready) -> dict[str, Any]:
    ids = {x["asset_id"] for x in cohort.values()}
    assets = paged(client.table("assets"), "id,mime_type")
    sources = paged(client.table("asset_sources"), "asset_id")
    destinations = paged(client.table("asset_destinations"), "asset_id")
    ready_all = paged(client.table("kdi_search_ready_assets_v1"), "asset_id,search_ready")
    ready = {str(x["asset_id"]) for x in ready_all if x.get("search_ready") is True}
    layers = paged(client.table("asset_semantic_layers"), "asset_id,layer_id,active,processing_status,completeness_status")
    scenes = paged(client.table("asset_scenes"), "id,asset_id,scene_index,semantic_version,canonical_active")
    keys = paged(client.table("asset_keyframes"), "id,asset_id,scene_id,frame_index,semantic_version")
    docs = paged(client.table("search_document_builds"), "id,asset_id,document_type,scene_id,event_id,active,stale,status")
    embs = paged(client.table("semantic_embeddings"), "id,asset_id,representation_type,scene_id,event_id,keyframe_id,source_document_fingerprint,metadata,active,stale")
    active_layers = [x for x in layers if x.get("active")]
    current_docs = [x for x in docs if x.get("active") and not x.get("stale")]
    current_embs = [x for x in embs if x.get("active") and not x.get("stale")]
    def duplicates(rows, fields):
        seen, dup = set(), 0
        for row in rows:
            key = tuple(row.get(f) for f in fields)
            dup += key in seen
            seen.add(key)
        return dup
    canonical_scene_ids = {str(x["id"]) for x in scenes if x.get("canonical_active")}
    cohort_assets = {str(x["id"]): str(x.get("mime_type", "")) for x in assets if str(x["id"]) in ids}
    rep = lambda name: sum(x.get("representation_type") == name for x in current_embs)
    cohort_layer_counts = {aid: sum(x.get("asset_id") == aid for x in active_layers) for aid in ids}
    unresolved = [cohort[o] for o in sorted(cohort) if cohort[o]["asset_id"] not in ready or cohort_layer_counts[cohort[o]["asset_id"]] != 18]
    return {"generated_at": utcnow(), "assets": len(assets), "asset_sources": len({x['asset_id'] for x in sources}),
        "asset_destinations": len({x['asset_id'] for x in destinations}), "search_ready": len(ready),
        "active_layers": len(active_layers), "cohort_ready": len(ready & ids), "asset_docs": sum(x.get("document_type")=="ASSET" for x in current_docs),
        "scene_docs": sum(x.get("document_type")=="SCENE" for x in current_docs),
        "event_docs": sum(x.get("document_type")=="EVENT" for x in current_docs),
        "text_asset": rep("TEXT_ASSET"), "ready_videos": sum(a in ready and m.lower().startswith("video") for a,m in cohort_assets.items()),
        "ready_images": sum(a in ready and m.lower().startswith("image") for a,m in cohort_assets.items()),
        "ready_documents": sum(a in ready and not (m.lower().startswith("video") or m.lower().startswith("image")) for a,m in cohort_assets.items()),
        "canonical_scenes": len(canonical_scene_ids), "canonical_keyframes": sum(str(x.get("scene_id")) in canonical_scene_ids for x in keys),
        "text_scene": rep("TEXT_SCENE"), "text_event": rep("TEXT_EVENT"), "text_transcript": rep("TEXT_TRANSCRIPT"), "text_ocr": rep("TEXT_OCR"),
        "duplicate_current_docs": duplicates(current_docs, ("asset_id","document_type","scene_id","event_id")),
        "duplicate_current_embeddings": duplicates(
            [{**x, "natural_source_unit": ((x.get("metadata") or {}).get("source_unit_id") or
                                             x.get("keyframe_id") or x.get("source_document_fingerprint"))}
             for x in current_embs],
            ("asset_id","representation_type","scene_id","event_id","keyframe_id","natural_source_unit")),
        "active_stale_embeddings": sum(x.get("active") and x.get("stale") for x in embs),
        "out_of_scope_processed": len(set(processed_ids)-ids), "original_ready_assets_preserved": before_ready <= ready,
        "unresolved_assets": [{"ordinal": x["ordinal"], "asset_id": x["asset_id"], "filename": x["filename"]} for x in unresolved]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ordinal-start", type=int, default=31); p.add_argument("--ordinal-end", type=int, default=130)
    p.add_argument("--concurrency", type=int, default=int(os.getenv("KDI_SEMANTIC_CONCURRENCY", "4")))
    p.add_argument("--api-concurrency", type=int, default=int(os.getenv("KDI_CLAUDE_CONCURRENCY", "4")))
    p.add_argument("--embedding-concurrency", type=int, default=int(os.getenv("KDI_EMBEDDING_CONCURRENCY", "2")))
    p.add_argument("--db-concurrency", type=int, default=int(os.getenv("KDI_DB_CONCURRENCY", "4")))
    p.add_argument("--max-attempts", type=int, default=3); p.add_argument("--resume", action="store_true")
    p.add_argument("--only-not-ready", action="store_true"); p.add_argument("--preflight", action="store_true")
    p.add_argument("--provider", choices=("claude", "claude_code", "codex_cli"), default=None,
                   help="semantic inference transport; overrides KDI_SEMANTIC_PROVIDER")
    p.add_argument("--limit", type=int, default=0,
                   help="process at most N pending assets from the front of the range")
    args = p.parse_args()
    if not args.only_not_ready: raise RuntimeError("ONLY_NOT_READY_REQUIRED")
    if args.provider:
        os.environ["KDI_SEMANTIC_PROVIDER"] = args.provider
    load_env()
    global PROVIDER_NAME, PROVIDER_MODEL
    from kdi_media.semantic_provider_factory import resolve_provider_name
    PROVIDER_NAME = resolve_provider_name()
    PROVIDER_MODEL = (os.getenv("KDI_CLAUDE_CODE_MODEL", "sonnet") if PROVIDER_NAME == "claude_code"
                      else os.getenv("KDI_CODEX_MODEL", "codex-default") if PROVIDER_NAME == "codex_cli"
                      else os.getenv("KDI_CLAUDE_MODEL", ""))
    from supabase import create_client
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    cohort = frozen_cohort(args.ordinal_start, args.ordinal_end); ids = {x["asset_id"] for x in cohort.values()}
    ready_before_all = live_ready(client, {str(x["id"]) for x in paged(client.table("assets"), "id")})
    ready_before_cohort = live_ready(client, ids)
    pending = [cohort[o] for o in sorted(cohort) if cohort[o]["asset_id"] not in ready_before_cohort]
    if args.limit:
        pending = pending[:args.limit]
    layers_before = len(paged(client.table("asset_semantic_layers"), "id", filters=(("eq", ("active", True)),)))
    preflight = {"TOTAL_ASSETS": len(paged(client.table("assets"), "id")), "SEARCH_READY_BEFORE": len(ready_before_all),
        "ACTIVE_LAYERS_BEFORE": layers_before, "TARGET_RANGE": f"{args.ordinal_start}-{args.ordinal_end}", "TARGET_TOTAL": len(cohort),
        "TARGET_READY": len(ready_before_cohort), "TARGET_PENDING": len(pending), "CONCURRENCY": args.concurrency,
        "scope_guard": True, "clinical_guard": True, "canonical_active_scene_handling": True,
        "semantic_provider": PROVIDER_NAME, "provider_model": PROVIDER_MODEL,
        "anthropic_api_used": PROVIDER_NAME == "claude",
        "openai_api_used": False, "claude_code_used": PROVIDER_NAME == "claude_code"}
    print(json.dumps({"preflight": preflight}), flush=True)
    if args.preflight: return
    runtime = Runtime(cohort, args.api_concurrency, args.embedding_concurrency, args.db_concurrency)
    started = time.perf_counter(); results = []; total = len(pending)
    with ThreadPoolExecutor(max_workers=args.concurrency, thread_name_prefix="kdi-semantic") as pool:
        futures = {pool.submit(process_one, runtime, row, args.max_attempts): row for row in pending}
        for future in as_completed(futures):
            row = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                # One asset-specific worker failure is data, never a reason to abandon the queue.
                result = {"ordinal": int(row["ordinal"]), "asset_id": row["asset_id"],
                          "filename": row["filename"], "status": "FAILED",
                          "stage": "UNCAUGHT_WORKER", "detail": str(exc), "elapsed_seconds": 0.0}
            results.append(result); n = len(results)
            print(f"[{n}/{total}] ordinal={result['ordinal']} filename={result['filename']} {result['status']} stage={result.get('stage')} elapsed={result.get('elapsed_seconds')}", flush=True)
            atomic_json(STATE, {"status":"RUNNING", "updated_at":utcnow(), "preflight":preflight, "results":results})
            if n % 10 == 0:
                durations=[x["elapsed_seconds"] for x in results]; success=sum(x["status"]=="SEARCH_READY" for x in results)
                elapsed=time.perf_counter()-started
                print(json.dumps({"progress":{"completed":success,"failed":sum(x["status"]=="FAILED" for x in results),
                    "retrying":sum(x.get("attempts",1)>1 and x["status"]!="SEARCH_READY" for x in results),"remaining":total-n,
                    "average_seconds_per_asset":round(statistics.mean(durations),2),"effective_assets_per_minute":round(success/max(elapsed,1)*60,2),
                    "concurrency":args.concurrency}}), flush=True)
            if n % 40 == 0:
                periodic = audit(client, cohort, [x["asset_id"] for x in results], ready_before_all)
                print(json.dumps({"periodic_audit": {k: periodic[k] for k in (
                    "search_ready", "active_layers", "asset_docs", "text_asset",
                    "duplicate_current_docs", "duplicate_current_embeddings",
                    "active_stale_embeddings", "out_of_scope_processed")}}), flush=True)
    elapsed=time.perf_counter()-started
    final_audit=audit(client, cohort, [x["asset_id"] for x in results], ready_before_all)
    durations=[x["elapsed_seconds"] for x in results if x["status"]=="SEARCH_READY"]
    final_audit.update({"bulk_worker":str(Path(__file__)),"concurrency":args.concurrency,"preflight":preflight,
        "processed":len(results),"newly_search_ready":sum(x["status"]=="SEARCH_READY" for x in results),
        "failed":sum(x["status"]=="FAILED" for x in results),"blocked":sum(x["status"]=="BLOCKED" for x in results),
        "median_seconds_per_new_asset":round(statistics.median(durations),2) if durations else None,
        "p90_seconds_per_new_asset":round(sorted(durations)[max(0, int(len(durations)*.9)-1)],2) if durations else None,
        "total_wall_clock_seconds":round(elapsed,2),"effective_assets_per_minute":round(sum(x["status"]=="SEARCH_READY" for x in results)/max(elapsed,1)*60,2),
        "waiting_for_usage_reset":sum(x["status"]=="WAITING_FOR_USAGE_RESET" for x in results),
        "semantic_provider":PROVIDER_NAME,"provider_model":PROVIDER_MODEL,
        "anthropic_api_used":PROVIDER_NAME == "claude", "openai_api_used":False,
        "claude_code_used":PROVIDER_NAME == "claude_code",
        "claude_code_usage_limit_hit":bool(getattr(runtime, "usage_limit", None)),
        "claude_code_usage_limit_detail":getattr(runtime, "usage_limit", None),
        "codex_usage_limit_hit":bool(getattr(runtime, "usage_limit", None)) and PROVIDER_NAME == "codex_cli",
        "codex_usage_limit_detail":getattr(runtime, "usage_limit", None) if PROVIDER_NAME == "codex_cli" else None,
        "errors":[x for x in results if x["status"] not in {"SEARCH_READY","SKIPPED_READY"}]})
    bounded = bool(args.limit)
    passed = (bounded or final_audit["search_ready"] == args.ordinal_end) and (
             bounded or final_audit["active_layers"] == args.ordinal_end * 18 and final_audit["cohort_ready"] == len(cohort)
              and not final_audit["unresolved_assets"]) and (final_audit["duplicate_current_docs"] == 0
              and final_audit["duplicate_current_embeddings"] == 0 and final_audit["active_stale_embeddings"] == 0
              and final_audit["out_of_scope_processed"] == 0 and final_audit["original_ready_assets_preserved"])
    final_audit["status"] = "PASS" if passed else "BLOCKED"
    atomic_json(FINAL, final_audit); atomic_json(STATE, {"status":final_audit["status"],"results":results})
    print(json.dumps({"final":final_audit}), flush=True)
    if not passed: raise SystemExit(2)


if __name__ == "__main__": main()
