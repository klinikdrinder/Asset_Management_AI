"""Tests for the OpenAI provider adapter. Every test uses a fake client
object injected via the adapters' `client=` constructor parameter - no real
network call is ever made. Real openai SDK exception classes are
constructed directly (never raised over the network) to verify this
adapter's retryable/permanent classification."""

from __future__ import annotations

import inspect
import base64
import json
import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import httpx
import openai

from kdi_media.providers.base import (
    AIProviderNotConfiguredError,
    DescriptionValidationError,
    ProviderPermanentError,
    ProviderRetryableError,
)
from kdi_media.providers.openai_adapter import (
    CONNECT_TIMEOUT_SECONDS,
    DESCRIPTION_SYSTEM_PROMPT,
    RESPONSE_SCHEMA,
    OpenAIDescriptionAdapter,
    OpenAIEmbeddingAdapter,
    REQUEST_TIMEOUT_SECONDS,
    SDK_MAX_RETRIES,
    build_description_provider,
    build_embedding_provider,
)


def _http_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.openai.com/v1/x")
    return httpx.Response(status_code=status_code, request=request)


def rate_limit_error() -> Exception:
    return openai.RateLimitError("rate limited", response=_http_response(429), body=None)


def timeout_error() -> Exception:
    return openai.APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/x"))


def connection_error() -> Exception:
    return openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/x"))


def authentication_error() -> Exception:
    return openai.AuthenticationError("invalid api key", response=_http_response(401), body=None)


def bad_request_error() -> Exception:
    return openai.BadRequestError("bad request", response=_http_response(400), body=None)


class FakeResponsesNamespace:
    def __init__(self, *, output_text=None, usage=None, error=None):
        self._output_text = output_text
        self._usage = usage
        self._error = error
        self.captured_kwargs: dict | None = None

    def create(self, **kwargs):
        self.captured_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return SimpleNamespace(output_text=self._output_text, usage=self._usage)


class FakeEmbeddingsNamespace:
    def __init__(self, *, rows=None, usage=None, error=None):
        self._rows = rows
        self._usage = usage
        self._error = error
        self.captured_kwargs: dict | None = None

    def create(self, **kwargs):
        self.captured_kwargs = kwargs
        if self._error is not None:
            raise self._error
        return SimpleNamespace(data=self._rows, usage=self._usage)


class FakeOpenAIClient:
    def __init__(self, *, responses=None, embeddings=None):
        self.responses = responses or FakeResponsesNamespace()
        self.embeddings = embeddings or FakeEmbeddingsNamespace()


VALID_METADATA_JSON = json.dumps(
    {
        "content_type": "Patient Testimonial",
        "treatment": "Long Hair FUE",
        "subject": "Female patient",
        "doctor_name": "Datuk Dr Inder",
        "short_caption": "Female patient shares her Long Hair FUE recovery experience.",
        "ai_description": "A female patient discusses her Long Hair FUE treatment experience.",
    }
)


def description_adapter(**overrides) -> tuple[OpenAIDescriptionAdapter, FakeResponsesNamespace]:
    responses = overrides.pop("responses", None) or FakeResponsesNamespace(output_text=VALID_METADATA_JSON)
    client = FakeOpenAIClient(responses=responses)
    adapter = OpenAIDescriptionAdapter(
        api_key="unused", model="gpt-5.6-luna", schema_version="v1", client=client
    )
    return adapter, responses


def embedding_adapter(**overrides) -> tuple[OpenAIEmbeddingAdapter, FakeEmbeddingsNamespace]:
    embeddings = overrides.pop("embeddings", None) or FakeEmbeddingsNamespace(
        rows=[SimpleNamespace(embedding=[0.1] * 1536)]
    )
    client = FakeOpenAIClient(embeddings=embeddings)
    adapter = OpenAIEmbeddingAdapter(
        api_key="unused", model="text-embedding-3-small", dimensions=1536, version="v1", client=client
    )
    return adapter, embeddings


class OpenAIDescriptionAdapterTests(unittest.TestCase):
    def test_client_has_explicit_bounded_timeouts_and_no_nested_retries(self) -> None:
        with patch("openai.OpenAI") as constructor:
            from kdi_media.providers.openai_adapter import _client

            _client("unused-secret")
        kwargs = constructor.call_args.kwargs
        self.assertEqual(kwargs["max_retries"], SDK_MAX_RETRIES)
        self.assertEqual(kwargs["timeout"].connect, CONNECT_TIMEOUT_SECONDS)
        self.assertEqual(kwargs["timeout"].read, REQUEST_TIMEOUT_SECONDS)

    def test_correct_responses_api_request_shape_with_structured_output(self) -> None:
        adapter, responses = description_adapter()
        adapter.describe_media(
            file_name="a.jpg", mime_type="image/jpeg", media_category="image", images=[b"frame"]
        )
        kwargs = responses.captured_kwargs
        assert kwargs is not None
        self.assertEqual(kwargs["model"], "gpt-5.6-luna")
        self.assertEqual(kwargs["instructions"], DESCRIPTION_SYSTEM_PROMPT)
        self.assertEqual(kwargs["text"]["format"]["type"], "json_schema")
        self.assertTrue(kwargs["text"]["format"]["strict"])
        self.assertEqual(kwargs["text"]["format"]["schema"], RESPONSE_SCHEMA)
        self.assertFalse(RESPONSE_SCHEMA["additionalProperties"])
        self.assertEqual(kwargs["input"][0]["role"], "user")

    def test_image_data_url_contains_complete_jpeg_bytes(self) -> None:
        adapter, responses = description_adapter()
        jpeg = b"\xff\xd8complete-synthetic-jpeg\xff\xd9"
        adapter.describe_media(
            file_name="synthetic.jpg", mime_type="image/jpeg",
            media_category="image", images=[jpeg],
        )
        content = responses.captured_kwargs["input"][0]["content"]
        image_url = next(part["image_url"] for part in content if part["type"] == "input_image")
        prefix, encoded = image_url.split(",", 1)
        self.assertEqual(prefix, "data:image/jpeg;base64")
        self.assertEqual(base64.b64decode(encoded, validate=True), jpeg)

    def test_only_representative_frames_are_included_never_a_full_video(self) -> None:
        adapter, responses = description_adapter()
        frames = [b"frame-1", b"frame-2", b"frame-3"]
        adapter.describe_media(
            file_name="v.mp4", mime_type="video/mp4", media_category="video",
            images=frames, transcript="hello world",
        )
        content = responses.captured_kwargs["input"][0]["content"]
        image_parts = [part for part in content if part["type"] == "input_image"]
        self.assertEqual(len(image_parts), len(frames))
        # No part carries a raw video blob - only base64 JPEG data URIs.
        for part in image_parts:
            self.assertTrue(part["image_url"].startswith("data:image/jpeg;base64,"))

    def test_describe_media_signature_has_no_full_content_or_video_parameter(self) -> None:
        # Structural guarantee: it is impossible to pass a raw video/content
        # blob through this interface - only representative frames.
        parameters = set(inspect.signature(OpenAIDescriptionAdapter.describe_media).parameters)
        self.assertIn("images", parameters)
        self.assertIn("transcript", parameters)
        self.assertNotIn("content", parameters)
        self.assertNotIn("video", parameters)

    def test_transcript_included_in_prompt_when_provided(self) -> None:
        adapter, responses = description_adapter()
        adapter.describe_media(
            file_name="v.mp4", mime_type="video/mp4", media_category="video",
            images=[b"frame"], transcript="doctor explains aftercare",
        )
        text_part = responses.captured_kwargs["input"][0]["content"][0]
        self.assertIn("doctor explains aftercare", text_part["text"])

    def test_transcript_omitted_from_prompt_when_none(self) -> None:
        adapter, responses = description_adapter()
        adapter.describe_media(
            file_name="v.mp4", mime_type="video/mp4", media_category="video",
            images=[b"frame"], transcript=None,
        )
        text_part = responses.captured_kwargs["input"][0]["content"][0]
        self.assertNotIn("Transcript excerpt", text_part["text"])

    def test_no_images_is_rejected(self) -> None:
        adapter, _ = description_adapter()
        with self.assertRaises(ProviderPermanentError):
            adapter.describe_media(file_name="a.jpg", mime_type="image/jpeg", media_category="image", images=[])

    def test_valid_response_is_parsed_into_structured_metadata(self) -> None:
        adapter, _ = description_adapter()
        metadata, _cost = adapter.describe_media(
            file_name="a.jpg", mime_type="image/jpeg", media_category="image", images=[b"frame"]
        )
        self.assertEqual(metadata.content_type, "Patient Testimonial")
        self.assertEqual(metadata.doctor_name, "Datuk Dr Inder")

    def test_model_name_and_provider_recorded_correctly(self) -> None:
        adapter, _ = description_adapter()
        self.assertEqual(adapter.model_name, "gpt-5.6-luna")
        self.assertEqual(adapter.provider_name, "openai")
        self.assertEqual(adapter.schema_version, "v1")

    def test_extra_field_in_response_is_rejected(self) -> None:
        malformed = json.dumps({**json.loads(VALID_METADATA_JSON), "audience": "everyone"})
        adapter, _ = description_adapter(responses=FakeResponsesNamespace(output_text=malformed))
        with self.assertRaises(DescriptionValidationError):
            adapter.describe_media(file_name="a.jpg", mime_type="image/jpeg", media_category="image", images=[b"f"])

    def test_invalid_content_type_falls_back_to_other(self) -> None:
        malformed = json.dumps({**json.loads(VALID_METADATA_JSON), "content_type": "Something Else"})
        adapter, _ = description_adapter(responses=FakeResponsesNamespace(output_text=malformed))
        metadata, _cost = adapter.describe_media(
            file_name="a.jpg", mime_type="image/jpeg", media_category="image", images=[b"f"]
        )
        self.assertEqual(metadata.content_type, "Other")

    def test_empty_response_raises_validation_error(self) -> None:
        adapter, _ = description_adapter(responses=FakeResponsesNamespace(output_text=""))
        with self.assertRaises(DescriptionValidationError):
            adapter.describe_media(file_name="a.jpg", mime_type="image/jpeg", media_category="image", images=[b"f"])

    def test_non_json_response_raises_validation_error(self) -> None:
        adapter, _ = description_adapter(responses=FakeResponsesNamespace(output_text="not json"))
        with self.assertRaises(DescriptionValidationError):
            adapter.describe_media(file_name="a.jpg", mime_type="image/jpeg", media_category="image", images=[b"f"])

    def test_rate_limit_error_is_retryable(self) -> None:
        adapter, _ = description_adapter(responses=FakeResponsesNamespace(error=rate_limit_error()))
        with self.assertRaises(ProviderRetryableError):
            adapter.describe_media(file_name="a.jpg", mime_type="image/jpeg", media_category="image", images=[b"f"])

    def test_timeout_error_is_retryable(self) -> None:
        adapter, _ = description_adapter(responses=FakeResponsesNamespace(error=timeout_error()))
        with self.assertRaises(ProviderRetryableError):
            adapter.describe_media(file_name="a.jpg", mime_type="image/jpeg", media_category="image", images=[b"f"])

    def test_connection_error_is_retryable(self) -> None:
        adapter, _ = description_adapter(responses=FakeResponsesNamespace(error=connection_error()))
        with self.assertRaises(ProviderRetryableError):
            adapter.describe_media(file_name="a.jpg", mime_type="image/jpeg", media_category="image", images=[b"f"])

    def test_authentication_error_is_permanent(self) -> None:
        adapter, _ = description_adapter(responses=FakeResponsesNamespace(error=authentication_error()))
        with self.assertRaises(ProviderPermanentError):
            adapter.describe_media(file_name="a.jpg", mime_type="image/jpeg", media_category="image", images=[b"f"])

    def test_bad_request_error_is_permanent(self) -> None:
        adapter, _ = description_adapter(responses=FakeResponsesNamespace(error=bad_request_error()))
        with self.assertRaises(ProviderPermanentError):
            adapter.describe_media(file_name="a.jpg", mime_type="image/jpeg", media_category="image", images=[b"f"])

    def test_cost_estimated_from_usage_tokens(self) -> None:
        adapter, _ = description_adapter(
            responses=FakeResponsesNamespace(
                output_text=VALID_METADATA_JSON,
                usage=SimpleNamespace(input_tokens=1000, output_tokens=200),
            )
        )
        _metadata, cost = adapter.describe_media(
            file_name="a.jpg", mime_type="image/jpeg", media_category="image", images=[b"f"]
        )
        self.assertIsNotNone(cost)
        assert cost is not None
        self.assertGreater(cost, 0)

    def test_fabrication_prevention_instructions_present(self) -> None:
        self.assertIn("Never invent", DESCRIPTION_SYSTEM_PROMPT)
        self.assertIn("null", DESCRIPTION_SYSTEM_PROMPT)
        self.assertIn("patient's identity", DESCRIPTION_SYSTEM_PROMPT)
        self.assertIn("marketing claims", DESCRIPTION_SYSTEM_PROMPT)


class OpenAIEmbeddingAdapterTests(unittest.TestCase):
    def test_requests_exactly_configured_dimensions(self) -> None:
        adapter, embeddings = embedding_adapter()
        adapter.embed_text("female patient testimonial")
        self.assertEqual(embeddings.captured_kwargs["dimensions"], 1536)

    def test_exact_dimension_response_is_accepted(self) -> None:
        adapter, _ = embedding_adapter()
        values, _cost = adapter.embed_text("hello")
        self.assertEqual(len(values), 1536)

    def test_incompatible_dimension_response_is_rejected_not_truncated(self) -> None:
        adapter, _ = embedding_adapter(
            embeddings=FakeEmbeddingsNamespace(rows=[SimpleNamespace(embedding=[0.1] * 100)])
        )
        with self.assertRaises(ProviderPermanentError):
            adapter.embed_text("hello")

    def test_empty_text_is_rejected_without_calling_the_api(self) -> None:
        adapter, embeddings = embedding_adapter()
        with self.assertRaises(ProviderPermanentError):
            adapter.embed_text("   ")
        self.assertIsNone(embeddings.captured_kwargs)

    def test_text_is_normalized_before_request(self) -> None:
        adapter, embeddings = embedding_adapter()
        adapter.embed_text("  female   patient   testimonial  ")
        self.assertEqual(embeddings.captured_kwargs["input"], "female patient testimonial")

    def test_provider_model_dimensions_version_recorded(self) -> None:
        adapter, _ = embedding_adapter()
        self.assertEqual(adapter.provider_name, "openai")
        self.assertEqual(adapter.model_name, "text-embedding-3-small")
        self.assertEqual(adapter.embedding_dimensions, 1536)
        self.assertEqual(adapter.version, "v1")

    def test_rate_limit_error_is_retryable(self) -> None:
        adapter, _ = embedding_adapter(embeddings=FakeEmbeddingsNamespace(error=rate_limit_error()))
        with self.assertRaises(ProviderRetryableError):
            adapter.embed_text("hello")

    def test_authentication_error_is_permanent(self) -> None:
        adapter, _ = embedding_adapter(embeddings=FakeEmbeddingsNamespace(error=authentication_error()))
        with self.assertRaises(ProviderPermanentError):
            adapter.embed_text("hello")

    def test_batch_embedding_returns_matching_count_and_dimension(self) -> None:
        adapter, _ = embedding_adapter(
            embeddings=FakeEmbeddingsNamespace(
                rows=[SimpleNamespace(embedding=[0.1] * 1536), SimpleNamespace(embedding=[0.2] * 1536)]
            )
        )
        results = adapter.embed_batch(["first text", "second text"])
        self.assertEqual(len(results), 2)
        for values, _cost in results:
            self.assertEqual(len(values), 1536)

    def test_batch_falls_back_to_per_item_when_any_text_is_empty(self) -> None:
        adapter, embeddings = embedding_adapter()
        # Falls back to embed_text() per item rather than silently dropping
        # or misaligning the batch; the empty item raises like a solo call
        # would, instead of returning a shorter/misaligned result list.
        with self.assertRaises(ProviderPermanentError):
            adapter.embed_batch(["valid text", "   "])
        # The single-item request shape was used (fallback path), not a
        # multi-input batch request.
        self.assertEqual(embeddings.captured_kwargs["input"], "valid text")


class OpenAIFactoryTests(unittest.TestCase):
    """Constructing an openai.OpenAI client never makes a network call, so
    these exercise the real factory wiring end-to-end (without ever calling
    describe_media()/embed_text(), which would)."""

    def setUp(self) -> None:
        self._removed = {
            name: os.environ.pop(name, None)
            for name in (
                "AI_DESCRIPTION_PROVIDER",
                "AI_EMBEDDING_PROVIDER",
                "OPENAI_API_KEY",
                "OPENAI_DESCRIPTION_MODEL",
                "OPENAI_EMBEDDING_MODEL",
                "OPENAI_EMBEDDING_DIMENSIONS",
                "OPENAI_DESCRIPTION_SCHEMA_VERSION",
                "OPENAI_EMBEDDING_VERSION",
            )
        }

    def tearDown(self) -> None:
        for name, value in self._removed.items():
            if value is not None:
                os.environ[name] = value
            else:
                os.environ.pop(name, None)

    def test_description_provider_is_selected_and_configured(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-test-not-real"
        os.environ["OPENAI_DESCRIPTION_MODEL"] = "gpt-5.6-luna"
        os.environ["OPENAI_DESCRIPTION_SCHEMA_VERSION"] = "v1"
        provider = build_description_provider()
        self.assertEqual(provider.provider_name, "openai")
        self.assertEqual(provider.model_name, "gpt-5.6-luna")
        self.assertEqual(provider.schema_version, "v1")
        self.assertTrue(callable(provider._client.responses.create))

    def test_embedding_provider_is_selected_and_configured(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-test-not-real"
        os.environ["OPENAI_EMBEDDING_MODEL"] = "text-embedding-3-small"
        os.environ["OPENAI_EMBEDDING_DIMENSIONS"] = "1536"
        os.environ["OPENAI_EMBEDDING_VERSION"] = "v1"
        provider = build_embedding_provider()
        self.assertEqual(provider.provider_name, "openai")
        self.assertEqual(provider.model_name, "text-embedding-3-small")
        self.assertEqual(provider.embedding_dimensions, 1536)
        self.assertEqual(provider.version, "v1")
        self.assertTrue(callable(provider._client.embeddings.create))

    def test_missing_api_key_raises_not_configured_without_leaking_key(self) -> None:
        os.environ["OPENAI_DESCRIPTION_MODEL"] = "gpt-5.6-luna"
        with self.assertRaises(AIProviderNotConfiguredError) as ctx:
            build_description_provider()
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))
        self.assertNotIn("sk-", str(ctx.exception))

    def test_missing_description_model_raises_not_configured(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-test-not-real"
        with self.assertRaises(AIProviderNotConfiguredError):
            build_description_provider()

    def test_invalid_embedding_dimensions_raises_not_configured(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-test-not-real"
        os.environ["OPENAI_EMBEDDING_MODEL"] = "text-embedding-3-small"
        os.environ["OPENAI_EMBEDDING_DIMENSIONS"] = "not-a-number"
        with self.assertRaises(AIProviderNotConfiguredError):
            build_embedding_provider()

    def test_get_description_provider_dispatches_to_openai(self) -> None:
        from kdi_media.providers.base import get_description_provider

        os.environ["AI_DESCRIPTION_PROVIDER"] = "openai"
        os.environ["OPENAI_API_KEY"] = "sk-test-not-real"
        os.environ["OPENAI_DESCRIPTION_MODEL"] = "gpt-5.6-luna"
        provider = get_description_provider()
        self.assertEqual(provider.provider_name, "openai")


if __name__ == "__main__":
    unittest.main()
