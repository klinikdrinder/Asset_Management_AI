"""Read-only local FFmpeg verification for videos in an explicit pilot manifest."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Iterator

from dotenv import load_dotenv
from PIL import Image
from supabase import create_client

from kdi_media.google_drive import create_service_account_readonly_drive_service
from kdi_media.semantic_indexing import DriveContentFetcher, SupabaseSemanticIndexRepository
from kdi_media.semantic_pilot import PilotManifest
from kdi_media.video_frames import DEFAULT_MAX_FRAMES, FfmpegFrameExtractor, resolve_ffmpeg_paths


@contextmanager
def local_video_file(content: bytes, directory: Path) -> Iterator[Path]:
    path = directory / "probe-source.mp4"
    path.write_bytes(content)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--execute-local", action="store_true")
    args = parser.parse_args()
    if not args.execute_local:
        print(json.dumps({"status": "NOT_EXECUTED", "external_ai_calls": 0}))
        return 0

    load_dotenv()
    manifest = PilotManifest.load(args.manifest)
    video_assets = [asset for asset in manifest.assets if asset.media_type == "video"]
    ffmpeg_path, ffprobe_path = resolve_ffmpeg_paths()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    repository = SupabaseSemanticIndexRepository(client)
    fetcher = DriveContentFetcher(create_service_account_readonly_drive_service())
    extractor = FfmpegFrameExtractor(ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path)

    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="kdi-video-verification-") as root_value:
        root = Path(root_value)
        for asset in video_assets:
            started = time.perf_counter()
            candidate = repository.fetch_candidate(asset.asset_id)
            if candidate is None:
                results.append({"asset_id": asset.asset_id, "status": "CANDIDATE_NOT_FOUND"})
                continue
            try:
                content = fetcher.fetch(candidate)
                with local_video_file(content, root) as video_path:
                    probe = subprocess.run(
                        [
                            ffprobe_path, "-v", "error", "-show_entries",
                            "format=duration:stream=codec_type,codec_name,width,height",
                            "-of", "json", str(video_path),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        check=True,
                    )
                    probe_data = json.loads(probe.stdout)
                duration = float((probe_data.get("format") or {}).get("duration") or 0)
                timestamps = extractor._evenly_spaced_timestamps(duration, DEFAULT_MAX_FRAMES)
                frames = extractor.extract_frames(content, max_frames=DEFAULT_MAX_FRAMES)
                dimensions: list[list[int]] = []
                for frame in frames:
                    if not frame.startswith(b"\xff\xd8"):
                        raise ValueError("Extracted frame is not JPEG")
                    with Image.open(BytesIO(frame)) as image:
                        image.load()
                        if image.format != "JPEG" or max(image.size) > 1600:
                            raise ValueError("Extracted frame violates JPEG/dimension boundary")
                        dimensions.append([image.width, image.height])
                streams = probe_data.get("streams") or []
                codecs = sorted(
                    {f"{stream.get('codec_type')}:{stream.get('codec_name')}" for stream in streams}
                )
                duration_delta = (
                    abs(duration * 1000 - asset.duration_ms) if asset.duration_ms is not None else None
                )
                results.append(
                    {
                        "asset_id": asset.asset_id,
                        "filename": asset.filename,
                        "status": "OK",
                        "duration_seconds": round(duration, 3),
                        "duration_delta_ms": round(duration_delta, 3) if duration_delta is not None else None,
                        "timestamps_seconds": [round(value, 3) for value in timestamps],
                        "frame_count": len(frames),
                        "frame_dimensions": dimensions,
                        "codecs": codecs,
                        "source_bytes": len(content),
                        "elapsed_seconds": round(time.perf_counter() - started, 3),
                        "bounded": 0 < len(frames) <= DEFAULT_MAX_FRAMES,
                    }
                )
            except Exception as exc:  # noqa: BLE001 - sanitized local verification report
                results.append(
                    {
                        "asset_id": asset.asset_id,
                        "filename": asset.filename,
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                    }
                )
            leftovers = [path.name for path in root.iterdir()]
            if leftovers:
                raise RuntimeError(f"Temporary cleanup failed: {leftovers}")

    successful = sum(result["status"] == "OK" for result in results)
    print(
        json.dumps(
            {
                "status": "OK" if successful == len(video_assets) else "FAILED",
                "ffmpeg_path": ffmpeg_path,
                "ffprobe_path": ffprobe_path,
                "videos_attempted": len(video_assets),
                "videos_successful": successful,
                "videos_failed": len(video_assets) - successful,
                "frames_generated": sum(int(result.get("frame_count", 0)) for result in results),
                "temporary_cleanup": "PASS",
                "external_ai_calls": 0,
                "database_writes": 0,
                "results": results,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if successful == len(video_assets) else 1


if __name__ == "__main__":
    raise SystemExit(main())
