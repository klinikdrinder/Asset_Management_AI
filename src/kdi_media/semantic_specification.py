"""Resolve and fail-closed verify the locked semantic extraction contract."""
from __future__ import annotations

from dataclasses import dataclass

EXPECTED_SEMANTIC_SPEC_VERSION = "kdi_semantic_18_layer_v1"
EXPECTED_SEMANTIC_SPEC_FINGERPRINT = "6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7"


class SemanticSpecificationMismatch(RuntimeError):
    """Raised before analysis when the database contract is missing or differs."""


@dataclass(frozen=True)
class LockedSemanticSpecification:
    spec_version: str
    spec_fingerprint: str


def resolve_locked_semantic_specification(client, *, expected_version: str = EXPECTED_SEMANTIC_SPEC_VERSION,
                                          expected_fingerprint: str = EXPECTED_SEMANTIC_SPEC_FINGERPRINT) -> LockedSemanticSpecification:
    response = (client.table("semantic_specifications")
                .select("spec_version,spec_fingerprint,status,locked")
                .eq("spec_version", expected_version).limit(2).execute())
    rows = list(response.data or [])
    if len(rows) != 1:
        raise SemanticSpecificationMismatch(f"Expected exactly one semantic specification {expected_version}")
    row = rows[0]
    if row.get("status") != "LOCKED" or row.get("locked") is not True:
        raise SemanticSpecificationMismatch(f"Semantic specification {expected_version} is not locked")
    if row.get("spec_fingerprint") != expected_fingerprint:
        raise SemanticSpecificationMismatch(
            f"Semantic specification fingerprint mismatch for {expected_version}; analysis refused"
        )
    return LockedSemanticSpecification(expected_version, expected_fingerprint)
