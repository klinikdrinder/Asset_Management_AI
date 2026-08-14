"""Loopback-only Ollama adapters for KDI metadata and embeddings."""

from __future__ import annotations

import base64
import json
import math
import os
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from kdi_media.providers.base import (
    AIProviderNotConfiguredError, AI_DESCRIPTION_MAX_LEN, CONTROLLED_CONTENT_TYPES,
    ProviderPermanentError, ProviderRetryableError, SHORT_CAPTION_MAX_LEN,
    StructuredMetadata, normalize_embedding_text, parse_structured_metadata,
)

PROVIDER_NAME = "ollama"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_EMBEDDING_CONTEXT_LENGTH = 2048
DEFAULT_EMBEDDING_BATCH_SIZE = 32
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "content_type": {"type": ["string", "null"], "enum": [*CONTROLLED_CONTENT_TYPES, None]},
        "treatment": {"type": ["string", "null"]},
        "subject": {"type": ["string", "null"]},
        "doctor_name": {"type": ["string", "null"]},
        "ai_description": {"type": "string", "maxLength": AI_DESCRIPTION_MAX_LEN},
        "short_caption": {"type": "string", "maxLength": SHORT_CAPTION_MAX_LEN},
    },
    "required": ["content_type", "treatment", "subject", "doctor_name", "ai_description", "short_caption"],
    "additionalProperties": False,
}

DESCRIPTION_PROMPT = """You are cataloguing business media for internal semantic search.
Describe only what is supported by the supplied prepared media frames and trusted context.
Return exactly the JSON schema fields. Use the broadest accurate description when uncertain.
Do not guess treatments, procedures, doctor identities, patient identities, outcomes, or diagnoses.
A specific treatment name requires strong explicit evidence; visible injections alone do not establish PRP.
Doctor identity requires reliable non-biometric evidence; never identify a person from appearance.
Use null for treatment or doctor_name whenever evidence is insufficient. Do not infer consent,
marketing approval, or public-use status. Descriptions must be factual, neutral, concise, and useful
for search, without promotional claims. If no clinic or treatment context is supported, use
content_type "Other" and do not describe the media as medical."""


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AIProviderNotConfiguredError(f"Ollama provider requires {name} to be set")
    return value


def _base_url() -> str:
    value = os.environ.get("OLLAMA_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in LOCAL_HOSTS or parsed.port != 11434:
        raise AIProviderNotConfiguredError("OLLAMA_BASE_URL must be loopback HTTP on port 11434")
    return value


def _timeout() -> float:
    try:
        value = float(os.environ.get("OLLAMA_REQUEST_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    except ValueError as exc:
        raise AIProviderNotConfiguredError("OLLAMA_REQUEST_TIMEOUT_SECONDS must be numeric") from exc
    if not 1 <= value <= 600:
        raise AIProviderNotConfiguredError("OLLAMA_REQUEST_TIMEOUT_SECONDS must be between 1 and 600")
    return value


class OllamaClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url
        self.timeout = timeout

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(f"{self.base_url}{path}", data=json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - loopback enforced
                raw = response.read()
        except HTTPError as exc:
            detail = _safe(exc.read().decode("utf-8", "replace"))
            if exc.code == 404:
                raise ProviderPermanentError(f"Ollama model or endpoint missing: {detail}") from exc
            raise ProviderRetryableError(f"Ollama HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderRetryableError(f"Local Ollama unavailable: {_safe(str(exc))}") from exc
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderRetryableError("Ollama returned malformed JSON") from exc
        if not isinstance(result, dict):
            raise ProviderRetryableError("Ollama response was not a JSON object")
        return result


class OllamaDescriptionAdapter:
    provider_name = PROVIDER_NAME

    def __init__(self, *, model: str, schema_version: str, client: OllamaClient) -> None:
        self.model_name, self.schema_version, self._client = model, schema_version, client

    def describe_media(self, *, file_name: str, mime_type: str, media_category: str,
                       images: Sequence[bytes], transcript: str | None = None) -> tuple[StructuredMetadata, float | None]:
        if not images:
            raise ProviderPermanentError("describe_media requires at least one prepared image")
        context = f"Media category: {media_category}."
        if transcript:
            context += f" Bounded transcript context: {transcript}"
        response = self._client.post("/api/chat", {
            "model": self.model_name,
            "messages": [{"role": "user", "content": f"{DESCRIPTION_PROMPT}\n{context}",
                          "images": [base64.b64encode(image).decode("ascii") for image in images]}],
            "format": RESPONSE_SCHEMA, "stream": False,
            "options": {"temperature": 0}, "keep_alive": 0,
        })
        content = (response.get("message") or {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderRetryableError("Ollama vision response contained no structured content")
        try:
            raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderRetryableError("Ollama vision response was not valid JSON") from exc
        return parse_structured_metadata(raw), None


class OllamaEmbeddingAdapter:
    provider_name = PROVIDER_NAME

    def __init__(self, *, model: str, dimensions: int, version: str,
                 context_length: int, batch_size: int, client: OllamaClient) -> None:
        self.model_name, self.embedding_dimensions, self.version = model, dimensions, version
        self.context_length = context_length
        self.batch_size = batch_size
        self._client = client

    def embed_text(self, text: str) -> tuple[list[float], float | None]:
        normalized = normalize_embedding_text(text)
        if not normalized:
            raise ProviderPermanentError("Cannot embed empty or invalid text")
        response = self._client.post("/api/embed", {"model": self.model_name, "input": normalized,
                                     "dimensions": self.embedding_dimensions, "truncate": False,
                                     "options": {"num_ctx": self.context_length,
                                                 "num_batch": self.batch_size}, "keep_alive": 0})
        rows = response.get("embeddings")
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], list):
            raise ProviderRetryableError("Ollama embedding response contained no vector")
        values = rows[0]
        if len(values) != self.embedding_dimensions:
            raise ProviderPermanentError(f"Embedding dimension mismatch: expected {self.embedding_dimensions}, got {len(values)}")
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
            raise ProviderPermanentError("Embedding contained non-numeric or non-finite values")
        return [float(value) for value in values], None


def build_description_provider() -> OllamaDescriptionAdapter:
    return OllamaDescriptionAdapter(model=_required("OLLAMA_VISION_MODEL"),
        schema_version=os.environ.get("OLLAMA_DESCRIPTION_VERSION", "v1").strip() or "v1",
        client=OllamaClient(_base_url(), _timeout()))


def build_embedding_provider() -> OllamaEmbeddingAdapter:
    try:
        dimensions = int(_required("OLLAMA_EMBEDDING_DIMENSIONS"))
    except ValueError as exc:
        raise AIProviderNotConfiguredError("OLLAMA_EMBEDDING_DIMENSIONS must be an integer") from exc
    if dimensions <= 0:
        raise AIProviderNotConfiguredError("OLLAMA_EMBEDDING_DIMENSIONS must be positive")
    try:
        context_length = int(os.environ.get(
            "OLLAMA_EMBEDDING_CONTEXT_LENGTH", str(DEFAULT_EMBEDDING_CONTEXT_LENGTH)))
    except ValueError as exc:
        raise AIProviderNotConfiguredError("OLLAMA_EMBEDDING_CONTEXT_LENGTH must be an integer") from exc
    if not 256 <= context_length <= 32768:
        raise AIProviderNotConfiguredError(
            "OLLAMA_EMBEDDING_CONTEXT_LENGTH must be between 256 and 32768")
    try:
        batch_size = int(os.environ.get(
            "OLLAMA_EMBEDDING_BATCH_SIZE", str(DEFAULT_EMBEDDING_BATCH_SIZE)))
    except ValueError as exc:
        raise AIProviderNotConfiguredError("OLLAMA_EMBEDDING_BATCH_SIZE must be an integer") from exc
    if not 1 <= batch_size <= 512:
        raise AIProviderNotConfiguredError("OLLAMA_EMBEDDING_BATCH_SIZE must be between 1 and 512")
    return OllamaEmbeddingAdapter(model=_required("OLLAMA_EMBEDDING_MODEL"), dimensions=dimensions,
        version=os.environ.get("OLLAMA_EMBEDDING_VERSION", "v1").strip() or "v1",
        context_length=context_length,
        batch_size=batch_size,
        client=OllamaClient(_base_url(), _timeout()))


def _safe(value: str) -> str:
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())[:500]
