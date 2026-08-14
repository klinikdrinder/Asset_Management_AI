"""Explicit, synthetic-only connectivity check for configured AI providers.

The safe default performs no provider call. A live test requires both
--execute-live and --confirm-synthetic and exactly one provider operation.
It never reads the production catalogue or writes semantic database rows.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from io import BytesIO
import json
import math
import time

from dotenv import load_dotenv
from PIL import Image, ImageDraw

from kdi_media.providers.base import StructuredMetadata, get_description_provider, get_embedding_provider
from kdi_media.semantic_indexing import build_searchable_text


def build_synthetic_jpeg() -> bytes:
    """Create deterministic, ordinary-sized non-KDI connectivity media."""
    image = Image.new("RGB", (512, 512), (242, 246, 250))
    draw = ImageDraw.Draw(image)
    draw.rectangle((48, 56, 232, 240), fill=(37, 99, 235))
    draw.ellipse((280, 56, 464, 240), fill=(220, 38, 38))
    draw.rectangle((96, 304, 416, 448), fill=(22, 163, 74))
    output = BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True)
    return output.getvalue()


SYNTHETIC_JPEG = build_synthetic_jpeg()
SYNTHETIC_EMBEDDING_METADATA = StructuredMetadata(
    content_type="Educational Video",
    treatment=None,
    subject="Geometric shapes",
    doctor_name=None,
    short_caption="Synthetic geometric connectivity fixture.",
    ai_description="A synthetic image contains blue, red, and green geometric shapes.",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--description", action="store_true")
    operation.add_argument("--embedding", action="store_true")
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--confirm-synthetic", action="store_true")
    args = parser.parse_args()
    load_dotenv()
    if not (args.execute_live and args.confirm_synthetic):
        print(json.dumps({"status": "NOT_EXECUTED", "external_ai_calls": 0}))
        return 0

    if args.description:
        provider = get_description_provider()
        started = time.perf_counter()
        metadata, cost = provider.describe_media(
            file_name="synthetic-connectivity.jpg",
            mime_type="image/jpeg",
            media_category="image",
            images=[SYNTHETIC_JPEG],
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        print(json.dumps({
            "status": "OK", "operation": "description",
            "provider": provider.provider_name, "model": provider.model_name,
            "version": provider.schema_version,
            "structured_output": bool(metadata.ai_description and metadata.short_caption),
            "field_names": sorted(asdict(metadata)),
            "metadata": asdict(metadata),
            "latency_ms": elapsed_ms,
            "request_count": 1,
            "retry_count": 0,
            "estimated_cost_usd": cost,
            "production_rows_written": 0,
        }, sort_keys=True))
    else:
        provider = get_embedding_provider()
        searchable_text = build_searchable_text(metadata=SYNTHETIC_EMBEDDING_METADATA)
        started = time.perf_counter()
        vector, cost = provider.embed_text(searchable_text)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        numeric_finite = all(
            isinstance(value, (int, float)) and math.isfinite(value) for value in vector
        )
        print(json.dumps({
            "status": "OK", "operation": "embedding",
            "provider": provider.provider_name, "model": provider.model_name,
            "version": provider.version,
            "dimensions": len(vector), "expected_dimensions": provider.embedding_dimensions,
            "numeric_finite": numeric_finite,
            "latency_ms": elapsed_ms,
            "request_count": 1,
            "retry_count": 0,
            "estimated_cost_usd": cost, "production_rows_written": 0,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
