"""Deterministic, shadow-only, every-frame video timeline analysis.

No semantic labels, OCR, transcription, embeddings, database writes, or source mutations occur here.
FFmpeg decodes a low-resolution grayscale derivative of every decodable frame. NumPy computes
lightweight temporal signals used for technical scene/event/keyframe candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import time
import tracemalloc
from typing import Any
import uuid

import numpy as np

from .video_frames import resolve_ffmpeg_paths


PROCESSOR_VERSION = "kdi_video_timeline_v1"
NAMESPACE = uuid.UUID("fa84535f-f7b7-42bd-a434-00d0f04330bd")


class TimelineProcessingError(RuntimeError):
    pass


def canonical_fingerprint(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def parse_rate(value: str | None) -> float:
    if not value or value in {"0/0", "N/A"}:
        return 0.0
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        return float(numerator) / float(denominator) if float(denominator) else 0.0
    return float(value)


@dataclass(frozen=True)
class TimelineConfig:
    values: dict[str, Any]
    fingerprint: str

    @classmethod
    def load(cls, path: Path) -> "TimelineConfig":
        values = json.loads(path.read_text(encoding="utf-8"))
        if values.get("processor_version") != PROCESSOR_VERSION:
            raise TimelineProcessingError("processor/config version mismatch")
        return cls(values=values, fingerprint=canonical_fingerprint(values))

    def __getitem__(self, key: str) -> Any:
        return self.values[key]


class VideoTimelineProcessor:
    def __init__(self, config: TimelineConfig, *, ffmpeg_path: str | None = None, ffprobe_path: str | None = None) -> None:
        self.config = config
        resolved_ffmpeg, resolved_ffprobe = resolve_ffmpeg_paths()
        self.ffmpeg_path = ffmpeg_path or resolved_ffmpeg
        self.ffprobe_path = ffprobe_path or resolved_ffprobe

    def probe(self, source: Path) -> dict[str, Any]:
        command = [self.ffprobe_path, "-v", "error", "-show_streams", "-show_format", "-count_frames", "-of", "json", str(source)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=120)
            raw = json.loads(result.stdout)
        except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as exc:
            raise TimelineProcessingError(f"ffprobe failed: {exc}") from exc
        videos = [x for x in raw.get("streams", []) if x.get("codec_type") == "video"]
        if not videos:
            raise TimelineProcessingError("no video stream")
        video = videos[0]
        audio = next((x for x in raw.get("streams", []) if x.get("codec_type") == "audio"), None)
        fmt = raw.get("format") or {}
        fps = parse_rate(video.get("avg_frame_rate") or video.get("r_frame_rate"))
        duration = float(video.get("duration") or fmt.get("duration") or 0)
        frames = int(video.get("nb_read_frames") or video.get("nb_frames") or round(duration * fps))
        rotation = (video.get("tags") or {}).get("rotate")
        for side_data in video.get("side_data_list") or []:
            rotation = side_data.get("rotation", rotation)
        probe = {
            "container": fmt.get("format_name"), "codec": video.get("codec_name"),
            "duration_seconds": duration, "width": int(video.get("width") or 0),
            "height": int(video.get("height") or 0), "fps": fps,
            "frame_count": frames, "pixel_format": video.get("pix_fmt"),
            "rotation": int(rotation or 0), "audio_stream_present": audio is not None,
            "audio_codec": audio.get("codec_name") if audio else None,
            "file_size_bytes": int(fmt.get("size") or source.stat().st_size),
            "variable_frame_rate_possible": video.get("avg_frame_rate") != video.get("r_frame_rate"),
        }
        if duration <= 0 or probe["width"] <= 0 or probe["height"] <= 0 or fps <= 0 or frames <= 0:
            raise TimelineProcessingError(f"invalid probe metadata: {probe}")
        return probe

    def _decode_signals(self, source: Path, fps: float) -> tuple[list[dict[str, float]], int, list[str]]:
        width, height = int(self.config["analysis_width"]), int(self.config["analysis_height"])
        frame_bytes = width * height
        vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=gray"
        command = [self.ffmpeg_path, "-v", "error", "-i", str(source), "-map", "0:v:0", "-vf", vf, "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert process.stdout is not None
        signals: list[dict[str, float]] = []
        previous: np.ndarray | None = None
        failures = 0
        warnings: list[str] = []
        try:
            while True:
                data = process.stdout.read(frame_bytes)
                if not data:
                    break
                if len(data) != frame_bytes:
                    failures += 1
                    warnings.append(f"partial_raw_frame:{len(data)}/{frame_bytes}")
                    break
                frame = np.frombuffer(data, dtype=np.uint8).reshape(height, width)
                brightness = float(frame.mean() / 255.0)
                edge = float((np.abs(np.diff(frame.astype(np.int16), axis=0)).mean() + np.abs(np.diff(frame.astype(np.int16), axis=1)).mean()) / 510.0)
                hist = np.histogram(frame, bins=16, range=(0, 256), density=True)[0]
                quadrants = np.array([frame[:height//2, :width//2].mean(), frame[:height//2, width//2:].mean(), frame[height//2:, :width//2].mean(), frame[height//2:, width//2:].mean()]) / 255.0
                if previous is None:
                    diff = hist_diff = composition = 0.0
                else:
                    delta = np.abs(frame.astype(np.int16) - previous.astype(np.int16))
                    diff = float(delta.mean() / 255.0)
                    prior_hist = np.histogram(previous, bins=16, range=(0, 256), density=True)[0]
                    hist_diff = float(np.abs(hist - prior_hist).sum() * 8.0)
                    prior_q = np.array([previous[:height//2, :width//2].mean(), previous[:height//2, width//2:].mean(), previous[height//2:, :width//2].mean(), previous[height//2:, width//2:].mean()]) / 255.0
                    composition = float(np.abs(quadrants - prior_q).mean())
                change = min(1.0, 0.62 * diff + 0.23 * min(hist_diff, 1.0) + 0.15 * composition)
                signals.append({"frame": len(signals), "timestamp_seconds": len(signals) / fps, "visual_change_score": change, "motion_score": diff, "histogram_change_score": min(hist_diff, 1.0), "composition_change_score": composition, "brightness": brightness, "edge_texture_score": edge})
                previous = frame.copy()
                if failures > int(self.config["maximum_decode_failures"]):
                    break
            stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
            return_code = process.wait(timeout=int(self.config["decode_timeout_seconds"]))
            if return_code != 0:
                raise TimelineProcessingError(f"ffmpeg decode failed ({return_code}): {stderr[-500:]}")
        except Exception:
            process.kill()
            process.wait()
            raise
        if not signals:
            raise TimelineProcessingError("no decodable frames")
        return signals, failures, warnings

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        return float(np.percentile(np.asarray(values, dtype=float), percentile)) if values else 0.0

    def _boundaries(self, signals: list[dict[str, float]], fps: float) -> list[dict[str, Any]]:
        changes = [x["visual_change_score"] for x in signals[1:]]
        hard = max(float(self.config["hard_cut_min_score"]), self._percentile(changes, float(self.config["hard_cut_percentile"])))
        soft = max(float(self.config["soft_change_min_score"]), self._percentile(changes, float(self.config["soft_change_percentile"])))
        persistence = max(2, round(float(self.config["soft_persistence_seconds"]) * fps))
        debounce = max(1, round(float(self.config["boundary_debounce_seconds"]) * fps))
        minimum_scene = max(1, round(float(self.config["minimum_scene_duration_seconds"]) * fps))
        candidates: list[dict[str, Any]] = []
        for i in range(1, len(signals)):
            s = signals[i]
            if s["visual_change_score"] >= hard and s["histogram_change_score"] >= min(0.12, hard):
                candidates.append({"frame": i, "boundary_type": "HARD_CUT", "score": s["visual_change_score"], "confidence": min(1.0, s["visual_change_score"] / max(hard, 1e-6)), "supporting_signals": {k: s[k] for k in ("visual_change_score", "motion_score", "histogram_change_score", "composition_change_score")}})
            elif i >= persistence:
                window = signals[i-persistence+1:i+1]
                mean_change = statistics.fmean(x["visual_change_score"] for x in window)
                mean_composition = statistics.fmean(x["composition_change_score"] for x in window)
                if mean_change >= soft and mean_composition >= soft * 0.35:
                    candidates.append({"frame": i - persistence // 2, "boundary_type": "SOFT_TRANSITION", "score": mean_change, "confidence": min(1.0, mean_change / max(soft, 1e-6)), "supporting_signals": {"persistent_mean_change": mean_change, "persistent_composition_change": mean_composition, "window_frames": persistence}})
        accepted: list[dict[str, Any]] = []
        for candidate in sorted(candidates, key=lambda x: (x["frame"], -x["score"])):
            if candidate["frame"] < minimum_scene or candidate["frame"] > len(signals) - minimum_scene:
                continue
            if accepted and candidate["frame"] - accepted[-1]["frame"] < debounce:
                if candidate["score"] > accepted[-1]["score"]:
                    accepted[-1] = candidate
                continue
            accepted.append(candidate)
        for item in accepted:
            item["timestamp_seconds"] = item["frame"] / fps
        return accepted

    def _scenes(self, signals: list[dict[str, float]], boundaries: list[dict[str, Any]], fps: float, duration: float, seed: str) -> list[dict[str, Any]]:
        points = [0] + [x["frame"] for x in boundaries] + [len(signals)]
        scenes = []
        for index, (start, stop) in enumerate(zip(points, points[1:])):
            end_frame = max(start, stop - 1)
            end_time = duration if index == len(points) - 2 else stop / fps
            incoming = "VIDEO_START" if index == 0 else boundaries[index - 1]["boundary_type"]
            outgoing = "VIDEO_END" if index == len(points) - 2 else boundaries[index]["boundary_type"]
            confidence_values = [x["confidence"] for x in boundaries[max(0,index-1):min(len(boundaries),index+1)]]
            scenes.append({"scene_id": str(uuid.uuid5(NAMESPACE, f"{seed}:scene:{index}:{start}:{end_frame}")), "scene_index": index, "start_time": start / fps, "end_time": end_time, "start_frame": start, "end_frame": end_frame, "duration": max(0.0, end_time - start / fps), "boundary_in_reason": incoming, "boundary_out_reason": outgoing, "confidence": statistics.fmean(confidence_values) if confidence_values else 0.75})
        return scenes

    def _events(self, signals: list[dict[str, float]], scenes: list[dict[str, Any]], fps: float, seed: str) -> list[dict[str, Any]]:
        values = [max(x["visual_change_score"], x["motion_score"], x["composition_change_score"]) for x in signals[1:]]
        threshold = max(float(self.config["event_min_score"]), self._percentile(values, float(self.config["event_percentile"])))
        peaks = [i for i in range(1, len(signals)) if max(signals[i]["visual_change_score"], signals[i]["motion_score"], signals[i]["composition_change_score"]) >= threshold]
        context = max(1, round(float(self.config["event_context_seconds"]) * fps))
        merge = max(1, round(float(self.config["event_merge_window_seconds"]) * fps))
        windows: list[list[int]] = []
        for peak in peaks:
            start, end = max(0, peak - context), min(len(signals) - 1, peak + context)
            if windows and start - windows[-1][1] <= merge:
                windows[-1][1] = max(windows[-1][1], end)
                windows[-1][2].append(peak)
            else:
                windows.append([start, end, [peak]])
        events = []
        min_frames = max(1, round(float(self.config["minimum_event_duration_seconds"]) * fps))
        max_frames = max(min_frames, round(float(self.config["maximum_event_duration_seconds"]) * fps))
        for index, (start, end, local_peaks) in enumerate(windows):
            if end - start + 1 < min_frames:
                end = min(len(signals) - 1, start + min_frames - 1)
            if end - start + 1 > max_frames:
                strongest = max(local_peaks, key=lambda i: signals[i]["visual_change_score"] + signals[i]["motion_score"])
                start, end = max(0, strongest - max_frames//2), min(len(signals)-1, strongest + max_frames//2)
            peak = max(local_peaks, key=lambda i: signals[i]["visual_change_score"] + signals[i]["motion_score"] + signals[i]["composition_change_score"])
            scene = next((s for s in scenes if s["start_frame"] <= peak <= s["end_frame"]), scenes[-1])
            magnitude = max(signals[peak]["visual_change_score"], signals[peak]["motion_score"], signals[peak]["composition_change_score"])
            signal_type = "COMPOSITION_CHANGE" if signals[peak]["composition_change_score"] >= signals[peak]["motion_score"] else ("VISUAL_STATE_CHANGE" if signals[peak]["visual_change_score"] >= signals[peak]["motion_score"] else "MOTION_CHANGE")
            events.append({"event_id": str(uuid.uuid5(NAMESPACE, f"{seed}:event:{index}:{start}:{end}:{peak}")), "event_index": index, "scene_index": scene["scene_index"], "scene_id": scene["scene_id"], "start_time": start / fps, "end_time": min(end / fps, scenes[-1]["end_time"]), "peak_time": peak / fps, "start_frame": start, "end_frame": end, "peak_frame": peak, "event_signal_type": signal_type, "change_magnitude": magnitude, "confidence": min(1.0, magnitude / max(threshold, 1e-6))})
        return events

    def _adaptive_frames(self, signals: list[dict[str, float]], scenes: list[dict[str, Any]], events: list[dict[str, Any]], boundaries: list[dict[str, Any]], fps: float) -> tuple[set[int], dict[int, set[str]]]:
        selected: set[int] = set()
        reasons: dict[int, set[str]] = {}
        def add(frame: int, reason: str) -> None:
            frame = min(max(0, frame), len(signals) - 1)
            selected.add(frame); reasons.setdefault(frame, set()).add(reason)
        stable_step = max(1, round(float(self.config["stable_sampling_interval_seconds"]) * fps))
        for frame in range(0, len(signals), stable_step): add(frame, "STABLE_INTERVAL")
        for scene in scenes:
            add(scene["start_frame"], "SCENE_START_STATE"); add((scene["start_frame"] + scene["end_frame"]) // 2, "SCENE_MIDDLE_REPRESENTATIVE"); add(scene["end_frame"], "SCENE_END_STATE")
        boundary_window = max(1, round(float(self.config["boundary_dense_window_seconds"]) * fps))
        boundary_step = max(1, round(float(self.config["boundary_sampling_interval_seconds"]) * fps))
        for boundary in boundaries:
            for frame in range(max(0,boundary["frame"]-boundary_window), min(len(signals),boundary["frame"]+boundary_window+1), boundary_step): add(frame, "BOUNDARY_DENSE_SAMPLE")
            add(boundary["frame"], "PEAK_CHANGE")
        event_step = max(1, round(float(self.config["event_sampling_interval_seconds"]) * fps))
        for event in events:
            for frame in range(event["start_frame"], event["end_frame"]+1, event_step): add(frame, "EVENT_DENSE_SAMPLE")
            add(event["peak_frame"], "EVENT_PEAK")
        return selected, reasons

    def _keyframes(self, signals: list[dict[str, float]], scenes: list[dict[str, Any]], events: list[dict[str, Any]], sampled: set[int], reasons: dict[int, set[str]], fps: float, source_fingerprint: str, seed: str) -> tuple[list[dict[str, Any]], int]:
        chosen: list[dict[str, Any]] = []
        removed = 0
        threshold = float(self.config["keyframe_redundancy_threshold"])
        max_per_scene = int(self.config["maximum_keyframes_per_scene"])
        for frame in sorted(sampled):
            scene = next((s for s in scenes if s["start_frame"] <= frame <= s["end_frame"]), scenes[-1])
            event = next((e for e in events if e["start_frame"] <= frame <= e["end_frame"]), None)
            role_set = reasons[frame]
            keyframe_roles = {"SCENE_START_STATE", "SCENE_MIDDLE_REPRESENTATIVE", "SCENE_END_STATE", "PEAK_CHANGE", "EVENT_PEAK"}
            if not (role_set & keyframe_roles):
                removed += 1
                continue
            protected = bool({"EVENT_PEAK", "PEAK_CHANGE", "SCENE_START_STATE", "SCENE_END_STATE"} & role_set)
            signature = np.array([signals[frame][k] for k in ("brightness", "edge_texture_score", "histogram_change_score", "composition_change_score")])
            same_scene = [x for x in chosen if x["scene_index"] == scene["scene_index"]]
            if len(same_scene) >= max_per_scene and not protected:
                removed += 1; continue
            if same_scene and not protected:
                prior = np.array(same_scene[-1]["technical_signature"])
                if float(np.linalg.norm(signature-prior)) < threshold:
                    removed += 1; continue
            score = min(1.0, 0.4 + signals[frame]["visual_change_score"] + signals[frame]["motion_score"] * 0.5)
            reason = sorted(role_set, key=lambda x: (x not in {"EVENT_PEAK","PEAK_CHANGE","SCENE_MIDDLE_REPRESENTATIVE"}, x))[0]
            chosen.append({"keyframe_id": str(uuid.uuid5(NAMESPACE, f"{seed}:keyframe:{frame}:{scene['scene_index']}:{event['event_index'] if event else 'none'}")), "frame_number": frame, "timestamp": frame / fps, "scene_index": scene["scene_index"], "scene_id": scene["scene_id"], "event_index": event["event_index"] if event else None, "event_id": event["event_id"] if event else None, "selection_reason": reason, "selection_reasons": sorted(role_set), "selection_score": score, "source_fingerprint": source_fingerprint, "technical_signature": signature.round(6).tolist()})
        return chosen, removed

    def process(self, source: Path, *, asset_id: str, filename: str, source_fingerprint: str, semantic_spec_version: str, semantic_spec_fingerprint: str, pilot_manifest_version: str) -> dict[str, Any]:
        tracemalloc.start()
        started = datetime.now(timezone.utc); wall_start = time.perf_counter()
        seed = f"{asset_id}:{source_fingerprint}:{PROCESSOR_VERSION}:{self.config.fingerprint}"
        run_id = str(uuid.uuid5(NAMESPACE, f"{seed}:run"))
        output: dict[str, Any] = {"analysis_run_id": run_id, "asset_id": asset_id, "filename": filename, "source_fingerprint": source_fingerprint, "processor_version": PROCESSOR_VERSION, "processor_config_fingerprint": self.config.fingerprint, "semantic_spec_version": semantic_spec_version, "semantic_spec_fingerprint": semantic_spec_fingerprint, "pilot_manifest_version": pilot_manifest_version, "started_at": started.isoformat(), "status": "PROCESSING", "warnings": []}
        try:
            probe = self.probe(source); output["technical_metadata"] = probe
            signals, failures, warnings = self._decode_signals(source, probe["fps"])
            boundaries = self._boundaries(signals, probe["fps"])
            decoded_duration = len(signals) / probe["fps"]
            effective_duration = min(probe["duration_seconds"], decoded_duration) if probe["duration_seconds"] else decoded_duration
            scenes = self._scenes(signals, boundaries, probe["fps"], effective_duration, seed)
            events = self._events(signals, scenes, probe["fps"], seed)
            sampled, reasons = self._adaptive_frames(signals, scenes, events, boundaries, probe["fps"])
            keyframes, redundant = self._keyframes(signals, scenes, events, sampled, reasons, probe["fps"], source_fingerprint, seed)
            coverage = min(100.0, len(signals) / max(1, probe["frame_count"]) * 100.0)
            scene_rate = len(scenes) / max(probe["duration_seconds"] / 60.0, 1/60)
            event_rate = len(events) / max(probe["duration_seconds"] / 60.0, 1/60)
            keyframe_rate = len(keyframes) / max(probe["duration_seconds"] / 60.0, 1/60)
            quality_warnings = list(warnings)
            if scene_rate > float(self.config["oversegmentation_scenes_per_minute_warning"]): quality_warnings.append("OVER_SEGMENTATION_SCENE_RATE")
            if event_rate > float(self.config["event_count_per_minute_warning"]): quality_warnings.append("EVENT_COUNT_EXPLOSION")
            if keyframe_rate > float(self.config["keyframes_per_minute_warning"]): quality_warnings.append("KEYFRAME_COUNT_EXPLOSION")
            spikes = sum(x["visual_change_score"] >= max(float(self.config["soft_change_min_score"]), self._percentile([y["visual_change_score"] for y in signals], 90)) for x in signals)
            if probe["duration_seconds"] >= float(self.config["undersegmentation_min_duration_seconds"]) and len(scenes) == 1 and spikes >= int(self.config["undersegmentation_change_spike_count"]): quality_warnings.append("POSSIBLE_UNDER_SEGMENTATION")
            output.update({"status": "COMPLETED" if not failures else "PARTIAL", "frame_analysis": {"expected_frames": probe["frame_count"], "decodable_frames": len(signals), "frames_processed": len(signals), "first_processed_timestamp": 0.0, "last_processed_timestamp": signals[-1]["timestamp_seconds"], "processed_duration_seconds": effective_duration, "timeline_coverage_percent": coverage, "decode_failures": failures, "every_frame_participated": True, "timestamp_basis": "decoded frame ordinal / probed average FPS; presentation timestamps unavailable in raw pipe", "signals": signals}, "boundaries": boundaries, "scene_candidates": scenes, "event_candidates": events, "adaptive_sampling": {"candidate_frame_count": len(sampled), "candidate_frames": sorted(sampled)}, "keyframe_candidates": keyframes, "redundant_keyframes_removed": redundant, "quality_metrics": {"scene_count_per_minute": scene_rate, "event_count_per_minute": event_rate, "keyframes_per_minute": keyframe_rate, "median_scene_duration": statistics.median(x["duration"] for x in scenes), "change_spike_count": spikes}, "warnings": quality_warnings})
        except Exception as exc:
            output.update({"status": "FAILED", "failure": {"type": type(exc).__name__, "message": str(exc)}})
        completed = datetime.now(timezone.utc); elapsed = time.perf_counter() - wall_start
        duration = (output.get("technical_metadata") or {}).get("duration_seconds") or 0
        _, peak_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        output.update({"completed_at": completed.isoformat(), "generated_at": completed.isoformat(), "performance": {"wall_clock_seconds": elapsed, "processing_time_over_video_duration": elapsed / duration if duration else None, "frames_per_second": (output.get("frame_analysis") or {}).get("frames_processed", 0) / elapsed if elapsed else 0, "peak_memory_mb": peak_memory / (1024 * 1024), "temporary_storage_bytes": 0}})
        return output


def functional_output(output: dict[str, Any]) -> dict[str, Any]:
    return {key: output.get(key) for key in ("analysis_run_id", "asset_id", "source_fingerprint", "processor_version", "processor_config_fingerprint", "technical_metadata", "boundaries", "scene_candidates", "event_candidates", "adaptive_sampling", "keyframe_candidates", "redundant_keyframes_removed", "warnings")}
