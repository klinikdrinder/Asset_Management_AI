from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import tempfile

import pytest
from PIL import Image, ImageDraw

from kdi_media.image_analysis import (
    ImageAnalysisConfig,
    ImageAnalysisProcessor,
    canonical_fingerprint,
    file_sha256,
    functional_output,
    suppress_redundant_regions,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "semantic-search" / "kdi_image_analysis_v1.json"
SPEC_FP = "ea74ef9c07f8341342817bc924d78fb6ae28049a8a29b6c571172a77c923308c"


def fixture(path: Path, size=(640, 400), orientation=None, feature=True):
    image = Image.new("RGB", size, "#808080")
    if feature:
        draw = ImageDraw.Draw(image)
        draw.rectangle((size[0]//3, size[1]//4, size[0]*3//4, size[1]*3//4), fill="white", outline="black", width=8)
    exif = Image.Exif()
    if orientation is not None:
        exif[274] = orientation
    image.save(path, "JPEG", exif=exif)


def process(path: Path):
    fp = file_sha256(path)
    return ImageAnalysisProcessor(ImageAnalysisConfig.load(CONFIG_PATH)).process(path, asset_id="00000000-0000-4000-8000-000000000004", filename=path.name, source_fingerprint=fp, semantic_spec_version="semantic_index_v1", semantic_spec_fingerprint=SPEC_FP, pilot_manifest_version="kdi_semantic_pilot_v1")


def test_configuration_fingerprint_is_canonical():
    config = ImageAnalysisConfig.load(CONFIG_PATH)
    assert config.fingerprint == canonical_fingerprint(json.loads(CONFIG_PATH.read_text()))
    assert config.values["processor_version"] == "kdi_image_analysis_v1"


@pytest.mark.parametrize("size", [(640, 400), (400, 640), (500, 500)])
def test_full_image_fallback_and_coordinates(size):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "fixture.jpg"; fixture(path, size=size, feature=False)
        result = process(path)
        assert result["status"] == "COMPLETED"
        full = result["regions"][0]
        assert full["region_type"] == "FULL_IMAGE"
        assert (full["x1"], full["y1"], full["x2"], full["y2"]) == (0, 0, *size)
        assert full["normalized_coordinates"] == {"x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0}


def test_exif_orientation_is_normalized_without_rewriting_source():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "rotated.jpg"; fixture(path, size=(640, 400), orientation=6)
        before = path.read_bytes(); result = process(path)
        assert result["technical_metadata"]["source_width"] == 640
        assert result["technical_metadata"]["analysis_width"] == 400
        assert result["technical_metadata"]["analysis_height"] == 640
        assert result["technical_metadata"]["orientation"] == "PORTRAIT"
        assert path.read_bytes() == before


def test_every_region_coordinate_is_valid_and_normalized():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "regions.jpg"; fixture(path)
        result = process(path); width = result["technical_metadata"]["analysis_width"]; height = result["technical_metadata"]["analysis_height"]
        for region in result["regions"]:
            assert 0 <= region["x1"] < region["x2"] <= width
            assert 0 <= region["y1"] < region["y2"] <= height
            assert all(0.0 <= value <= 1.0 for value in region["normalized_coordinates"].values())


def test_redundancy_suppression_and_different_purpose_retention():
    candidates = [
        {"region_type":"OTHER_SALIENT_REGION","x1":0,"y1":0,"x2":100,"y2":100,"selection_score":0.9},
        {"region_type":"OTHER_SALIENT_REGION","x1":2,"y1":2,"x2":98,"y2":98,"selection_score":0.8},
        {"region_type":"TEXT_REGION_CANDIDATE","x1":2,"y1":2,"x2":98,"y2":98,"selection_score":0.7},
    ]
    kept, removed = suppress_redundant_regions(candidates, iou_threshold=.65, containment_threshold=.9, limit=5)
    assert len(kept) == 2 and removed == 1
    assert {x["region_type"] for x in kept} == {"OTHER_SALIENT_REGION", "TEXT_REGION_CANDIDATE"}


def test_repeat_output_is_functionally_identical():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "same.jpg"; fixture(path)
        assert functional_output(process(path)) == functional_output(process(path))


@pytest.mark.parametrize("payload", [b"not a jpeg", b"\xff\xd8\xff", b""])
def test_invalid_or_truncated_image_fails_in_isolation(payload):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "bad.jpg"; path.write_bytes(payload)
        result = process(path)
        assert result["status"] == "FAILED"
        assert result["failure"]["reason"]


def test_source_identity_mismatch_fails_before_analysis():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "identity.jpg"; fixture(path)
        result = ImageAnalysisProcessor(ImageAnalysisConfig.load(CONFIG_PATH)).process(path, asset_id="00000000-0000-4000-8000-000000000004", filename=path.name, source_fingerprint="0"*64, semantic_spec_version="semantic_index_v1", semantic_spec_fingerprint=SPEC_FP, pilot_manifest_version="kdi_semantic_pilot_v1")
        assert result["status"] == "FAILED"
        assert "SOURCE_IDENTITY_MISMATCH" in result["failure"]["reason"]


def test_image_applicability_and_negative_assertion_contract():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "states.jpg"; fixture(path)
        result = process(path)
        assert result["applicability"]["3"]["state"] == "NOT_APPLICABLE"
        assert result["applicability"]["14"]["state"] == "NOT_APPLICABLE"
        assert result["applicability"]["15"]["state"] == "UNKNOWN"
        assert not any(result["negative_assertion_safety"].values())


def test_engine_has_no_production_write_path():
    text = (ROOT / "src" / "kdi_media" / "image_analysis.py").read_text().lower()
    for forbidden in ("supabase", ".table(", "execute_sql", "apply_migration", "production write"):
        assert forbidden not in text
