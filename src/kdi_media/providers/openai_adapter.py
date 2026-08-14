"""OpenAI provider adapter: description generation (Responses API, strict
structured output) and embeddings (Embeddings API). The only AI provider
currently approved and registered - see kdi_media.providers.base for the
factory functions that construct these adapters and the provider-neutral
interfaces they implement. Nothing outside kdi_media.providers.base and this
module should import the openai SDK directly.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Sequence

from kdi_media.providers.base import (
    CONTROLLED_CONTENT_TYPES,
    AIProviderNotConfiguredError,
    DescriptionValidationError,
    ProviderPermanentError,
    ProviderRetryableError,
    StructuredMetadata,
    normalize_embedding_text,
    parse_structured_metadata,
)

PROVIDER_NAME = "openai"
CONNECT_TIMEOUT_SECONDS = 10.0
REQUEST_TIMEOUT_SECONDS = 30.0
SDK_MAX_RETRIES = 0  # SemanticIndexingWorker owns the bounded retry policy.

# The model only ever receives representative image frames plus a bounded
# transcript excerpt (see kdi_media.video_frames.limit_transcript) - never a
# complete video file.
DESCRIPTION_SYSTEM_PROMPT = (
    "You are labeling media for a hair transplant and aesthetics clinic's internal "
    "media library. Describe only what is visibly or audibly present in the "
    "supplied image frames and transcript excerpt. Never invent a doctor's name, "
    "treatment, or patient detail you are not confident about - return null for "
    "that field instead. Do not infer or state a patient's identity. Avoid medical "
    "conclusions and unsupported marketing claims. content_type MUST be exactly "
    "one of: " + ", ".join(CONTROLLED_CONTENT_TYPES) + ". short_caption must be one "
    "concise sentence suitable for a compact two-line grid card (no unsupported "
    "medical or marketing claims, do not repeat the filename). ai_description must "
    "be a more detailed factual sentence for a preview screen. Return only the "
    "approved fields; do not add any field outside the provided schema."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "content_type": {"type": "string", "enum": list(CONTROLLED_CONTENT_TYPES)},
        "treatment": {"type": ["string", "null"]},
        "subject": {"type": ["string", "null"]},
        "doctor_name": {"type": ["string", "null"]},
        "short_caption": {"type": ["string", "null"]},
        "ai_description": {"type": ["string", "null"]},
    },
    "required": [
        "content_type",
        "treatment",
        "subject",
        "doctor_name",
        "short_caption",
        "ai_description",
    ],
    "additionalProperties": False,
}


def _required_config(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AIProviderNotConfiguredError(
            f"AI_DESCRIPTION_PROVIDER/AI_EMBEDDING_PROVIDER=openai requires {name} to be set."
        )
    return value


def build_description_provider() -> "OpenAIDescriptionAdapter":
    """Constructs the description adapter from environment configuration.
    Called only from kdi_media.providers.base.get_description_provider()."""
    api_key = _required_config("OPENAI_API_KEY")
    model = _required_config("OPENAI_DESCRIPTION_MODEL")
    schema_version = os.environ.get("OPENAI_DESCRIPTION_SCHEMA_VERSION", "v1").strip() or "v1"
    return OpenAIDescriptionAdapter(api_key=api_key, model=model, schema_version=schema_version)


def build_embedding_provider() -> "OpenAIEmbeddingAdapter":
    """Constructs the embedding adapter from environment configuration.
    Called only from kdi_media.providers.base.get_embedding_provider()."""
    api_key = _required_config("OPENAI_API_KEY")
    model = _required_config("OPENAI_EMBEDDING_MODEL")
    dimensions_raw = _required_config("OPENAI_EMBEDDING_DIMENSIONS")
    try:
        dimensions = int(dimensions_raw)
    except ValueError as exc:
        raise AIProviderNotConfiguredError("OPENAI_EMBEDDING_DIMENSIONS must be an integer") from exc
    if dimensions <= 0:
        raise AIProviderNotConfiguredError("OPENAI_EMBEDDING_DIMENSIONS must be positive")
    version = os.environ.get("OPENAI_EMBEDDING_VERSION", "v1").strip() or "v1"
    return OpenAIEmbeddingAdapter(api_key=api_key, model=model, dimensions=dimensions, version=version)


def _client(api_key: str) -> Any:
    import httpx
    from openai import OpenAI  # deferred import: keep the SDK optional at module load

    return OpenAI(
        api_key=api_key,
        timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS),
        max_retries=SDK_MAX_RETRIES,
    )


class OpenAIDescriptionAdapter:
    """DescriptionProvider backed by the OpenAI Responses API with strict
    structured JSON output (`additionalProperties: false`, all fields
    required-but-nullable). Accepts representative image frames plus an
    optional, already-length-limited transcript excerpt - never raw video
    bytes; the type signature itself makes that impossible to pass."""

    provider_name = PROVIDER_NAME

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        schema_version: str,
        client: Any | None = None,
    ) -> None:
        self.model_name = model
        self.schema_version = schema_version
        self._client = client if client is not None else _client(api_key)

    def describe_media(
        self,
        *,
        file_name: str,
        mime_type: str,
        media_category: str,
        images: Sequence[bytes],
        transcript: str | None = None,
    ) -> tuple[StructuredMetadata, float | None]:
        if not images:
            raise ProviderPermanentError(
                "describe_media requires at least one representative image frame"
            )

        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": (
                    f"File name: {file_name}\nMedia category: {media_category}\n"
                    + (f"Transcript excerpt: {transcript}\n" if transcript else "")
                    + "Return the metadata contract as JSON matching the provided schema."
                ),
            }
        ]
        for image_bytes in images:
            encoded = base64.b64encode(image_bytes).decode("ascii")
            content.append({"type": "input_image", "image_url": f"data:image/jpeg;base64,{encoded}"})

        try:
            response = self._client.responses.create(
                model=self.model_name,
                instructions=DESCRIPTION_SYSTEM_PROMPT,
                input=[{"role": "user", "content": content}],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "kdi_asset_metadata",
                        "schema": RESPONSE_SCHEMA,
                        "strict": True,
                    }
                },
            )
        except Exception as exc:
            raise _classify_openai_error(exc) from exc

        raw = _parse_json_response(getattr(response, "output_text", None))
        metadata = parse_structured_metadata(raw)
        return metadata, _estimate_description_cost(response)


class OpenAIEmbeddingAdapter:
    """EmbeddingProvider backed by the OpenAI Embeddings API. Requests and
    strictly validates an exact fixed dimension - never truncates or pads a
    mismatched vector, rejects it instead (ProviderPermanentError)."""

    provider_name = PROVIDER_NAME

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int,
        version: str,
        client: Any | None = None,
    ) -> None:
        self.model_name = model
        self.embedding_dimensions = dimensions
        self.version = version
        self._client = client if client is not None else _client(api_key)

    def embed_text(self, text: str) -> tuple[list[float], float | None]:
        normalized = normalize_embedding_text(text)
        if not normalized:
            raise ProviderPermanentError("Cannot embed empty or invalid text")

        try:
            response = self._client.embeddings.create(
                model=self.model_name,
                input=normalized,
                dimensions=self.embedding_dimensions,
            )
        except Exception as exc:
            raise _classify_openai_error(exc) from exc

        rows = getattr(response, "data", None) or []
        if not rows:
            raise ProviderPermanentError("Embedding response contained no vectors")
        values = list(rows[0].embedding)
        if len(values) != self.embedding_dimensions:
            raise ProviderPermanentError(
                f"Embedding dimension mismatch: expected {self.embedding_dimensions}, got {len(values)}"
            )
        return values, _estimate_embedding_cost(response)

    def embed_batch(self, texts: Sequence[str]) -> list[tuple[list[float], float | None]]:
        """Batches multiple texts into one request where safe. Falls back to
        one embed_text() call per item if any input would normalize to
        empty, so a single bad item cannot silently misalign the rest."""
        normalized = [normalize_embedding_text(text) for text in texts]
        if not normalized or any(not text for text in normalized):
            return [self.embed_text(text) for text in texts]

        try:
            response = self._client.embeddings.create(
                model=self.model_name,
                input=normalized,
                dimensions=self.embedding_dimensions,
            )
        except Exception as exc:
            raise _classify_openai_error(exc) from exc

        rows = getattr(response, "data", None) or []
        if len(rows) != len(normalized):
            raise ProviderPermanentError("Embedding batch response size did not match request size")
        cost = _estimate_embedding_cost(response)
        per_item_cost = (cost / len(rows)) if cost else None
        results: list[tuple[list[float], float | None]] = []
        for row in rows:
            values = list(row.embedding)
            if len(values) != self.embedding_dimensions:
                raise ProviderPermanentError(
                    f"Embedding dimension mismatch: expected {self.embedding_dimensions}, got {len(values)}"
                )
            results.append((values, per_item_cost))
        return results


def _parse_json_response(text: str | None) -> Any:
    if not text:
        raise DescriptionValidationError("Model returned an empty response")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DescriptionValidationError("Model response was not valid JSON") from exc


def _classify_openai_error(exc: Exception) -> Exception:
    """Maps an openai SDK exception to ProviderRetryableError/
    ProviderPermanentError. Falls back to retryable for anything
    unrecognized, matching the worker's default-retry behavior."""
    try:
        import openai
    except ImportError:
        return ProviderRetryableError(_sanitize(str(exc)))

    if isinstance(
        exc,
        (
            openai.AuthenticationError,
            openai.PermissionDeniedError,
            openai.BadRequestError,
            openai.NotFoundError,
        ),
    ):
        return ProviderPermanentError(_sanitize(str(exc)))
    if isinstance(exc, (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)):
        return ProviderRetryableError(_sanitize(str(exc)))
    if isinstance(exc, openai.APIStatusError):
        status_code = getattr(exc, "status_code", 500)
        if 400 <= status_code < 500 and status_code != 429:
            return ProviderPermanentError(_sanitize(str(exc)))
        return ProviderRetryableError(_sanitize(str(exc)))
    return ProviderRetryableError(_sanitize(str(exc)))


def _sanitize(value: str) -> str:
    # Defense in depth: never let a key/token leak into a stored failure
    # reason even if an SDK error message were to echo request headers.
    clean = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    for marker in ("Bearer ", "sk-"):
        index = clean.find(marker)
        if index != -1:
            clean = clean[:index] + "[redacted]"
    return clean[:500]


def _estimate_description_cost(response: Any) -> float | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    # Placeholder linear estimate; tune against actual OpenAI pricing during the pilot.
    return round((input_tokens * 0.0000005) + (output_tokens * 0.0000015), 6)


def _estimate_embedding_cost(response: Any) -> float | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    tokens = getattr(usage, "total_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0
    return round(tokens * 0.00000002, 6)
