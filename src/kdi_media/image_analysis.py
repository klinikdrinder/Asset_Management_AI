"""Deterministic, semantic-safe image evidence preparation for KDI Phase 4."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import time
import tracemalloc
from typing import Any
import uuid
import warnings

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


PROCESSOR_VERSION = "kdi_image_analysis_v1"
NAMESPACE = uuid.UUID("bb735c5b-6b2d-48dd-943b-b62ce36eb88a")


def canonical_fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ImageAnalysisConfig:
    values: dict[str, Any]
    fingerprint: str

    @classmethod
    def load(cls, path: Path) -> "ImageAnalysisConfig":
        values = json.loads(path.read_text(encoding="utf-8"))
        if values.get("processor_version") != PROCESSOR_VERSION:
            raise ValueError("IMAGE_PROCESSOR_VERSION_MISMATCH")
        return cls(values, canonical_fingerprint(values))

    def __getitem__(self, key: str) -> Any:
        return self.values[key]


def _iou(a: dict[str, Any], b: dict[str, Any]) -> tuple[float, float]:
    ix1, iy1 = max(a["x1"], b["x1"]), max(a["y1"], b["y1"])
    ix2, iy2 = min(a["x2"], b["x2"]), min(a["y2"], b["y2"])
    intersection = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area_a = (a["x2"] - a["x1"]) * (a["y2"] - a["y1"])
    area_b = (b["x2"] - b["x1"]) * (b["y2"] - b["y1"])
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0, intersection / min(area_a, area_b) if min(area_a, area_b) else 0.0


def suppress_redundant_regions(candidates: list[dict[str, Any]], *, iou_threshold: float, containment_threshold: float, limit: int) -> tuple[list[dict[str, Any]], int]:
    retained: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: (-item["selection_score"], item["y1"], item["x1"])):
        duplicate = False
        for current in retained:
            iou, containment = _iou(candidate, current)
            if candidate["region_type"] == current["region_type"] and (iou >= iou_threshold or containment >= containment_threshold):
                duplicate = True
                break
        if not duplicate and len(retained) < limit:
            retained.append(candidate)
    return retained, len(candidates) - len(retained)


class ImageAnalysisProcessor:
    def __init__(self, config: ImageAnalysisConfig) -> None:
        self.config = config

    @staticmethod
    def _signals(image: Image.Image) -> tuple[np.ndarray, dict[str, float]]:
        gray = np.asarray(image.convert("L"), dtype=np.float32)
        dx = np.abs(np.diff(gray, axis=1)) if gray.shape[1] > 1 else np.zeros_like(gray)
        dy = np.abs(np.diff(gray, axis=0)) if gray.shape[0] > 1 else np.zeros_like(gray)
        sharpness = float((np.var(np.diff(gray, n=2, axis=0)) if gray.shape[0] > 2 else 0) + (np.var(np.diff(gray, n=2, axis=1)) if gray.shape[1] > 2 else 0))
        return gray, {
            "brightness_mean": float(gray.mean()),
            "brightness_median": float(np.median(gray)),
            "contrast_stddev": float(gray.std()),
            "sharpness_estimate": sharpness,
            "horizontal_edge_mean": float(dx.mean()),
            "vertical_edge_mean": float(dy.mean()),
        }

    def _saliency_candidates(self, gray: np.ndarray, width: int, height: int) -> list[dict[str, Any]]:
        small_h, small_w = gray.shape
        values: list[dict[str, Any]] = []
        for scale in self.config["saliency_tile_scales"]:
            tile_w, tile_h = max(8, round(small_w * scale)), max(8, round(small_h * scale))
            for py in (0.0, 0.25, 0.5, 0.75, 1.0):
                for px in (0.0, 0.25, 0.5, 0.75, 1.0):
                    sx = round((small_w - tile_w) * px); sy = round((small_h - tile_h) * py)
                    crop = gray[sy:sy + tile_h, sx:sx + tile_w]
                    edge = float(np.abs(np.diff(crop, axis=0)).mean() + np.abs(np.diff(crop, axis=1)).mean())
                    contrast = float(crop.std())
                    score = contrast + edge
                    x1, y1 = round(sx / small_w * width), round(sy / small_h * height)
                    x2, y2 = round((sx + tile_w) / small_w * width), round((sy + tile_h) / small_h * height)
                    ratio = (x2 - x1) * (y2 - y1) / (width * height)
                    if self.config["minimum_region_area_ratio"] <= ratio <= self.config["maximum_region_area_ratio"]:
                        values.append({"region_type": "OTHER_SALIENT_REGION", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "area_ratio": ratio, "selection_method": "MULTISCALE_EDGE_CONTRAST", "selection_score_raw": score})
        if not values:
            return []
        threshold = float(np.percentile([x["selection_score_raw"] for x in values], self.config["saliency_percentile_threshold"]))
        maximum = max(x["selection_score_raw"] for x in values) or 1.0
        return [{**x, "selection_score": round(x["selection_score_raw"] / maximum, 6), "selection_confidence": round(min(1.0, x["selection_score_raw"] / maximum), 6)} for x in values if x["selection_score_raw"] >= threshold]

    @staticmethod
    def _region(seed: str, asset_id: str, region_type: str, coordinates: tuple[int, int, int, int], width: int, height: int, method: str, confidence: float, score: float, source_fingerprint: str) -> dict[str, Any]:
        x1, y1, x2, y2 = coordinates
        rid = str(uuid.uuid5(NAMESPACE, f"{seed}:region:{region_type}:{x1}:{y1}:{x2}:{y2}"))
        return {"region_id": rid, "asset_id": asset_id, "region_type": region_type, "x1": x1, "y1": y1, "x2": x2, "y2": y2, "normalized_coordinates": {"x1": x1 / width, "y1": y1 / height, "x2": x2 / width, "y2": y2 / height}, "area_ratio": (x2-x1)*(y2-y1)/(width*height), "selection_method": method, "selection_confidence": confidence, "selection_score": score, "processor_version": PROCESSOR_VERSION, "source_fingerprint": source_fingerprint}

    def process(self, source: Path, *, asset_id: str, filename: str, source_fingerprint: str, semantic_spec_version: str, semantic_spec_fingerprint: str, pilot_manifest_version: str, inherited_conflicts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        seed = f"{asset_id}:{source_fingerprint}:{PROCESSOR_VERSION}:{self.config.fingerprint}"
        analysis_run_id = str(uuid.uuid5(NAMESPACE, f"{seed}:analysis-run"))
        started = datetime.now(timezone.utc); started_clock = time.perf_counter(); tracemalloc.start()
        output: dict[str, Any] = {"analysis_run_id": analysis_run_id, "asset_id": asset_id, "filename": filename, "source_fingerprint": source_fingerprint, "processor_version": PROCESSOR_VERSION, "configuration_version": self.config["configuration_version"], "configuration_fingerprint": self.config.fingerprint, "semantic_spec_version": semantic_spec_version, "semantic_spec_fingerprint": semantic_spec_fingerprint, "pilot_manifest_version": pilot_manifest_version, "started_at": started.isoformat(), "status": "PROCESSING"}
        try:
            actual = file_sha256(source)
            if actual != source_fingerprint:
                raise ValueError(f"SOURCE_IDENTITY_MISMATCH:{actual}")
            previous = Image.MAX_IMAGE_PIXELS; Image.MAX_IMAGE_PIXELS = self.config["maximum_image_pixels"]
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(source) as opened:
                        source_size = opened.size; source_mode = opened.mode; source_format = opened.format
                        exif_orientation = opened.getexif().get(274); alpha = "A" in opened.getbands()
                        opened.load(); oriented = ImageOps.exif_transpose(opened).convert("RGB")
            finally:
                Image.MAX_IMAGE_PIXELS = previous
            width, height = oriented.size
            analysis = oriented.copy(); analysis.thumbnail((self.config["analysis_max_dimension"], self.config["analysis_max_dimension"]), Image.Resampling.LANCZOS)
            gray, signals = self._signals(analysis)
            full = self._region(seed, asset_id, "FULL_IMAGE", (0, 0, width, height), width, height, "MANDATORY_FULL_FRAME", 1.0, 1.0, source_fingerprint)
            raw = self._saliency_candidates(gray, width, height)
            retained_raw, removed = suppress_redundant_regions(raw, iou_threshold=self.config["iou_redundancy_threshold"], containment_threshold=self.config["containment_redundancy_threshold"], limit=self.config["maximum_salient_regions"])
            salient = [self._region(seed, asset_id, item["region_type"], (item["x1"], item["y1"], item["x2"], item["y2"]), width, height, item["selection_method"], item["selection_confidence"], item["selection_score"], source_fingerprint) for item in retained_raw]
            regions = [full, *salient]
            evidence = [{"evidence_id": str(uuid.uuid5(NAMESPACE, f"{seed}:evidence:{region['region_id']}")), "asset_id": asset_id, "evidence_type": "ASSET_LEVEL", "region_id": region["region_id"], "observation_type": "IMAGE_REGION", "value": region["region_type"], "confidence": region["selection_confidence"], "method": region["selection_method"], "processor_version": PROCESSOR_VERSION, "source_fingerprint": source_fingerprint, "analysis_run_id": analysis_run_id} for region in regions]
            for name, value in signals.items():
                evidence.append({"evidence_id": str(uuid.uuid5(NAMESPACE, f"{seed}:evidence:technical:{name}")), "asset_id": asset_id, "evidence_type": "ASSET_LEVEL", "region_id": full["region_id"], "observation_type": name.upper(), "value": value, "confidence": 1.0, "method": "DETERMINISTIC_IMAGE_STATISTIC", "processor_version": PROCESSOR_VERSION, "source_fingerprint": source_fingerprint, "analysis_run_id": analysis_run_id})
            orientation = "SQUARE" if width == height else "LANDSCAPE" if width > height else "PORTRAIT"
            output.update({"status": "COMPLETED", "technical_metadata": {"source_width": source_size[0], "source_height": source_size[1], "analysis_width": width, "analysis_height": height, "aspect_ratio": width / height, "orientation": orientation, "exif_orientation": exif_orientation, "orientation_normalized_for_analysis": source_size != oriented.size or exif_orientation not in (None, 1), "source_color_mode": source_mode, "analysis_color_mode": "RGB", "bit_depth_per_channel": 8, "format": source_format, "alpha_channel_present": alpha, "file_size_bytes": source.stat().st_size, "metadata_readable": True, "corruption_status": "NONE"}, "technical_signals": signals, "regions": regions, "candidate_region_count": len(raw) + 1, "retained_region_count": len(regions), "redundant_regions_removed": removed, "detector_availability": {"person_detector": False, "face_head_detector": False, "anatomy_detector": False, "equipment_detector": False, "text_region_detector": False, "generic_saliency": True}, "applicability": {"3": {"layer": "Temporal / Scene Structure", "applicability": "NOT_APPLICABLE", "state": "NOT_APPLICABLE"}, "14": {"layer": "Speech / Transcript / Audio", "applicability": "NOT_APPLICABLE", "state": "NOT_APPLICABLE"}, "15": {"layer": "OCR / Visible Text", "applicability": "APPLICABLE", "state": "UNKNOWN", "note": "No OCR executed; absence of OCR records is not negative evidence."}}, "evidence": evidence, "existing_semantic_status": "UNVERIFIED_EXISTING", "inherited_conflicts": inherited_conflicts or [], "semantic_fields_requiring_phase5": ["GLOBAL_ASSET_UNDERSTANDING", "PEOPLE_ROLES", "PERSON_APPEARANCE", "ANATOMY", "TREATMENT_PROCEDURE", "ACTIONS_EVENTS", "RELATIONSHIPS", "CLINICAL_VISUAL_OBSERVATIONS", "ENVIRONMENT", "CINEMATOGRAPHY", "COMPOSITION", "MARKETING_CONTENT_USAGE", "SEMANTIC_NARRATIVE", "SEARCH_EMBEDDINGS"], "negative_assertion_safety": {"unsupported_no_treatment_imported": False, "unsupported_no_text_imported": False, "absence_of_records_used_as_negative_evidence": False}})
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            output.update({"status": "FAILED", "failure": {"type": type(exc).__name__, "reason": str(exc)}})
        finally:
            _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
            completed = datetime.now(timezone.utc)
            output.update({"completed_at": completed.isoformat(), "generated_at": completed.isoformat(), "performance": {"wall_clock_seconds": time.perf_counter() - started_clock, "peak_memory_mb": peak / 1024 / 1024}})
        return output


def functional_output(output: dict[str, Any]) -> dict[str, Any]:
    keys = ("analysis_run_id", "asset_id", "source_fingerprint", "processor_version", "configuration_version", "configuration_fingerprint", "status", "technical_metadata", "technical_signals", "regions", "candidate_region_count", "retained_region_count", "redundant_regions_removed", "detector_availability", "applicability", "evidence", "inherited_conflicts", "semantic_fields_requiring_phase5", "negative_assertion_safety", "failure")
    return {key: output.get(key) for key in keys}
