"""Robust, original-preserving image access for analysis.

Three tiers, cheapest first:
  1. native decode via Pillow + pillow-heif (HEIC/HEIF), taking the HEIF
     container's PRIMARY image (not merely the first frame of a motion photo).
  2. Google Drive rendered-JPEG thumbnail fallback for anything that will not
     decode locally - Drive renders a preview whatever the source format.
  3. format is detected by MAGIC BYTES, not extension/mime (a .JPG can be HEIC).

Hard constraint: originals are never converted or modified. Everything here
decodes in memory and returns a fresh in-memory JPEG for the model; the source
bytes on Drive are read-only and untouched.
"""
from __future__ import annotations

import io
import re
from typing import Optional

import httpx
from PIL import Image
from pillow_heif import register_heif_opener
from google.auth.transport.requests import Request as GoogleRequest

register_heif_opener()  # PIL.Image.open() now returns the HEIF primary image


def detect_format(head: bytes) -> str:
    """Identify actual container from the first bytes."""
    b = head
    if b[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if len(b) >= 12 and b[4:8] == b"ftyp":
        brand = b[8:12]
        if brand in (b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"mif1", b"msf1"):
            return "heic"
        if brand == b"avif":
            return "avif"
        return "iso-" + brand.decode("latin1", "ignore").strip()
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if b[:2] == b"BM":
        return "bmp"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if b[:2] in (b"II", b"MM"):
        return "tiff"
    return "unknown"


def _encode_jpeg(img: Image.Image, max_side: int) -> bytes:
    img = img.convert("RGB")
    w, h = img.size
    sc = min(1.0, max_side / max(w, h))
    if sc < 1:
        img = img.resize((int(w * sc), int(h * sc)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def decode_primary_rgb(raw: bytes) -> Image.Image:
    """Decode to an RGB PIL image. For HEIF/motion-photo containers Pillow's
    HEIF opener yields the primary image (the container's `pitm`), which is what
    we want - not an arbitrary auxiliary/first frame."""
    im = Image.open(io.BytesIO(raw))
    im.load()
    return im


def _thumbnail_bytes(drive, creds, file_id: str, max_side: int) -> bytes:
    meta = drive.files().get(fileId=file_id, fields="thumbnailLink", supportsAllDrives=True).execute()
    link = meta.get("thumbnailLink")
    if not link:
        raise RuntimeError("no_thumbnail_link")
    # Drive thumbnails carry a size suffix like =s220; request a larger render.
    link = re.sub(r"=s\d+(-c)?$", f"=s{max_side}", link) if re.search(r"=s\d+", link) else link + f"=s{max_side}"
    if not getattr(creds, "valid", False):
        creds.refresh(GoogleRequest())
    r = httpx.get(link, headers={"Authorization": f"Bearer {creds.token}"}, timeout=60)
    r.raise_for_status()
    return r.content


def get_display_jpeg(raw: Optional[bytes], *, drive=None, creds=None, file_id: str = None,
                     max_side: int = 1536) -> dict:
    """Return an in-memory JPEG suitable for the model, plus provenance.

    result = {jpeg, decode_source, detected_format, reason}
      decode_source: 'native' | 'drive_thumbnail' | 'failed'
    Never writes anything. `raw` may be None to force the Drive path.
    """
    fmt = detect_format(raw[:32]) if raw else "unknown"
    # Tier 1 + 3: magic-byte-aware native decode (pillow-heif handles HEIC primary).
    if raw:
        try:
            return {"jpeg": _encode_jpeg(decode_primary_rgb(raw), max_side),
                    "decode_source": "native", "detected_format": fmt, "reason": None}
        except Exception as ex:  # noqa
            native_reason = f"native_decode:{type(ex).__name__}"
    else:
        native_reason = "no_local_bytes"
    # Tier 2: Drive rendered JPEG thumbnail.
    if drive is not None and creds is not None and file_id:
        try:
            thumb = _thumbnail_bytes(drive, creds, file_id, max_side)
            return {"jpeg": _encode_jpeg(decode_primary_rgb(thumb), max_side),
                    "decode_source": "drive_thumbnail", "detected_format": fmt, "reason": None}
        except Exception as ex:  # noqa
            return {"jpeg": None, "decode_source": "failed", "detected_format": fmt,
                    "reason": f"{native_reason}; thumbnail:{type(ex).__name__}"}
    return {"jpeg": None, "decode_source": "failed", "detected_format": fmt, "reason": native_reason}


__all__ = ["detect_format", "decode_primary_rgb", "get_display_jpeg"]
