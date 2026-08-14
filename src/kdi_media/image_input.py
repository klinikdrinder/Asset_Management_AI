"""Bounded, local-only image derivation for multimodal provider input."""

from __future__ import annotations

from io import BytesIO
from typing import Protocol
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError


MAX_IMAGE_DIMENSION = 1600
MAX_IMAGE_PIXELS = 64_000_000
JPEG_QUALITY = 88


class ImagePreparationError(ValueError):
    """Input is corrupt, unsafe, or cannot be converted to bounded JPEG."""


class ImagePreprocessor(Protocol):
    def prepare(self, image_bytes: bytes) -> bytes: ...


class PillowImagePreprocessor:
    """Return a derived JPEG; original KDI bytes are never modified."""

    def prepare(self, image_bytes: bytes) -> bytes:
        if not image_bytes:
            raise ImagePreparationError("Image input is empty")
        previous_limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(image_bytes)) as opened:
                    opened.load()
                    oriented = ImageOps.exif_transpose(opened)
                    converted = oriented.convert("RGB")
                    converted.thumbnail(
                        (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
                        Image.Resampling.LANCZOS,
                    )
                    output = BytesIO()
                    converted.save(
                        output,
                        format="JPEG",
                        quality=JPEG_QUALITY,
                        optimize=True,
                    )
                    return output.getvalue()
        except (
            UnidentifiedImageError,
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise ImagePreparationError("Image input is corrupt or exceeds safety limits") from exc
        finally:
            Image.MAX_IMAGE_PIXELS = previous_limit
