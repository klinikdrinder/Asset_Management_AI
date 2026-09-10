"""Local preparation for the whole 881-asset library, stopping at the privacy gate.

Rollout order is now: finish every stage that can run locally for every asset, and defer all
external Claude work until the human privacy review. This worker takes assets to
LOCAL_EVIDENCE_COMPLETE and no further.

    prepare     acquire, verify checksum, probe, scene detection, keyframes, audio, OCR
    transcript  local faster-whisper over audio-bearing videos (separate process: CTranslate2
                and PyTorch cannot share one)
    visual      OpenCLIP 512D vectors and canonical persistence of the local evidence
    reconcile   the library-wide reconciliation report

Scope: ordinals #31-#880 of the frozen manifest. Assets #1-#30 are certified and untouched; the
one unsupported file is excluded by the manifest itself. `prepare` skips #31-#130 because their
local acquisition already completed; `visual` covers them so the whole library reaches the same
state. Nothing here calls Claude, and no access-control row is ever written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FULL = ROOT / "reports/semantic-search/rollout/full"
MANIFEST = FULL / "kdi_local_preparation_manifest_v1.json"
CHECKPOINT = FULL / "local-preparation-checkpoint.json"
RECONCILIATION = FULL / "local-preparation-reconciliation.json"
WORKROOT = FULL / "local-work"
FROZEN_CHECKPOINT = ROOT / "reports/semantic-search/rollout/100/production-rollout-local-checkpoint.json"
FROZEN_WORK = ROOT / "reports/semantic-search/rollout/100/local-work"
FF = str(ROOT / ".tools/ffmpeg/bin/ffmpeg.exe")
FP = str(ROOT / ".tools/ffmpeg/bin/ffprobe.exe")
RUN_NAMESPACE = uuid.UUID("3d7e51a6-2c94-4f18-9b60-5a4c7e2f8d13")
FIRST_NEW_ORDINAL = 131


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path: Path, payload: Any) -> None:
    """Atomic checkpoint write, retried around transient Windows file locks.

    os.replace fails with WinError 32 whenever anything else - a scanner, an indexer, a reader -
    holds the target for even a moment. Losing a multi-hour run to that is not acceptable, so the
    swap is retried briefly before giving up.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    for attempt in range(10):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.5 * (attempt + 1))


def manifest_assets() -> list[dict[str, Any]]:
    data = read_json(MANIFEST, None)
    if not data:
        raise RuntimeError("MANIFEST_MISSING: run scripts/build_full_local_manifest.py first")
    assets = data["assets"]
    if any(x["ordinal"] < 31 for x in assets):
        raise RuntimeError("OUT_OF_SCOPE_ASSET: manifest reaches into the certified cohort")
    return sorted(assets, key=lambda x: x["ordinal"])


def state() -> dict[str, Any]:
    return read_json(CHECKPOINT, {"status": "RUNNING", "assets": {}})


def local_run_id(asset_id: str, checksum: str) -> str:
    return str(uuid.uuid5(RUN_NAMESPACE, f"{asset_id}:{checksum}:kdi_local_preparation_v1"))


# ------------------------------------------------------------------- acquisition
def drive_client():
    """Drive reader with a bounded socket timeout.

    httplib2 has no timeout by default, so a stalled transfer can block the whole run
    indefinitely - one asset in the first pass held the worker for 28 minutes. A bounded
    timeout turns that into a fast, retryable failure instead.
    """
    import socket
    socket.setdefaulttimeout(120)
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    credentials = os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH") or str(ROOT / ".secrets/kdi-media-reader.json")
    return build("drive", "v3", cache_discovery=False,
                 credentials=service_account.Credentials.from_service_account_file(
                     credentials, scopes=["https://www.googleapis.com/auth/drive.readonly"]))


def download(drive, file_id: str, target: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload
    with target.open("wb") as handle:
        loader = MediaIoBaseDownload(handle, drive.files().get_media(fileId=file_id, supportsAllDrives=True),
                                     chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            _, done = loader.next_chunk(num_retries=3)


def probe_video(path: Path) -> dict[str, Any]:
    raw = json.loads(subprocess.run([FP, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                                    capture_output=True, text=True, check=True, timeout=180).stdout)
    streams = raw.get("streams", [])
    video = next((x for x in streams if x.get("codec_type") == "video"), {})
    audio = next((x for x in streams if x.get("codec_type") == "audio"), {})
    return {"duration_seconds": float((raw.get("format") or {}).get("duration") or 0),
            "width": video.get("width"), "height": video.get("height"),
            "fps": video.get("avg_frame_rate"), "codec": video.get("codec_name"),
            "audio_stream": bool(audio), "audio_codec": audio.get("codec_name"),
            "sample_rate_hz": int(audio["sample_rate"]) if audio.get("sample_rate") else None,
            "rotation_degrees": int((video.get("tags") or {}).get("rotate", 0) or 0),
            "format_name": (raw.get("format") or {}).get("format_name"),
            "file_size_bytes": path.stat().st_size,
            "decoded_locally": True}


def probe_image(path: Path) -> dict[str, Any]:
    from PIL import Image, ImageFile
    truncated = False
    try:
        with Image.open(path) as image:
            image.verify()
    except OSError as exc:
        if "Truncated File Read" not in str(exc):
            raise
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        truncated = True
    with Image.open(path) as image:
        image.load()
        return {"width": image.width, "height": image.height, "format": image.format,
                "file_size_bytes": path.stat().st_size, "decoded_locally": True,
                "truncated_source_tolerated": truncated}


def bounded_ocr_input(image):
    """Bound OCR memory and retain coordinates in the original image space."""
    import numpy
    source = image.convert("RGB")
    width, height = source.size
    scale = min(1.0, 4096 / max(width, height),
                (12_000_000 / max(1, width * height)) ** 0.5)
    if scale < 1.0:
        source = source.resize((max(1, round(width * scale)), max(1, round(height * scale))))
    return numpy.array(source), scale


def rasterise_pdf(path: Path, folder: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Render each PDF page to a JPEG so a document yields the same local evidence as an image.

    A document has no timeline, so it gets no scenes and no keyframes; the pages are OCR and
    visual-embedding inputs only, pooled into a single VISUAL_ASSET vector.
    """
    import pypdfium2
    pages = []
    document = pypdfium2.PdfDocument(str(path))
    try:
        for index in range(len(document)):
            target = folder / f"page-{index:03d}.jpg"
            image = document[index].render(scale=2).to_pil().convert("RGB")
            image.save(target, "JPEG", quality=85)
            pages.append({"page_index": index, "path": str(target),
                          "width": image.width, "height": image.height})
    finally:
        document.close()
    if not pages:
        raise RuntimeError("NO_RENDERABLE_PDF_PAGES")
    return {"pages": len(pages), "width": pages[0]["width"], "height": pages[0]["height"],
            "format": "PDF", "decoded_locally": True}, pages


def cuts(path: Path, duration: float) -> list[float]:
    if duration < 2:
        return []
    result = subprocess.run([FF, "-v", "info", "-i", str(path), "-filter:v",
                             "select='gt(scene,0.35)',showinfo", "-f", "null", "-"],
                            capture_output=True, text=True, timeout=900)
    return sorted({round(float(x), 3) for x in re.findall(r"pts_time:([0-9.]+)", result.stderr or "")
                   if 0.4 < float(x) < duration - 0.4})


def extract_scenes(path: Path, duration: float, folder: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Content-driven scene boundaries and their representative keyframes."""
    bounds = [0.0] + cuts(path, duration) + [max(duration, 0.001)]
    scenes, keyframes = [], []
    for index in range(len(bounds) - 1):
        start, end = bounds[index], bounds[index + 1]
        span = end - start
        scenes.append({"scene_index": index, "start_seconds": start, "end_seconds": end})
        points = [start + span * 0.5] if span < 4 else [start + span * 0.25, start + span * 0.75]
        for frame_index, timestamp in enumerate(points):
            target = folder / f"scene-{index:03d}-frame-{frame_index:02d}.jpg"
            subprocess.run([FF, "-ss", f"{timestamp:.3f}", "-i", str(path), "-frames:v", "1",
                            "-q:v", "4", "-y", str(target)], capture_output=True, timeout=300)
            if target.is_file() and target.stat().st_size:
                keyframes.append({"scene_index": index, "frame_index": frame_index,
                                  "timestamp": round(timestamp, 3), "path": str(target)})
    return scenes, keyframes


def in_scope(record: dict[str, Any], through: int) -> bool:
    return 31 <= int(record.get("ordinal", -1)) <= through


def prepare_stage(limit: int | None, only: set[int] | None = None, through: int = 880) -> dict[str, Any]:
    """Acquire and locally decode assets #131 onward. Nothing leaves the machine."""
    assets = [x for x in manifest_assets() if FIRST_NEW_ORDINAL <= x["ordinal"] <= through
              and (only is None or x["ordinal"] in only)]
    data = state()
    records: dict[str, Any] = data.setdefault("assets", {})
    pending = [x for x in assets if records.get(x["asset_id"], {}).get("checkpoint") not in
               {"LOCAL_EVIDENCE_COMPLETE", "OCR_COMPLETE", "TRANSCRIBED", "PERSISTED"}]
    if limit:
        pending = pending[:limit]
    if not pending:
        return {"stage": "prepare", "pending": 0}

    try:
        import easyocr
        reader = easyocr.Reader(["en"], gpu=False,
                                model_storage_directory=str(ROOT / "tmp/phase7_easyocr_models"),
                                user_network_directory=str(ROOT / "tmp/phase7_easyocr_models"),
                                verbose=False, download_enabled=False)
        ocr_error = None
    except Exception as exc:  # a missing local OCR model is a real stage failure, never a silent pass
        reader, ocr_error = None, str(exc)

    drive = drive_client()
    WORKROOT.mkdir(parents=True, exist_ok=True)
    processed = 0
    for item in pending:
        asset_id = item["asset_id"]
        started = time.perf_counter()
        work = WORKROOT / asset_id
        work.mkdir(parents=True, exist_ok=True)
        media = work / item["filename"]
        record = {**item, "started_at": now(), "external_ai_calls": 0}
        try:
            if not (media.is_file() and media.stat().st_size):
                references = [item.get("destination_reference"), item.get("source_master_reference")]
                errors = []
                for reference in [x for x in references if x]:
                    try:
                        download(drive, reference, media)
                        break
                    except Exception as exc:
                        errors.append(f"{reference}: {type(exc).__name__}")
                else:
                    raise RuntimeError("MEDIA_UNREACHABLE:" + "; ".join(errors or ["no reference"]))
            digest = hashlib.sha256(media.read_bytes()).hexdigest()
            if digest != item["checksum"]:
                raise RuntimeError("MASTER_HASH_MISMATCH")
            record["checksum_verified"] = True
            record["checkpoint"] = "ACQUIRED"

            kind = item["media_type"]
            pages: list[dict[str, Any]] = []
            if kind == "VIDEO":
                technical = probe_video(media)
            elif kind == "IMAGE":
                technical = probe_image(media)
            elif kind == "DOCUMENT":
                technical, pages = rasterise_pdf(media, work)
            else:
                raise RuntimeError(f"NO_LOCAL_DECODER_FOR_MEDIA_TYPE:{kind}")
            record["technical_probe"] = technical
            record["page_images"] = pages
            record["checkpoint"] = "PROBED"

            if kind == "VIDEO":
                scenes, keyframes = extract_scenes(media, float(technical["duration_seconds"]), work)
                if not scenes or not keyframes:
                    raise RuntimeError("NO_DECODABLE_VIDEO_FRAMES")
                record["audio_stream"] = bool(technical["audio_stream"])
                record["transcript_state"] = "PENDING_LOCAL_TRANSCRIPTION" if technical["audio_stream"] else "NOT_APPLICABLE"
                ocr_targets = [(frame["path"], frame["scene_index"], frame["frame_index"], frame["timestamp"])
                               for frame in keyframes]
            else:
                scenes, keyframes = [], []
                record["audio_stream"] = False
                record["transcript_state"] = "NOT_APPLICABLE"
                ocr_targets = ([(page["path"], None, page["page_index"], None) for page in pages]
                               if pages else [(str(media), None, 0, None)])
            record["scenes"] = scenes
            record["keyframes"] = keyframes
            record["canonical_scenes"] = len(scenes)
            record["canonical_keyframes"] = len(keyframes)
            record["audio_evaluated"] = True
            record["checkpoint"] = "KEYFRAMES_COMPLETE"

            if reader is None:
                record["ocr_evaluated"] = False
                record["ocr_error"] = ocr_error
                raise RuntimeError("LOCAL_OCR_UNAVAILABLE")
            import numpy
            from PIL import Image
            observations = []
            for path, scene_index, frame_index, timestamp in ocr_targets:
                with Image.open(path) as image:
                    ocr_input, ocr_scale = bounded_ocr_input(image)
                    for box, text, confidence in reader.readtext(ocr_input, detail=1, paragraph=False):
                        observations.append({"text": text, "confidence": float(confidence),
                                             "scene_index": scene_index, "frame_index": frame_index,
                                             "timestamp": timestamp,
                                             "box": [[float(x) / ocr_scale for x in point] for point in box],
                                             "ocr_input_scale": ocr_scale})
            record["ocr_evaluated"] = True
            record["ocr_texts_by_scene"] = {}
            for observation in observations:
                key = str(observation["scene_index"])
                record["ocr_texts_by_scene"].setdefault(key, []).append(observation["text"])
            record["ocr_observations_list"] = observations
            record["ocr_observations"] = len(observations)
            record["checkpoint"] = "OCR_COMPLETE"
            record["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        except Exception as exc:
            record["checkpoint"] = "LOCAL_FAILED"
            record["failure"] = f"{type(exc).__name__}: {exc}"
            record["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        records[asset_id] = record
        processed += 1
        write_json(CHECKPOINT, {**data, "updated_at": now()})
        print(json.dumps({"ordinal": record["ordinal"], "checkpoint": record["checkpoint"],
                          "scenes": record.get("canonical_scenes"), "keyframes": record.get("canonical_keyframes"),
                          "ocr": record.get("ocr_observations"), "failure": record.get("failure")}), flush=True)
    return {"stage": "prepare", "processed": processed}


# --------------------------------------------------------------------- transcript
def transcript_stage(limit: int | None, through: int = 880) -> dict[str, Any]:
    """Local speech evaluation. No audio ever leaves the machine."""
    from faster_whisper import WhisperModel

    data = state()
    records: dict[str, Any] = data.setdefault("assets", {})
    pending = [r for r in records.values() if in_scope(r, through)
               if r.get("checkpoint") == "OCR_COMPLETE" and r.get("transcript_state") == "PENDING_LOCAL_TRANSCRIPTION"]
    pending.sort(key=lambda x: x["ordinal"])
    settled = [r for r in records.values() if in_scope(r, through)
               if r.get("checkpoint") == "OCR_COMPLETE" and r.get("transcript_state") != "PENDING_LOCAL_TRANSCRIPTION"]
    for record in settled:  # assets with no audio need no model to be marked complete
        record["checkpoint"] = "TRANSCRIBED"
    if limit:
        pending = pending[:limit]
    if not pending:
        write_json(CHECKPOINT, {**data, "updated_at": now()})
        return {"stage": "transcript", "pending": 0, "settled_without_audio": len(settled)}

    snapshots = sorted((Path.home() / ".cache/huggingface/hub/models--Systran--faster-whisper-small/snapshots").glob("*"))
    if not snapshots:
        raise RuntimeError("LOCAL_WHISPER_MODEL_MISSING")
    model = WhisperModel(str(snapshots[-1]), device="cpu", compute_type="int8", local_files_only=True)
    processed = 0
    for record in pending:
        work = WORKROOT / record["asset_id"]
        media = work / record["filename"]
        try:
            if not media.is_file():
                raise RuntimeError("MEDIA_NOT_RETAINED")
            wav = work / "audio.wav"
            subprocess.run([FF, "-v", "error", "-i", str(media), "-vn", "-ac", "1", "-ar", "16000",
                            "-c:a", "pcm_s16le", "-y", str(wav)], capture_output=True, timeout=600)
            segments, info = model.transcribe(str(wav), beam_size=5, word_timestamps=True,
                                              vad_filter=True, temperature=0,
                                              condition_on_previous_text=False)
            chunks = []
            for segment in segments:
                probabilities = [float(w.probability) for w in (segment.words or [])
                                 if isinstance(w.probability, (int, float))]
                confidence = (round(sum(probabilities) / len(probabilities), 3) if probabilities else
                              (round(max(0.0, min(1.0, math.exp(float(segment.avg_logprob)))), 3)
                               if isinstance(segment.avg_logprob, (int, float)) else None))
                text = " ".join(str(segment.text or "").split())
                if not text:
                    continue
                chunks.append({"start": round(float(segment.start), 3), "end": round(float(segment.end), 3),
                               "text": text, "confidence": confidence, "language": info.language,
                               "language_probability": round(float(info.language_probability), 3)})
            # The certified meaningfulness gate: a chime or a single decoded token is not speech.
            meaningful = [c for c in chunks
                          if (c["confidence"] or 0) >= 0.6 and len(c["text"].split()) >= 2
                          and (c["end"] - c["start"]) >= 0.6
                          and (c["language_probability"] or 0) >= 0.7]
            record["transcript_chunks"] = meaningful
            record["transcript_rejected"] = len(chunks) - len(meaningful)
            record["transcript_state"] = ("MEANINGFUL_SPEECH" if meaningful else
                                          "NO_MEANINGFUL_SPEECH" if chunks else "NO_SPEECH")
            record["checkpoint"] = "TRANSCRIBED"
            wav.unlink(missing_ok=True)
        except Exception as exc:
            record["transcript_state"] = "LOCAL_TRANSCRIPTION_FAILED"
            record["transcript_error"] = f"{type(exc).__name__}: {exc}"
            record["checkpoint"] = "LOCAL_FAILED"
            record["failure"] = record["transcript_error"]
        processed += 1
        write_json(CHECKPOINT, {**data, "updated_at": now()})
        print(json.dumps({"ordinal": record["ordinal"], "transcript_state": record["transcript_state"],
                          "chunks": len(record.get("transcript_chunks", []))}), flush=True)
    return {"stage": "transcript", "processed": processed, "settled_without_audio": len(settled)}


# ------------------------------------------------------------------------ visual
def adopt_stage(limit: int | None, through: int = 880) -> dict[str, Any]:
    """Bring the completed #31-#130 local work into this checkpoint.

    Acquisition, probing, scene detection, keyframe extraction and transcription all stand as they
    are; nothing is re-downloaded or re-decoded. The one gap is OCR: that run recorded only a count,
    never the recognised text, so the text is read back off the retained keyframes. That completes a
    stage rather than repeating one, and it is what lets those assets persist OCR evidence.
    """
    frozen = read_json(FROZEN_CHECKPOINT, {"assets": []})
    data = state()
    records: dict[str, Any] = data.setdefault("assets", {})
    pending = [x for x in frozen.get("assets", []) if in_scope(x, through)
               and x.get("checkpoint") == "WAITING_EXTERNAL_AI_APPROVAL"
               and records.get(x["asset_id"], {}).get("checkpoint") not in
               {"TRANSCRIBED", "LOCAL_EVIDENCE_COMPLETE"}]
    pending.sort(key=lambda x: x["ordinal"])
    if limit:
        pending = pending[:limit]
    if not pending:
        return {"stage": "adopt", "pending": 0}

    import easyocr
    import numpy
    from PIL import Image
    reader = easyocr.Reader(["en"], gpu=False,
                            model_storage_directory=str(ROOT / "tmp/phase7_easyocr_models"),
                            user_network_directory=str(ROOT / "tmp/phase7_easyocr_models"),
                            verbose=False, download_enabled=False)
    adopted = 0
    for source in pending:
        asset_id = source["asset_id"]
        keyframes = [{"scene_index": int(f["scene_index"]),
                      "frame_index": int(str(f["path"]).rsplit("frame-", 1)[-1].split(".")[0]),
                      "timestamp": float(f["timestamp"]), "path": f["path"]}
                     for f in source.get("keyframes", [])]
        record = {**source, "keyframes": keyframes,
                  "adopted_from": "production-rollout-local-checkpoint.json"}
        try:
            observations = []
            for frame in keyframes:
                with Image.open(frame["path"]) as image:
                    ocr_input, ocr_scale = bounded_ocr_input(image)
                    for box, text, confidence in reader.readtext(ocr_input, detail=1, paragraph=False):
                        observations.append({"text": text, "confidence": float(confidence),
                                             "scene_index": frame["scene_index"],
                                             "frame_index": frame["frame_index"],
                                             "timestamp": frame["timestamp"],
                                             "box": [[float(x) / ocr_scale for x in point] for point in box],
                                             "ocr_input_scale": ocr_scale})
            record["ocr_observations_list"] = observations
            record["ocr_observations"] = len(observations)
            record["ocr_evaluated"] = True
            record["checkpoint"] = "TRANSCRIBED"
        except Exception as exc:
            record["checkpoint"] = "LOCAL_FAILED"
            record["failure"] = f"{type(exc).__name__}: {exc}"
        records[asset_id] = record
        adopted += 1
        write_json(CHECKPOINT, {**data, "updated_at": now()})
        print(json.dumps({"ordinal": record["ordinal"], "checkpoint": record["checkpoint"],
                          "ocr": record.get("ocr_observations")}), flush=True)
    return {"stage": "adopt", "adopted": adopted}


def requeue_failed(records: dict[str, Any], through: int = 880) -> int:
    """Return failed assets to the last stage they genuinely completed.

    A failure in one stage must not strand an asset whose earlier stages are intact, so retrying
    resumes from the completed evidence rather than re-acquiring and re-decoding the media.
    """
    requeued = 0
    for record in records.values():
        if not in_scope(record, through):
            continue
        if record.get("checkpoint") != "LOCAL_FAILED":
            continue
        if not (record.get("ocr_evaluated") and record.get("transcript_state") not in
                {None, "PENDING_LOCAL_TRANSCRIPTION", "LOCAL_TRANSCRIPTION_FAILED"}):
            continue
        record["checkpoint"] = "TRANSCRIBED"
        record.pop("failure", None)
        requeued += 1
    return requeued


def visual_stage(limit: int | None, dry_run: bool, through: int = 880) -> dict[str, Any]:
    """OpenCLIP vectors plus canonical persistence of the local evidence. No Claude call."""
    from supabase import create_client
    from PIL import Image
    sys.path.insert(0, str(ROOT / "dashboard"))
    from visual_indexing.openclip_encoder import OpenClipEncoder
    from kdi_media import canonical_rows as cr
    from kdi_media import local_preparation as lp
    from kdi_media.supabase_production_adapter import _l2_mean_pool

    manifest_ids = {x["asset_id"] for x in manifest_assets() if x["ordinal"] <= through}
    data = state()
    records: dict[str, Any] = data["assets"]
    requeued = requeue_failed(records, through)
    pending = [r for r in records.values() if in_scope(r, through) and r.get("checkpoint") == "TRANSCRIBED"]
    pending.sort(key=lambda x: x["ordinal"])
    if limit:
        pending = pending[:limit]
    if not pending:
        return {"stage": "visual", "pending": 0, "requeued": requeued}

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    certified = client.table("asset_semantic_layers").select("asset_id").eq("active", True).execute().data or []
    counts: dict[str, int] = {}
    for row in certified:
        counts[row["asset_id"]] = counts.get(row["asset_id"], 0) + 1
    locked = {k for k, v in counts.items() if v == 18}
    encoder = OpenClipEncoder()

    def embed(path: str) -> list[float]:
        with Image.open(path) as image:
            return [float(x) for x in encoder.embed_image(image)]

    processed = 0
    for record in pending:
        asset_id = record["asset_id"]
        if asset_id not in manifest_ids:
            raise RuntimeError(f"OUT_OF_SCOPE_ASSET:{asset_id}")
        if asset_id in locked:
            raise RuntimeError(f"CERTIFIED_ASSET_IS_IMMUTABLE:{asset_id}")
        checksum = record["checksum"]
        run_id = local_run_id(asset_id, checksum)
        started = time.perf_counter()
        try:
            keyframe_vectors = []
            asset_vector = None
            if record["media_type"] == "VIDEO":
                for frame in record["keyframes"]:
                    keyframe_vectors.append((int(frame["scene_index"]), int(frame["frame_index"]),
                                             embed(frame["path"])))
                if not keyframe_vectors:
                    raise RuntimeError("NO_KEYFRAMES_TO_EMBED")
            elif record.get("page_images"):
                pages = [embed(page["path"]) for page in record["page_images"]]
                asset_vector = _l2_mean_pool(pages) if len(pages) > 1 else pages[0]
            else:
                asset_vector = embed(str(WORKROOT / asset_id / record["filename"]))

            scenes = record.get("scenes", [])
            embeddings = lp.visual_embedding_rows(
                asset_id, run_id, checksum, keyframe_vectors=keyframe_vectors,
                scene_pool=_l2_mean_pool, asset_vector=asset_vector,
                asset_metadata=None if asset_vector is None else
                {"aggregation": "l2_mean_pool_l2_v1" if record.get("page_images") else "single_image",
                 "preprocessing": "openclip_exif_rgb_bicubic_v1",
                 "pages": len(record.get("page_images") or [])})
            rows = {
                "asset_scenes": lp.scene_rows(asset_id, run_id, checksum, scenes),
                "asset_keyframes": lp.keyframe_rows(asset_id, run_id, checksum, record.get("keyframes", [])),
                "ocr_observations": lp.ocr_rows(asset_id, run_id, checksum,
                                                record.get("ocr_observations_list", [])),
                "asset_transcript_chunks": lp.transcript_rows(asset_id, run_id, checksum,
                                                              record.get("transcript_chunks", []), scenes),
                "semantic_embeddings": embeddings,
            }
            record["staged"] = {table: len(value) for table, value in rows.items()}
            if dry_run:
                record["visual_dry_run"] = True
                print(json.dumps({"ordinal": record["ordinal"], "status": "DRY_RUN", **record["staged"]}), flush=True)
                processed += 1
                continue

            client.table("semantic_analysis_runs").upsert(
                lp.run_row(asset_id, run_id, checksum, record.get("started_at") or now(),
                           {"ordinal": record["ordinal"], "media_type": record["media_type"],
                            "scenes": len(scenes), "keyframes": len(record.get("keyframes", [])),
                            "technical_probe": record.get("technical_probe") or {},
                            "file_size_bytes": record.get("size")}),
                on_conflict="id").execute()
            technical = record.get("technical_probe") or {}
            width, height = technical.get("width"), technical.get("height")
            fps_value = technical.get("fps")
            if isinstance(fps_value, str) and "/" in fps_value:
                numerator, denominator = fps_value.split("/", 1)
                fps_value = float(numerator) / float(denominator) if float(denominator) else None
            orientation = ("LANDSCAPE" if width and height and width > height else
                           "PORTRAIT" if width and height and height > width else
                           "SQUARE" if width and height else "UNKNOWN")
            technical_row = {
                "asset_id": asset_id, "width_px": width, "height_px": height,
                "aspect_ratio": round(width / height, 6) if width and height else None,
                "orientation": orientation, "duration_seconds": technical.get("duration_seconds"),
                "fps": fps_value, "codec": technical.get("codec") or technical.get("format"),
                "rotation_degrees": technical.get("rotation_degrees"),
                "has_audio": bool(technical.get("audio_stream")),
                "audio_codec": technical.get("audio_codec"),
                "sample_rate_hz": technical.get("sample_rate_hz"),
                "provenance": "KDI_LOCAL_PREPARATION_V1",
                "metadata": {"source_fingerprint": checksum,
                             "file_size_bytes": technical.get("file_size_bytes") or record.get("size"),
                             "format_name": technical.get("format_name") or technical.get("format"),
                             "decoded_locally": bool(technical.get("decoded_locally"))},
            }
            try:
                client.table("asset_technical_metadata").upsert(
                    technical_row, on_conflict="asset_id").execute()
                record["technical_metadata_persisted_to"] = "asset_technical_metadata"
            except Exception as exc:
                # This table is intentionally not granted to the worker role in the current live
                # deployment. Keep the complete deterministic probe in the canonical run metadata
                # and checkpoint, and surface the grant gap as an exception instead of discarding
                # otherwise valid local evidence or changing database security here.
                if "permission denied for table asset_technical_metadata" not in str(exc):
                    raise
                record["technical_metadata_persisted_to"] = "semantic_analysis_runs.metadata"
                record["technical_metadata_exception"] = "WORKER_ROLE_TABLE_GRANT_MISSING"
            for table in ("asset_scenes", "asset_keyframes", "ocr_observations", "semantic_embeddings"):
                if rows[table]:
                    client.table(table).upsert(rows[table], on_conflict="id").execute()
            # Transcript chunks carry a generated bigint key, so idempotency comes from clearing
            # this run's own chunks before reinserting rather than from an upsert conflict target.
            client.table("asset_transcript_chunks").delete().eq("asset_id", asset_id).eq(
                "semantic_analysis_run_id", run_id).execute()
            if rows["asset_transcript_chunks"]:
                client.table("asset_transcript_chunks").insert(rows["asset_transcript_chunks"]).execute()

            record["analysis_run_id"] = run_id
            record["local_evidence_complete"] = True
            record["external_semantic_status"] = lp.EXTERNAL_STATUS
            record["SEARCH_READY"] = False
            record["checkpoint"] = "LOCAL_EVIDENCE_COMPLETE"
            record["visual_elapsed_seconds"] = round(time.perf_counter() - started, 2)
        except Exception as exc:
            record["checkpoint"] = "LOCAL_FAILED"
            record["failure"] = f"{type(exc).__name__}: {exc}"
        processed += 1
        write_json(CHECKPOINT, {**data, "updated_at": now()})
        print(json.dumps({"ordinal": record["ordinal"], "checkpoint": record["checkpoint"],
                          "staged": record.get("staged"), "failure": record.get("failure")}), flush=True)
    return {"stage": "visual", "processed": processed, "requeued": requeued}


# --------------------------------------------------------------------- reconcile
def reconcile(through: int = 880) -> dict[str, Any]:
    from supabase import create_client
    from kdi_media import local_preparation as lp

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    def count(table: str, build) -> int:
        query = build(client.table(table).select("*", count="exact", head=True))
        return int(query.execute().count or 0)

    manifest = read_json(MANIFEST, {})
    records = state().get("assets", {})
    values = [x for x in records.values() if in_scope(x, through)]
    certified = [x for x in manifest.get("excluded_assets", []) if x.get("certified")]
    unsupported = [x for x in manifest.get("excluded_assets", []) if not x.get("certified")]

    def has(state_name: str) -> int:
        return sum(1 for x in values if x.get("transcript_state") == state_name)

    complete = [x for x in values if x.get("checkpoint") == "LOCAL_EVIDENCE_COMPLETE"]
    failed = [x for x in values if x.get("checkpoint") == "LOCAL_FAILED"]
    ready = client.table("kdi_search_ready_assets_v1").select("asset_id", count="exact", head=True).eq(
        "search_ready", True).execute()

    payload = {
        "generated_at": now(),
        "total_assets": int(manifest.get("library_total", 0)),
        "certified_untouched": len(certified),
        "locally_processed": len(complete) + len(certified),
        "assets_with_scenes": sum(1 for x in values if x.get("canonical_scenes")),
        "scenes": sum(int(x.get("canonical_scenes") or 0) for x in values),
        "keyframes": sum(int(x.get("canonical_keyframes") or 0) for x in values),
        "audio_evaluated": sum(1 for x in values if x.get("audio_evaluated")),
        "meaningful_speech": has("MEANINGFUL_SPEECH"),
        "no_meaningful_speech": has("NO_MEANINGFUL_SPEECH"),
        "no_speech": has("NO_SPEECH"),
        "transcripts": sum(len(x.get("transcript_chunks") or []) for x in values),
        "ocr_observations": sum(int(x.get("ocr_observations") or 0) for x in values),
        "visual_asset_embeddings": count("semantic_embeddings", lambda q: q.eq("representation_type", "VISUAL_ASSET")),
        "visual_scene_embeddings": count("semantic_embeddings", lambda q: q.eq("representation_type", "VISUAL_SCENE")),
        "visual_keyframe_embeddings": count("semantic_embeddings", lambda q: q.eq("representation_type", "VISUAL_KEYFRAME")),
        "local_evidence_complete": len(complete),
        "pending_privacy_review": sum(1 for x in complete if x.get("external_semantic_status") == lp.EXTERNAL_STATUS),
        "claude_processed": 0,
        "search_ready": int(ready.count or 0),
        "failures": len(failed) + len(unsupported),
        "failure_reasons": {},
    }
    reasons: dict[str, int] = {}
    detail: list[dict[str, Any]] = []
    for item in failed:
        key = str(item.get("failure") or "UNKNOWN").split(":")[0]
        reasons[key] = reasons.get(key, 0) + 1
        detail.append({"ordinal": item["ordinal"], "filename": item["filename"], "reason": item.get("failure")})
    for item in unsupported:
        for reason in item["excluded_reasons"]:
            reasons[reason] = reasons.get(reason, 0) + 1
        detail.append({"ordinal": None, "filename": item["filename"],
                       "reason": ",".join(item["excluded_reasons"])})
    payload["failure_reasons"] = reasons
    payload["unresolved_failures"] = detail
    write_json(RECONCILIATION, payload)
    print(json.dumps({k: v for k, v in payload.items() if k != "unresolved_failures"}, default=str))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["prepare", "adopt", "transcript", "visual", "reconcile"], required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="visual stage only: build rows, write nothing")
    parser.add_argument("--only", default=None,
                        help="prepare stage only: comma-separated ordinals, for targeted reruns")
    parser.add_argument("--through", type=int, default=880,
                        help="inclusive final canonical ordinal; use 330 for Batch A")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local", override=False)
    if args.stage == "prepare":
        only = {int(x) for x in args.only.split(",")} if args.only else None
        print(json.dumps(prepare_stage(args.limit, only, args.through)))
    elif args.stage == "adopt":
        print(json.dumps(adopt_stage(args.limit, args.through)))
    elif args.stage == "transcript":
        print(json.dumps(transcript_stage(args.limit, args.through)))
    elif args.stage == "visual":
        print(json.dumps(visual_stage(args.limit, args.dry_run, args.through)))
    else:
        reconcile(args.through)


if __name__ == "__main__":
    main()
