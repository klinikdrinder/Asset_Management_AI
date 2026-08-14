from __future__ import annotations

from io import BytesIO
import unittest
from unittest.mock import patch

from PIL import Image

from kdi_media.image_input import (
    ImagePreparationError,
    MAX_IMAGE_DIMENSION,
    PillowImagePreprocessor,
)


def encoded_image(size: tuple[int, int], *, orientation: int | None = None) -> bytes:
    image = Image.new("RGB", size, (50, 100, 150))
    output = BytesIO()
    exif = Image.Exif()
    if orientation is not None:
        exif[274] = orientation
    image.save(output, "JPEG", exif=exif)
    return output.getvalue()


def output_size(value: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(value)) as image:
        image.load()
        return image.size


class PillowImagePreprocessorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.preprocessor = PillowImagePreprocessor()

    def test_portrait_is_bounded_and_aspect_ratio_preserved(self):
        self.assertEqual(output_size(self.preprocessor.prepare(encoded_image((2000, 4000)))), (800, 1600))

    def test_landscape_is_bounded_and_aspect_ratio_preserved(self):
        self.assertEqual(output_size(self.preprocessor.prepare(encoded_image((4000, 2000)))), (1600, 800))

    def test_square_is_bounded(self):
        self.assertEqual(output_size(self.preprocessor.prepare(encoded_image((3000, 3000)))), (1600, 1600))

    def test_already_small_image_is_not_upscaled(self):
        self.assertEqual(output_size(self.preprocessor.prepare(encoded_image((320, 240)))), (320, 240))

    def test_large_image_never_exceeds_maximum(self):
        width, height = output_size(self.preprocessor.prepare(encoded_image((5000, 3500))))
        self.assertLessEqual(max(width, height), MAX_IMAGE_DIMENSION)

    def test_malformed_image_is_rejected(self):
        with self.assertRaises(ImagePreparationError):
            self.preprocessor.prepare(b"not an image")

    def test_exif_orientation_is_applied_then_removed(self):
        result = self.preprocessor.prepare(encoded_image((400, 200), orientation=6))
        self.assertEqual(output_size(result), (200, 400))
        with Image.open(BytesIO(result)) as image:
            self.assertNotEqual(image.getexif().get(274), 6)

    def test_decompression_bomb_limit_is_enforced(self):
        with patch("kdi_media.image_input.MAX_IMAGE_PIXELS", 100):
            with self.assertRaises(ImagePreparationError):
                self.preprocessor.prepare(encoded_image((20, 20)))


if __name__ == "__main__":
    unittest.main()
