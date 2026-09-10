"""Production Claude semantic interpretation provider.

This module is deliberately provider-only: it never writes semantic truth.  The
indexing orchestrator supplies evidence and receives a strictly validated,
18-layer response.  External inference is disabled unless explicitly enabled
for a trusted background worker and the caller has already passed its privacy
eligibility gate.
"""
from __future__ import annotations

import base64
import json
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx

LAYER_IDS = (
    "ASSET_IDENTITY_PROVENANCE", "GLOBAL_ASSET_UNDERSTANDING",
    "TEMPORAL_SCENE_STRUCTURE", "PEOPLE_ROLES", "PERSON_APPEARANCE",
    "ANATOMY", "TREATMENT_PROCEDURE", "ACTIONS_EVENTS", "RELATIONSHIPS",
    "CLINICAL_VISUAL_OBSERVATIONS", "ENVIRONMENT", "CINEMATOGRAPHY",
    "COMPOSITION", "SPEECH_TRANSCRIPT_AUDIO", "OCR_VISIBLE_TEXT",
    "MARKETING_CONTENT_USAGE", "SEMANTIC_NARRATIVE", "SEARCH_EMBEDDINGS",
)
STATES = {"OBSERVED", "FALSE", "UNKNOWN", "NOT_APPLICABLE"}


class ClaudeConfigurationError(RuntimeError):
    """Raised when a trusted worker is not safely configured."""


class ClaudeResponseError(RuntimeError):
    """Raised when Claude returns malformed or unsafe structured output."""


@dataclass(frozen=True)
class ClaudeConfig:
    api_key: str
    model: str
    enabled: bool
    endpoint: str = "https://api.anthropic.com/v1"
    max_retries: int = 3

    @classmethod
    def from_environment(cls) -> "ClaudeConfig":
        enabled = os.getenv("KDI_EXTERNAL_AI_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        provider = os.getenv("KDI_SEMANTIC_PROVIDER", "claude").strip().lower()
        if provider != "claude":
            raise ClaudeConfigurationError(f"unsupported production provider: {provider!r}")
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if enabled and not key:
            raise ClaudeConfigurationError("ANTHROPIC_API_KEY is required when external AI is enabled")
        model = os.getenv("KDI_CLAUDE_MODEL", "").strip()
        return cls(api_key=key, model=model, enabled=enabled)


class ClaudeSemanticProvider:
    """Calls Claude Messages API and validates the locked semantic contract."""

    def __init__(self, config: ClaudeConfig | None = None, client: httpx.Client | None = None) -> None:
        self.config = config or ClaudeConfig.from_environment()
        self.client = client or httpx.Client(timeout=httpx.Timeout(120.0, connect=20.0))
        self.usage: list[dict[str, Any]] = []
        self.retry_events: list[dict[str, Any]] = []

    def discover_model(self) -> str:
        if self.config.model:
            return self.config.model
        if not self.config.enabled:
            raise ClaudeConfigurationError("external AI is disabled for the production worker")
        response = self.client.get(
            f"{self.config.endpoint}/models",
            headers={"x-api-key": self.config.api_key, "anthropic-version": "2023-06-01"},
        )
        response.raise_for_status()
        models = response.json().get("data", [])
        candidates = [m.get("id", "") for m in models if "sonnet" in m.get("id", "").lower()]
        if not candidates:
            raise ClaudeConfigurationError("no available Claude Sonnet model was returned")
        # Prefer the currently approved stable Sonnet identifiers when present;
        # only fall back to the newest discovered Sonnet if the provider changes
        # its naming scheme.
        for preferred in ("claude-sonnet-4-6", "claude-sonnet-4-5-20250929"):
            if preferred in candidates:
                return preferred
        return sorted(candidates)[-1]

    LAYER_CONTRACT = (
        "Return one JSON object and nothing else. No prose, no markdown fence.\n"
        "Schema:\n"
        '{"narrative": "<two sentences describing only what the images show>",\n'
        ' "layers": [{"layer_id": "<one of the ids below>",\n'
        '             "state": "OBSERVED|FALSE|UNKNOWN|NOT_APPLICABLE",\n'
        '             "evaluated": true,\n'
        '             "display_text": "<short grounded phrase>",\n'
        '             "evidence": ["<what in the images or supplied text supports this>"]}]}\n'
        "Rules:\n"
        "- The layers array must contain exactly these 18 layer_id values, each exactly once:\n"
        "  {layers}\n"
        "- evaluated must always be true: it records that you examined the evidence.\n"
        "- OBSERVED means the evidence shows it. FALSE means the evidence shows its absence.\n"
        "  UNKNOWN means you examined the evidence and still cannot tell. NOT_APPLICABLE means the\n"
        "  layer cannot apply to this medium.\n"
        "- evidence must be a non-empty array for OBSERVED and FALSE.\n"
        "- Never name a clinical procedure (hair transplant, FUE, implantation, extraction, PRP,\n"
        "  injection, surgery) unless that exact procedure is named in the supplied text. Gloves,\n"
        "  instruments, a scalp or physical contact never by themselves establish a named procedure;\n"
        "  in that case TREATMENT_PROCEDURE is UNKNOWN.\n"
        "Evidence follows.\n"
    )

    @classmethod
    def _prompt(cls, evidence_text: str) -> str:
        return cls.LAYER_CONTRACT.replace("{layers}", ", ".join(LAYER_IDS)) + evidence_text

    @staticmethod
    def _payload(model: str, content: list[dict[str, Any]]) -> dict[str, Any]:
        """Request body for the Messages API.

        `temperature` is deliberately omitted: newer Sonnet models reject it outright, and the
        determinism this pipeline needs comes from fixed evidence and strict schema validation
        rather than from a sampling parameter.
        """
        return {"model": model, "max_tokens": 6000,
                "messages": [{"role": "user", "content": content}]}

    @staticmethod
    def _validate(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or not isinstance(value.get("layers"), list):
            raise ClaudeResponseError("response must contain a layers array")
        by_id: dict[str, dict[str, Any]] = {}
        for layer in value["layers"]:
            if not isinstance(layer, dict) or layer.get("layer_id") not in LAYER_IDS:
                raise ClaudeResponseError(
                    f"unsupported or malformed layer: {json.dumps(layer)[:200]}")
            if layer["layer_id"] in by_id:
                raise ClaudeResponseError("duplicate layer evaluation")
            if layer.get("state") not in STATES or layer.get("evaluated") is not True:
                raise ClaudeResponseError("every layer must be explicitly evaluated with a valid state")
            if not isinstance(layer.get("evidence"), list):
                raise ClaudeResponseError("each layer requires evidence references")
            by_id[layer["layer_id"]] = layer
        missing = set(LAYER_IDS) - set(by_id)
        if missing:
            raise ClaudeResponseError(f"missing layer evaluations: {sorted(missing)}")
        return {"layers": [by_id[x] for x in LAYER_IDS], "narrative": value.get("narrative", "")}

    MAX_IMAGES_PER_REQUEST = 20

    def analyze(self, *, asset_id: str, evidence_text: str, image_bytes: bytes | None = None,
                images: Sequence[bytes] | None = None, request_type: str = "asset") -> dict[str, Any]:
        """Evaluates the locked 18-layer contract over real visual evidence.

        A video is never transmitted. Callers pass the representative JPEG keyframes for the unit
        being evaluated (one scene, or a cross-scene sample for asset-level synthesis) via `images`;
        `image_bytes` remains supported for the single-frame image case.
        """
        if not self.config.enabled:
            raise ClaudeConfigurationError("external AI is disabled; refusing production inference")
        frames: list[bytes] = [x for x in (list(images) if images else []) if x]
        if image_bytes:
            frames.insert(0, image_bytes)
        if len(frames) > self.MAX_IMAGES_PER_REQUEST:
            # Keep a deterministic, evenly spaced sample so a long scene stays within request limits.
            step = len(frames) / self.MAX_IMAGES_PER_REQUEST
            frames = [frames[int(i * step)] for i in range(self.MAX_IMAGES_PER_REQUEST)]
        image_count = len(frames)
        model = self.discover_model()
        prompt = self._prompt(evidence_text)
        content: list[dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(frame).decode("ascii")}}
            for frame in frames
        ]
        content.append({"type": "text", "text": prompt})
        last: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            started = time.perf_counter()
            try:
                response = self.client.post(
                    f"{self.config.endpoint}/messages",
                    headers={"x-api-key": self.config.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json=self._payload(model, content),
                )
                response.raise_for_status()
                body = response.json()
                text = "".join(x.get("text", "") for x in body.get("content", []) if x.get("type") == "text")
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    # Models occasionally wrap otherwise valid JSON in a
                    # markdown fence or a short preamble. Extract the first
                    # balanced object, then validate it strictly below.
                    start = text.find("{")
                    end = text.rfind("}")
                    if start < 0 or end <= start:
                        raise
                    parsed = json.loads(text[start:end + 1])
                result = self._validate(parsed)
                result["provider"] = "claude"
                result["model"] = model
                result["asset_id"] = asset_id
                result["image_count"] = image_count
                self.usage.append({"asset_id": asset_id, "request_type": request_type, "model": model, "images": image_count,
                                   "attempt": attempt + 1, "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                                   "input_tokens": body.get("usage", {}).get("input_tokens", 0),
                                   "output_tokens": body.get("usage", {}).get("output_tokens", 0),
                                   "request_id": response.headers.get("request-id")})
                return result
            except (httpx.HTTPError, json.JSONDecodeError, ClaudeResponseError) as exc:
                last = exc
                if isinstance(exc, httpx.HTTPStatusError):
                    status = exc.response.status_code
                    if status in {401, 403}:
                        raise ClaudeConfigurationError(
                            f"Claude authentication/authorization failed with HTTP {status}"
                        ) from exc
                    if status not in {408, 409, 429} and not 500 <= status < 600:
                        detail = " ".join(exc.response.text.split())[:500]
                        raise ClaudeResponseError(f"non-retryable Claude HTTP {status}: {detail}") from exc
                    self.retry_events.append({"asset_id": asset_id, "status": status, "attempt": attempt + 1})
                elif isinstance(exc, httpx.HTTPError):
                    self.retry_events.append({"asset_id": asset_id, "status": "NETWORK", "attempt": attempt + 1})
                if attempt < self.config.max_retries:
                    retry_after = 0.0
                    if isinstance(exc, httpx.HTTPStatusError):
                        try:
                            retry_after = float(exc.response.headers.get("retry-after", "0"))
                        except ValueError:
                            retry_after = 0.0
                    # Full jitter prevents four workers from retrying in lock-step. Retry-After,
                    # when supplied by Anthropic, is always the lower bound.
                    time.sleep(max(retry_after, (2 ** attempt) + random.uniform(0.0, 1.0)))
        raise ClaudeResponseError(f"Claude analysis failed after retries: {last}")
