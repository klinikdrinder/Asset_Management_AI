from __future__ import annotations

import json
from io import BytesIO
import math
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from kdi_media.providers.base import (
    AIProviderNotConfiguredError, ProviderPermanentError, ProviderRetryableError,
)
from kdi_media.providers.ollama_adapter import (
    OllamaClient, OllamaDescriptionAdapter, OllamaEmbeddingAdapter, RESPONSE_SCHEMA,
    build_description_provider, build_embedding_provider,
)


class FakeClient:
    def __init__(self, response: dict):
        self.response = response
        self.calls: list[tuple[str, dict]] = []

    def post(self, path: str, payload: dict) -> dict:
        self.calls.append((path, payload))
        return self.response


def metadata_response(**changes) -> dict:
    value = {"content_type": "Other", "treatment": None, "subject": "Geometric shapes",
             "doctor_name": None, "ai_description": "Blue, red, and green geometric shapes.",
             "short_caption": "Colorful geometric shapes."}
    value.update(changes)
    return {"message": {"content": json.dumps(value)}}


class OllamaDescriptionTests(unittest.TestCase):
    def test_strict_schema_and_local_vision_payload(self) -> None:
        client = FakeClient(metadata_response())
        provider = OllamaDescriptionAdapter(model="qwen3-vl:2b", schema_version="v1", client=client)
        metadata, cost = provider.describe_media(file_name="ignored.jpg", mime_type="image/jpeg",
            media_category="image", images=[b"jpeg"])
        path, payload = client.calls[0]
        self.assertEqual(path, "/api/chat")
        self.assertEqual(payload["format"], RESPONSE_SCHEMA)
        self.assertFalse(RESPONSE_SCHEMA["additionalProperties"])
        self.assertEqual(payload["options"]["temperature"], 0)
        self.assertEqual(payload["keep_alive"], 0)
        self.assertEqual(metadata.doctor_name, None)
        self.assertIsNone(cost)

    def test_malformed_and_extra_fields_are_rejected(self) -> None:
        malformed = FakeClient({"message": {"content": "not-json"}})
        with self.assertRaises(ProviderRetryableError):
            OllamaDescriptionAdapter(model="m", schema_version="v1", client=malformed).describe_media(
                file_name="x", mime_type="image/jpeg", media_category="image", images=[b"x"])
        extra = FakeClient(metadata_response(audience="public"))
        with self.assertRaises(ValueError):
            OllamaDescriptionAdapter(model="m", schema_version="v1", client=extra).describe_media(
                file_name="x", mime_type="image/jpeg", media_category="image", images=[b"x"])


class OllamaEmbeddingTests(unittest.TestCase):
    def test_exact_dimension_and_request_identity(self) -> None:
        client = FakeClient({"embeddings": [[0.01] * 1024]})
        provider = OllamaEmbeddingAdapter(model="qwen3-embedding:0.6b", dimensions=1024,
                                          version="v1", context_length=2048,
                                          batch_size=32, client=client)
        vector, cost = provider.embed_text("  hello   world ")
        self.assertEqual(len(vector), 1024)
        path, payload = client.calls[0]
        self.assertEqual(path, "/api/embed")
        self.assertEqual(payload["dimensions"], 1024)
        self.assertFalse(payload["truncate"])
        self.assertEqual(payload["keep_alive"], 0)
        self.assertEqual(payload["options"]["num_ctx"], 2048)
        self.assertEqual(payload["options"]["num_batch"], 32)
        self.assertEqual(payload["input"], "hello world")
        self.assertIsNone(cost)

    def test_wrong_dimension_nan_and_infinity_fail_closed(self) -> None:
        for vector in ([0.0] * 10, [math.nan] * 1024, [math.inf] * 1024):
            provider = OllamaEmbeddingAdapter(model="m", dimensions=1024, version="v1",
                                               context_length=2048,
                                               batch_size=32,
                                               client=FakeClient({"embeddings": [vector]}))
            with self.assertRaises(ProviderPermanentError):
                provider.embed_text("hello")

    def test_malformed_embedding_response_is_rejected(self) -> None:
        for response in ({}, {"embeddings": []}, {"embeddings": "not-an-array"}):
            provider = OllamaEmbeddingAdapter(
                model="m", dimensions=1024, version="v1", context_length=2048,
                batch_size=32, client=FakeClient(response),
            )
            with self.assertRaises(ProviderRetryableError):
                provider.embed_text("hello")


class OllamaClientFailureTests(unittest.TestCase):
    def test_model_unavailable_is_permanent(self) -> None:
        error = HTTPError("http://127.0.0.1:11434/api/embed", 404, "missing", {}, BytesIO(b"missing"))
        with patch("kdi_media.providers.ollama_adapter.urlopen", side_effect=error), \
                self.assertRaises(ProviderPermanentError):
            OllamaClient("http://127.0.0.1:11434", 1).post("/api/embed", {})

    def test_ollama_unavailable_and_timeout_are_retryable(self) -> None:
        for error in (URLError("offline"), TimeoutError("timed out")):
            with patch("kdi_media.providers.ollama_adapter.urlopen", side_effect=error), \
                    self.assertRaises(ProviderRetryableError):
                OllamaClient("http://127.0.0.1:11434", 1).post("/api/embed", {})


class OllamaFactoryTests(unittest.TestCase):
    def test_factory_selects_ollama_without_openai_key(self) -> None:
        values = {"AI_DESCRIPTION_PROVIDER": "ollama", "AI_EMBEDDING_PROVIDER": "ollama",
                  "OLLAMA_BASE_URL": "http://127.0.0.1:11434", "OLLAMA_VISION_MODEL": "qwen3-vl:2b",
                  "OLLAMA_EMBEDDING_MODEL": "qwen3-embedding:0.6b", "OLLAMA_EMBEDDING_DIMENSIONS": "1024"}
        with patch.dict(os.environ, values, clear=True):
            self.assertEqual(build_description_provider().provider_name, "ollama")
            provider = build_embedding_provider()
            self.assertEqual(provider.provider_name, "ollama")
            self.assertEqual(provider.model_name, "qwen3-embedding:0.6b")
            self.assertEqual(provider.embedding_dimensions, 1024)

    def test_non_loopback_and_nonpositive_dimensions_are_rejected(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://example.com:11434",
            "OLLAMA_VISION_MODEL": "m"}, clear=True), self.assertRaises(AIProviderNotConfiguredError):
            build_description_provider()
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://127.0.0.1:11434",
            "OLLAMA_EMBEDDING_MODEL": "m", "OLLAMA_EMBEDDING_DIMENSIONS": "0"}, clear=True), \
                self.assertRaises(AIProviderNotConfiguredError):
            build_embedding_provider()

    def test_provider_factory_remains_dimension_configurable(self) -> None:
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://127.0.0.1:11434",
            "OLLAMA_EMBEDDING_MODEL": "generic", "OLLAMA_EMBEDDING_DIMENSIONS": "768"}, clear=True):
            self.assertEqual(build_embedding_provider().embedding_dimensions, 768)


if __name__ == "__main__":
    unittest.main()
