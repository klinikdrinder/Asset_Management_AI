from __future__ import annotations
from contextlib import nullcontext
from pathlib import Path
import math, os
from PIL import Image, ImageOps, ImageFile
import torch
import open_clip

MODEL_PROVIDER = "open_clip"
MODEL_NAME = os.getenv("KDI_VISUAL_MODEL", "ViT-B-32")
MODEL_VERSION = os.getenv("KDI_VISUAL_PRETRAINED", "laion2b_s34b_b79k")
DIMENSIONS = 512

class OpenClipEncoder:
    def __init__(self) -> None:
        torch.set_num_threads(max(1, min(4, int(os.getenv("KDI_VISUAL_CPU_THREADS", "2")))))
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=MODEL_VERSION, device="cpu")
        self.tokenizer = open_clip.get_tokenizer(MODEL_NAME)
        self.model.eval()

    @staticmethod
    def _vector(tensor: torch.Tensor) -> list[float]:
        tensor = tensor.float().reshape(-1)
        tensor = tensor / tensor.norm(p=2).clamp_min(1e-12)
        values = tensor.cpu().tolist()
        if len(values) != DIMENSIONS or not all(math.isfinite(v) for v in values):
            raise ValueError("INVALID_VECTOR")
        return values

    def embed_text(self, text: str) -> list[float]:
        clean = " ".join(text.split())[:300]
        if not clean: raise ValueError("text is empty")
        with torch.inference_mode():
            return self._vector(self.model.encode_text(self.tokenizer([clean])))

    def embed_image(self, source: str | Path | Image.Image) -> list[float]:
        # Drive synchronization fixtures and partially recovered JPEG/PNG files
        # may have a valid decodable image followed by a truncated final block.
        # Pillow still validates headers and pixels; this only permits decoding
        # the available raster instead of inventing replacement content.
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        owned = not isinstance(source, Image.Image)
        image = Image.open(source) if owned else source
        try:
            rgb = ImageOps.exif_transpose(image).convert("RGB")
            try:
                tensor = self.preprocess(rgb).unsqueeze(0)
                with torch.inference_mode(): return self._vector(self.model.encode_image(tensor))
            finally: rgb.close()
        finally:
            if owned: image.close()

    @staticmethod
    def aggregate(vectors: list[list[float]]) -> list[float]:
        if not vectors: raise ValueError("no frame vectors")
        value = torch.tensor(vectors, dtype=torch.float32).mean(dim=0)
        return OpenClipEncoder._vector(value)
