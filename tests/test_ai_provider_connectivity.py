from __future__ import annotations

from io import BytesIO
import unittest

from PIL import Image, ImageStat

from scripts.test_ai_provider_connectivity import (
    SYNTHETIC_EMBEDDING_METADATA,
    SYNTHETIC_JPEG,
    build_synthetic_jpeg,
)
from kdi_media.semantic_indexing import build_searchable_text


class SyntheticConnectivityFixtureTests(unittest.TestCase):
    def test_fixture_is_deterministic_ordinary_rgb_jpeg(self) -> None:
        self.assertEqual(SYNTHETIC_JPEG, build_synthetic_jpeg())
        self.assertGreater(len(SYNTHETIC_JPEG), 1000)
        self.assertTrue(SYNTHETIC_JPEG.startswith(b"\xff\xd8"))
        self.assertTrue(SYNTHETIC_JPEG.endswith(b"\xff\xd9"))
        with Image.open(BytesIO(SYNTHETIC_JPEG)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (512, 512))
            self.assertEqual(image.mode, "RGB")
            image.verify()
        with Image.open(BytesIO(SYNTHETIC_JPEG)) as image:
            image.load()
            extrema = ImageStat.Stat(image).extrema
            self.assertTrue(any(low != high for low, high in extrema))

    def test_embedding_text_uses_only_approved_search_fields(self) -> None:
        text = build_searchable_text(
            metadata=SYNTHETIC_EMBEDDING_METADATA,
            file_name="must-not-appear.jpg",
        )
        self.assertNotIn("must-not-appear", text)
        self.assertNotIn(SYNTHETIC_EMBEDDING_METADATA.short_caption, text)
        self.assertIn(SYNTHETIC_EMBEDDING_METADATA.content_type, text)
        self.assertIn(SYNTHETIC_EMBEDDING_METADATA.subject or "", text)
        self.assertIn(SYNTHETIC_EMBEDDING_METADATA.ai_description, text)


if __name__ == "__main__":
    unittest.main()
