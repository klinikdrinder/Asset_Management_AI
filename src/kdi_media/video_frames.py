"""Representative-frame selection for video description generation.

The description provider must never receive a complete video file (see
DescriptionProvider in kdi_media.providers.base) - only a small number of
representative frames, extracted locally, are ever sent externally. This
module is the only place video bytes are decoded; nothing here performs a
network call.

Uses the `ffmpeg`/`ffprobe` command-line binaries via subprocess rather than
adding a new Python dependency: opencv-python/moviepy pull in a much heavier
footprint just to grab a handful of JPEG stills. Resolution prefers explicit
configuration, then the ignored project-local runtime, then PATH. The binaries
are not required to import this module because tests can inject an extractor.
"""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
from typing import Protocol

DEFAULT_MAX_FRAMES = 6
MAX_FRAME_DIMENSION = 1600


class FrameExtractionError(RuntimeError):
    """Raised when representative frames cannot be extracted from a video."""


class VideoFrameExtractor(Protocol):
    def extract_frames(self, video_bytes: bytes, *, max_frames: int) -> list[bytes]: ...


def resolve_media_executable(
    executable: str, *, environment_name: str, project_root: Path | None = None
) -> str:
    """Resolve explicit config, ignored project-local runtime, then PATH."""
    configured = os.environ.get(environment_name, "").strip()
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.is_file():
            raise FrameExtractionError(
                f"{environment_name} points to missing executable: {path}"
            )
        return str(path)

    root = project_root or Path(__file__).resolve().parents[2]
    names = (f"{executable}.exe", executable) if os.name == "nt" else (executable, f"{executable}.exe")
    for name in names:
        local = root / ".tools" / "ffmpeg" / "bin" / name
        if local.is_file():
            return str(local.resolve())

    system = shutil.which(executable)
    if system:
        return str(Path(system).resolve())
    raise FrameExtractionError(
        f"{executable} executable was not found via {environment_name}, "
        f"{root / '.tools' / 'ffmpeg' / 'bin'}, or system PATH"
    )


def resolve_ffmpeg_paths(*, project_root: Path | None = None) -> tuple[str, str]:
    return (
        resolve_media_executable(
            "ffmpeg", environment_name="KDI_FFMPEG_PATH", project_root=project_root
        ),
        resolve_media_executable(
            "ffprobe", environment_name="KDI_FFPROBE_PATH", project_root=project_root
        ),
    )


class FfmpegFrameExtractor:
    """Extracts up to `max_frames` evenly-spaced JPEG stills via ffmpeg.

    Efficient/representative by construction: frames are sampled at evenly
    spaced timestamps derived from the video's duration, not by decoding and
    inspecting every frame ("do not analyse every frame").
    """

    def __init__(self, *, ffmpeg_path: str | None = None, ffprobe_path: str | None = None) -> None:
        self.ffmpeg_path = ffmpeg_path or resolve_media_executable(
            "ffmpeg", environment_name="KDI_FFMPEG_PATH"
        )
        self.ffprobe_path = ffprobe_path or resolve_media_executable(
            "ffprobe", environment_name="KDI_FFPROBE_PATH"
        )

    def extract_frames(
        self, video_bytes: bytes, *, max_frames: int = DEFAULT_MAX_FRAMES
    ) -> list[bytes]:
        if max_frames < 1:
            raise ValueError("max_frames must be at least 1")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video_path = tmp_path / "source.bin"
            video_path.write_bytes(video_bytes)
            duration = self._probe_duration(video_path)
            frames: list[bytes] = []
            for index, timestamp in enumerate(self._evenly_spaced_timestamps(duration, max_frames)):
                frame_path = tmp_path / f"frame-{index}.jpg"
                self._extract_single_frame(video_path, timestamp, frame_path)
                if frame_path.exists():
                    frames.append(frame_path.read_bytes())
            if not frames:
                raise FrameExtractionError("No representative frames could be extracted")
            return frames

    def _probe_duration(self, video_path: Path) -> float:
        try:
            result = subprocess.run(
                [
                    self.ffprobe_path,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(video_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            return max(0.0, float(result.stdout.strip()))
        except (subprocess.SubprocessError, ValueError, OSError) as exc:
            raise FrameExtractionError(f"Could not determine video duration: {exc}") from exc

    @staticmethod
    def _evenly_spaced_timestamps(duration: float, max_frames: int) -> list[float]:
        if duration <= 0:
            return [0.0]
        # Avoid the very first/last instants, which are often black or mid-transition.
        margin = duration * 0.05
        span = max(0.0, duration - 2 * margin)
        if max_frames == 1:
            return [margin + span / 2]
        step = span / (max_frames - 1)
        return [margin + step * i for i in range(max_frames)]

    def _extract_single_frame(self, video_path: Path, timestamp: float, frame_path: Path) -> None:
        try:
            subprocess.run(
                [
                    self.ffmpeg_path,
                    "-ss", f"{timestamp:.3f}",
                    "-i", str(video_path),
                    "-frames:v", "1",
                    "-vf",
                    f"scale={MAX_FRAME_DIMENSION}:{MAX_FRAME_DIMENSION}:"
                    "force_original_aspect_ratio=decrease",
                    "-q:v", "3",
                    "-y", str(frame_path),
                ],
                capture_output=True,
                timeout=30,
                check=True,
            )
        except (subprocess.SubprocessError, OSError):
            return  # Skip an unreadable timestamp rather than failing the whole run.


def limit_transcript(text: str | None, *, max_chars: int = 2000) -> str | None:
    """Bounds transcript context before it is sent to the description
    provider. Returns None for missing/blank transcripts rather than an
    empty string, so callers can treat "no transcript" uniformly. Full
    transcripts are never stored in searchable_text or exposed to the
    frontend - only this bounded excerpt ever leaves this process boundary
    toward the description provider."""
    if text is None:
        return None
    normalized = " ".join(text.split())
    if not normalized:
        return None
    return normalized[:max_chars]
