"""Provider-neutral Gemini multimodal semantic-analysis adapter.

The adapter is deliberately side-effect free until ``analyze_media`` is called.
It keeps vendor details out of the indexing/database layers and rejects output
that is not the frozen 18-layer contract.  Credentials are read only from the
process environment; values are never included in errors or telemetry.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Callable, Mapping

from .base import ProviderPermanentError, ProviderRetryableError

GEMINI_PROVIDER_VERSION = "kdi_gemini_provider_v1"
GEMINI_SCHEMA_VERSION = "kdi_gemini_semantic_schema_v1"
GEMINI_PROMPT_VERSION = "kdi_gemini_semantic_analysis_v1"
DEFAULT_IMAGE_MODEL = "gemini-2.5-flash"
DEFAULT_VIDEO_MODEL = "gemini-2.5-flash"
LAYER_IDS = tuple(f"LAYER_{i:02d}" for i in range(1, 19))
ALLOWED_STATES = frozenset({"OBSERVED", "FALSE", "UNKNOWN", "NOT_APPLICABLE"})
EVIDENCE_TYPES = frozenset({"ASSET", "SCENE", "FRAME", "KEYFRAME", "TIME_RANGE", "TRANSCRIPT", "OCR", "METADATA"})


class GeminiConfigurationError(ProviderPermanentError):
    pass


class GeminiSchemaError(ProviderPermanentError):
    pass


@dataclass(frozen=True)
class GeminiConfig:
    api_key: str
    image_model: str
    video_model: str
    schema_version: str = GEMINI_SCHEMA_VERSION
    prompt_version: str = GEMINI_PROMPT_VERSION
    provider_version: str = GEMINI_PROVIDER_VERSION
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> "GeminiConfig":
        key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_GEMINI_API_KEY") or "").strip()
        if not key:
            raise GeminiConfigurationError("GEMINI_CREDENTIAL_NOT_CONFIGURED")
        image = (os.getenv("GEMINI_IMAGE_ANALYSIS_MODEL") or DEFAULT_IMAGE_MODEL).strip()
        video = (os.getenv("GEMINI_VIDEO_ANALYSIS_MODEL") or DEFAULT_VIDEO_MODEL).strip()
        if not image or not video:
            raise GeminiConfigurationError("GEMINI_MODEL_NOT_CONFIGURED")
        return cls(key, image, video)


def semantic_response_schema() -> dict[str, Any]:
    """Schema sent to Gemini structured-output mode."""
    evidence = {
        "type": "array",
        "items": {"type": "object", "properties": {
            "evidence_type": {"type": "string", "enum": sorted(EVIDENCE_TYPES)},
            "timestamp_ms": {"type": "integer", "minimum": 0},
            "start_ms": {"type": "integer", "minimum": 0},
            "end_ms": {"type": "integer", "minimum": 0},
            "scene_id": {"type": "string"}, "keyframe_id": {"type": "string"},
            "note": {"type": "string"},
        }, "required": ["evidence_type"]},
    }
    assertion = {"type": "object", "properties": {
        "concept": {"type": "string"}, "value": {},
        "state": {"type": "string", "enum": sorted(ALLOWED_STATES)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence": evidence,
    }, "required": ["concept", "state", "evidence"]}
    layer = {"type": "object", "properties": {
        "layer_id": {"type": "string", "enum": list(LAYER_IDS)},
        "layer_number": {"type": "integer", "minimum": 1, "maximum": 18},
        "status": {"type": "string", "enum": sorted(ALLOWED_STATES)},
        "assertions": {"type": "array", "items": assertion},
        "notes": {"type": "string"},
        "limitations": {"type": "string"},
    }, "required": ["layer_id", "layer_number", "status", "assertions"]}
    return {"type": "object", "properties": {
        "layers": {"type": "array", "minItems": 18, "maxItems": 18, "items": layer},
        "short_description": {"type": "string"},
        "semantic_narrative": {"type": "string"},
    }, "required": ["layers", "short_description", "semantic_narrative"]}


def validate_gemini_result(result: Mapping[str, Any], *, duration_ms: int | None = None) -> dict[str, Any]:
    """Normalize and strictly validate a provider response before persistence."""
    if not isinstance(result, Mapping) or not isinstance(result.get("layers"), list):
        raise GeminiSchemaError("GEMINI_RESPONSE_NOT_OBJECT")
    layers = result["layers"]
    if len(layers) != 18:
        raise GeminiSchemaError("INVALID_LAYER_COUNT")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, layer in enumerate(layers, 1):
        if not isinstance(layer, Mapping) or layer.get("layer_id") not in LAYER_IDS:
            raise GeminiSchemaError("INVALID_LAYER_ID")
        if layer["layer_id"] in seen or layer.get("layer_number") != index:
            raise GeminiSchemaError("AMBIGUOUS_LAYER_MAPPING")
        seen.add(layer["layer_id"])
        status = layer.get("status")
        if status not in ALLOWED_STATES or not isinstance(layer.get("assertions"), list):
            raise GeminiSchemaError("INVALID_LAYER_STATE")
        assertions: list[dict[str, Any]] = []
        for assertion in layer["assertions"]:
            if not isinstance(assertion, Mapping) or assertion.get("state") not in ALLOWED_STATES:
                raise GeminiSchemaError("INVALID_ASSERTION_STATE")
            evidence = assertion.get("evidence") or []
            if assertion["state"] in {"OBSERVED", "FALSE"} and not evidence:
                raise GeminiSchemaError("EVIDENCE_REQUIRED")
            for ev in evidence:
                if not isinstance(ev, Mapping) or ev.get("evidence_type") not in EVIDENCE_TYPES:
                    raise GeminiSchemaError("INVALID_EVIDENCE_TYPE")
                start, end, ts = ev.get("start_ms"), ev.get("end_ms"), ev.get("timestamp_ms")
                if any(isinstance(v, int) and v < 0 for v in (start, end, ts)):
                    raise GeminiSchemaError("NEGATIVE_TIMESTAMP")
                if isinstance(start, int) and isinstance(end, int) and end < start:
                    raise GeminiSchemaError("INVALID_TIME_RANGE")
                if duration_ms is not None and any(isinstance(v, int) and v > duration_ms for v in (start, end, ts)):
                    raise GeminiSchemaError("TIMESTAMP_OUT_OF_RANGE")
            assertions.append(dict(assertion))
        normalized.append({**dict(layer), "assertions": assertions})
    if seen != set(LAYER_IDS):
        raise GeminiSchemaError("INCOMPLETE_LAYER_SET")
    return {**dict(result), "layers": normalized, "provider": "GEMINI", "schema_version": GEMINI_SCHEMA_VERSION}


def default_prompt() -> str:
    return ("Return JSON only using the supplied schema. Evaluate observable media facts only. "
            "Return all exactly 18 layers in order. Preserve UNKNOWN, FALSE, and NOT_APPLICABLE "
            "semantics; FALSE requires evaluated negative evidence. Ground visual claims with "
            "ASSET/SCENE/FRAME/KEYFRAME/TIME_RANGE evidence and never infer identity or unsupported clinical facts.")


class GeminiSemanticAnalysisProvider:
    """Real Gemini adapter with injectable transport for deterministic tests."""
    provider_name = "GEMINI"
    provider_version = GEMINI_PROVIDER_VERSION

    def __init__(self, config: GeminiConfig | None = None, *, transport: Callable[..., Any] | None = None) -> None:
        self.config = config or GeminiConfig.from_env()
        self._transport = transport
        self.last_usage: dict[str, Any] | None = None

    def analyze_media(self, *, media: bytes, mime_type: str, media_category: str,
                      duration_ms: int | None = None) -> dict[str, Any]:
        if media_category not in {"image", "video"}:
            raise GeminiConfigurationError("UNSUPPORTED_MEDIA_CATEGORY")
        model = self.config.image_model if media_category == "image" else self.config.video_model
        payload = {"model": model, "mime_type": mime_type, "media": media,
                   "prompt": default_prompt(), "schema": semantic_response_schema()}
        try:
            raw = self._transport(payload) if self._transport else self._sdk_request(payload)
        except (TimeoutError, ConnectionError) as exc:
            raise ProviderRetryableError("GEMINI_TRANSIENT_FAILURE") from exc
        except GeminiSchemaError:
            raise
        except Exception as exc:
            raise GeminiConfigurationError("GEMINI_REQUEST_FAILED") from exc
        if isinstance(raw, str):
            try: raw = json.loads(raw)
            except json.JSONDecodeError as exc: raise GeminiSchemaError("GEMINI_NON_JSON_RESPONSE") from exc
        return validate_gemini_result(raw, duration_ms=duration_ms)

    def _sdk_request(self, payload: Mapping[str, Any]) -> Any:
        try:
            from google import genai  # type: ignore
            from google.genai import types  # type: ignore
        except ImportError as exc:
            raise GeminiConfigurationError("GEMINI_SDK_NOT_INSTALLED") from exc
        client = genai.Client(api_key=self.config.api_key)
        response = client.models.generate_content(
            model=payload["model"],
            contents=[types.Part.from_bytes(data=payload["media"], mime_type=payload["mime_type"]), payload["prompt"]],
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=semantic_response_schema()),
        )
        self.last_usage = getattr(response, "usage_metadata", None) or None
        text = getattr(response, "text", None)
        if not text: raise GeminiSchemaError("GEMINI_EMPTY_RESPONSE")
        return json.loads(text)
