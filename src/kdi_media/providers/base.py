"""Provider-neutral interfaces for AI-generated search metadata and embeddings.

get_description_provider()/get_embedding_provider() read
AI_DESCRIPTION_PROVIDER/AI_EMBEDDING_PROVIDER from the environment and
construct the matching adapter, or raise AIProviderNotConfiguredError with a
clear, credential-free message when unset/unrecognized. kdi_media.semantic_
indexing and the CLI treat that as a distinct "not configured" state, not a
per-asset failure.

Concrete adapters are registered for local Ollama (the approved production
provider) and explicit optional OpenAI use. Adding another provider means
implementing DescriptionProvider/EmbeddingProvider in a sibling module and
adding one branch to the two factory functions below; the worker and CLI stay
provider-neutral.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Protocol, Sequence

CONTROLLED_CONTENT_TYPES = (
    "Before & After",
    "Treatment Result",
    "Patient Testimonial",
    "Doctor Explanation",
    "Treatment Procedure",
    "Consultation",
    "Educational Video",
    "Clinic Environment",
    "Promotional Content",
    "Doctor Talking",
    "Patient Interview",
    "Other",
)

ALLOWED_METADATA_FIELDS = frozenset(
    {"content_type", "treatment", "subject", "doctor_name", "short_caption", "ai_description"}
)

SHORT_CAPTION_MAX_LEN = 200
AI_DESCRIPTION_MAX_LEN = 1000
EMBEDDING_TEXT_MAX_LEN = 4000


class DescriptionValidationError(ValueError):
    """Raised when a model response cannot be validated against the metadata contract."""


class AIProviderNotConfiguredError(RuntimeError):
    """Raised when no AI description/embedding provider has been configured.

    This is a configuration state, not a per-asset failure: callers (the CLI,
    the worker) should surface it distinctly - e.g. exit early with a clear
    message - rather than marking individual assets FAILED_* and retrying.
    Never includes a credential value.
    """


class ProviderRetryableError(RuntimeError):
    """Raised by a provider adapter for a transient failure: timeout, rate
    limit, transient connection error. The worker retries with backoff."""


class ProviderPermanentError(RuntimeError):
    """Raised by a provider adapter for a non-retryable failure: auth
    failure, invalid request shape, incompatible embedding dimensions. The
    worker does not retry."""


@dataclass(frozen=True)
class StructuredMetadata:
    content_type: str
    treatment: str | None
    subject: str | None
    doctor_name: str | None
    short_caption: str
    ai_description: str

    def __post_init__(self) -> None:
        if self.content_type not in CONTROLLED_CONTENT_TYPES:
            raise DescriptionValidationError(
                f"content_type {self.content_type!r} is not in the controlled list"
            )
        if not self.short_caption.strip():
            raise DescriptionValidationError("short_caption must be a useful non-empty string")
        if len(self.short_caption) > SHORT_CAPTION_MAX_LEN:
            raise DescriptionValidationError("short_caption exceeds the maximum length")
        if not self.ai_description.strip():
            raise DescriptionValidationError("ai_description must be a useful non-empty string")
        if len(self.ai_description) > AI_DESCRIPTION_MAX_LEN:
            raise DescriptionValidationError("ai_description exceeds the maximum length")


def parse_structured_metadata(raw: Any) -> StructuredMetadata:
    """Validate/normalize a raw model JSON response into StructuredMetadata.

    Never fabricates: any field the model did not confidently provide is
    stored as null rather than guessed. content_type falls back to 'Other'
    when the model's answer does not match the controlled list, rather than
    letting the model invent a new category. Any field outside the approved
    six-field contract is rejected outright (defense in depth alongside the
    strict JSON-schema request sent to the model).
    """
    if not isinstance(raw, dict):
        raise DescriptionValidationError("Model response was not a JSON object")

    extra_fields = set(raw.keys()) - ALLOWED_METADATA_FIELDS
    if extra_fields:
        raise DescriptionValidationError(
            f"Model response contained unapproved fields: {sorted(extra_fields)}"
        )

    def optional_text(key: str, max_len: int | None = None) -> str | None:
        value = raw.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise DescriptionValidationError(f"{key} must be a string or null")
        text = value.strip()
        if not text:
            return None
        if text.casefold() in {"unknown", "n/a", "not visible"}:
            return None
        if max_len and len(text) > max_len:
            raise DescriptionValidationError(f"{key} exceeds the maximum length")
        return text

    def required_text(key: str, max_len: int) -> str:
        value = optional_text(key, max_len)
        if value is None:
            raise DescriptionValidationError(f"{key} must be a useful non-empty string")
        return value

    content_type = raw.get("content_type")
    if not isinstance(content_type, str) or content_type not in CONTROLLED_CONTENT_TYPES:
        content_type = "Other"

    return StructuredMetadata(
        content_type=content_type,
        treatment=optional_text("treatment"),
        subject=optional_text("subject"),
        doctor_name=optional_text("doctor_name"),
        short_caption=required_text("short_caption", SHORT_CAPTION_MAX_LEN),
        ai_description=required_text("ai_description", AI_DESCRIPTION_MAX_LEN),
    )


def normalize_embedding_text(text: str, *, max_len: int = EMBEDDING_TEXT_MAX_LEN) -> str:
    """Deterministic normalization shared by asset-text and query-text
    embedding. The Next.js query-embedding path (app/lib/media/search.ts)
    implements the identical rule (trim, collapse whitespace, cap length) -
    keep the two in sync if this changes."""
    return " ".join(text.split())[:max_len]


class DescriptionProvider(Protocol):
    """Generates structured metadata for one asset's media content.

    Only representative image frames (plus optional limited transcript
    text) are ever passed in - never a complete video file. Self-reported
    attributes let the worker record exactly which provider/model/schema
    version produced each row without hardcoding a vendor name.
    """

    provider_name: str
    model_name: str
    schema_version: str

    def describe_media(
        self,
        *,
        file_name: str,
        mime_type: str,
        media_category: str,
        images: Sequence[bytes],
        transcript: str | None = None,
    ) -> tuple[StructuredMetadata, float | None]:
        """Return validated structured metadata and a cost-in-USD estimate (or None)."""
        ...


class EmbeddingProvider(Protocol):
    """Generates an embedding vector for a text string.

    embedding_dimensions is the provider's configured, expected output size;
    adapters must validate the actual response against it and raise
    ProviderPermanentError on any mismatch - never truncate or pad a vector.
    """

    provider_name: str
    model_name: str
    embedding_dimensions: int
    version: str

    def embed_text(self, text: str) -> tuple[list[float], float | None]:
        """Return an embedding vector and a cost-in-USD estimate (or None)."""
        ...


def get_description_provider() -> DescriptionProvider:
    """Look up and construct the configured description provider.

    Reads AI_DESCRIPTION_PROVIDER and constructs the explicitly selected
    registered adapter. Raises AIProviderNotConfiguredError -
    never a vendor SDK exception - when unset, unrecognized, or missing its
    own required configuration (e.g. OPENAI_API_KEY), so callers get one
    consistent, credential-free error type to handle.
    """
    provider_name = os.environ.get("AI_DESCRIPTION_PROVIDER", "").strip().lower()
    if not provider_name:
        raise AIProviderNotConfiguredError(
            "No AI description provider is configured. Set AI_DESCRIPTION_PROVIDER "
            "to enable natural-language search metadata generation."
        )
    if provider_name == "openai":
        from kdi_media.providers.openai_adapter import build_description_provider

        return build_description_provider()
    if provider_name == "ollama":
        from kdi_media.providers.ollama_adapter import build_description_provider

        return build_description_provider()
    raise AIProviderNotConfiguredError(
        f"AI_DESCRIPTION_PROVIDER={provider_name!r} has no registered adapter."
    )


def get_embedding_provider() -> EmbeddingProvider:
    """Look up and construct the configured embedding provider.

    Reads AI_EMBEDDING_PROVIDER and constructs the explicitly selected
    registered adapter. Same not-configured contract as
    get_description_provider().
    """
    provider_name = os.environ.get("AI_EMBEDDING_PROVIDER", "").strip().lower()
    if not provider_name:
        raise AIProviderNotConfiguredError(
            "No AI embedding provider is configured. Set AI_EMBEDDING_PROVIDER "
            "to enable embedding generation for natural-language search."
        )
    if provider_name == "openai":
        from kdi_media.providers.openai_adapter import build_embedding_provider

        return build_embedding_provider()
    if provider_name == "ollama":
        from kdi_media.providers.ollama_adapter import build_embedding_provider

        return build_embedding_provider()
    raise AIProviderNotConfiguredError(
        f"AI_EMBEDDING_PROVIDER={provider_name!r} has no registered adapter."
    )
