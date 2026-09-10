"""Local/self-hosted multimodal provider for KDI semantic indexing.

SmolVLM2 is loaded exclusively from a local model directory.  No network
transport exists in this adapter; malformed/non-JSON output fails closed before
it can reach the semantic persistence layer.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Sequence

from .gemini_adapter import validate_gemini_result, GeminiSchemaError

LOCAL_PROVIDER_VERSION = "kdi_local_multimodal_analyzer_v1"
LOCAL_SCHEMA_VERSION = "kdi_local_semantic_schema_v1"
LOCAL_PROMPT_VERSION = "kdi_local_semantic_analysis_v1"

@dataclass(frozen=True)
class LocalAnalyzerConfig:
    model_path: Path
    model_id: str = "HuggingFaceTB/SmolVLM2-256M-Video-Instruct"
    revision: str = "main"
    device: str = "cpu"
    max_new_tokens: int = 768

class LocalSemanticAnalysisProvider:
    provider_name = "LOCAL"
    provider_version = LOCAL_PROVIDER_VERSION

    def __init__(self, config: LocalAnalyzerConfig) -> None:
        self.config = config
        if not config.model_path.exists():
            raise RuntimeError("LOCAL_MODEL_NOT_FOUND")
        try:
            from transformers import AutoProcessor, AutoModelForImageTextToText
            import torch
            self._torch = torch
            self._processor = AutoProcessor.from_pretrained(str(config.model_path), local_files_only=True)
            self._model = AutoModelForImageTextToText.from_pretrained(str(config.model_path), local_files_only=True, torch_dtype=torch.float32)
            self._model.eval()
        except Exception as exc:
            raise RuntimeError("LOCAL_MODEL_INITIALIZATION_FAILED") from exc

    def analyze_image(self, image: Any, *, duration_ms: int | None = None) -> dict[str, Any]:
        return self._infer([image], "<image> Return JSON only with exactly 18 ordered KDI layers. " + self._instruction(), duration_ms)

    def analyze_video_keyframes(self, frames: Sequence[Any], *, duration_ms: int) -> dict[str, Any]:
        if not frames: raise ValueError("NO_KEYFRAMES")
        prompt = " ".join(["<image>"] * len(frames)) + " Return JSON only with exactly 18 ordered KDI layers. " + self._instruction()
        return self._infer(list(frames), prompt, duration_ms)

    @staticmethod
    def _instruction() -> str:
        return "Use observable facts only, preserve UNKNOWN/FALSE/NOT_APPLICABLE semantics, and attach ASSET/FRAME/KEYFRAME/TIME_RANGE evidence to evaluated assertions."

    def _infer(self, images: list[Any], prompt: str, duration_ms: int | None) -> dict[str, Any]:
        inputs = self._processor(text=prompt, images=images, return_tensors="pt")
        with self._torch.no_grad():
            generated = self._model.generate(**inputs, max_new_tokens=self.config.max_new_tokens)
        text = self._processor.batch_decode(generated, skip_special_tokens=True)[0]
        start = text.find("{")
        if start < 0: raise GeminiSchemaError("LOCAL_NON_JSON_RESPONSE")
        try: payload = json.loads(text[start:])
        except json.JSONDecodeError as exc: raise GeminiSchemaError("LOCAL_NON_JSON_RESPONSE") from exc
        return validate_gemini_result(payload, duration_ms=duration_ms)
