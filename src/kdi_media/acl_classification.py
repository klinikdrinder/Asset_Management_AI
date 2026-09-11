"""ACL-only reviewed classification backfill — pure logic (no DB, no secrets).

This module powers a NEW, indexing-free workflow that lets a human reviewer set
``asset_access_control.is_clinical`` (and the two directly-coupled clinical
fields) for assets that were never processed by the semantic rollout, so they
become visible under the existing RLS policy.

It performs NO media analysis, NO embeddings, NO external AI. Advisory
``suggested_classification`` values are derived only from already-stored
metadata (source folder / filename / stored OCR-transcript text) and are never
applied without an explicit human ``review_decision``.

Nothing here touches the database; the CLI scripts inject a client and only the
``--apply`` path writes. Keep this module import-safe and side-effect free so it
is unit-testable without credentials.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

# --- Versioning -------------------------------------------------------------
WORKSHEET_VERSION = "kdi_acl_classification_worksheet_v1"
SCRIPT_VERSION = "kdi_acl_classification_backfill_v1"

# --- Live asset_access_control contract (mirrors job2 core schema checks) ----
# Verified against supabase/migrations/20260819054255_ai_search_v3_job2_core_schema.sql
SENSITIVITY_VALUES = ("GENERAL", "INTERNAL", "RESTRICTED", "CLINICAL", "HIGHLY_RESTRICTED")
INTERNAL_USAGE_VALUES = ("UNKNOWN", "ALLOWED", "RESTRICTED", "NOT_ALLOWED")
CLASSIFICATION_VALUES = ("UNCLASSIFIED", "AI_SUGGESTED", "REVIEW_REQUIRED", "VERIFIED")
NON_CLINICAL_SENSITIVITIES = ("GENERAL", "INTERNAL")
CLINICAL_SENSITIVITIES = ("RESTRICTED", "CLINICAL", "HIGHLY_RESTRICTED")

# --- Review decisions -------------------------------------------------------
REVIEW_DECISIONS = ("CLINICAL", "NON_CLINICAL", "UNRESOLVED", "SKIP")
APPLYING_DECISIONS = ("CLINICAL", "NON_CLINICAL")  # the only decisions that write
SUGGESTIONS = ("CLINICAL", "NON_CLINICAL", "UNRESOLVED")

# --- Field-safety contract --------------------------------------------------
# The apply step is permitted to write ONLY these columns. Everything else in
# asset_access_control (external_ai_status, marketing_usage_status,
# consent_status, download_allowed, internal_usage_status, review_status,
# reviewed_at/by, source/semantic/search state) must remain untouched.
ALLOWED_WRITE_KEYS = frozenset(
    {"is_clinical", "sensitivity_level", "requires_clinical_permission", "classification_status", "metadata"}
)
FORBIDDEN_WRITE_KEYS = frozenset(
    {
        "external_ai_status",
        "marketing_usage_status",
        "consent_status",
        "download_allowed",
        "internal_usage_status",
        "review_status",
        "reviewed_at",
        "reviewed_by",
        "usage_restrictions",
    }
)

# --- Worksheet columns (Part 4) ---------------------------------------------
WORKSHEET_FIELDS = [
    "asset_id",
    "ordinal",
    "filename",
    "original_filename",
    "media_type",
    "source_name",
    "current_internal_usage_status",
    "current_sensitivity_level",
    "current_is_clinical",
    "current_requires_clinical_permission",
    "current_download_allowed",
    "source_available",
    "existing_description_summary",
    "existing_content_type",
    "existing_treatment",
    "existing_subject",
    "existing_clinical_visual_summary",
    "existing_semantic_evidence_available",
    "existing_people_evidence_available",
    "suggested_classification",
    "suggestion_reason",
    "suggestion_confidence",
    # ---- human review fields (blank at generation) ----
    "review_decision",
    "reviewer",
    "reviewed_at",
    "review_notes",
]

# --- Advisory keyword evidence (stored-metadata only) -----------------------
CLINICAL_HINTS = (
    "patient", "treatment", "procedure", "hair transplant", "transplant", "fue",
    "fut", "graft", "donor", "recipient", "prp", "injection", "scalp", "clinical",
    "consultation", "before", "after", "surgery", "surgical", "post-op", "postop",
    "pre-op", "preop", "extraction", "implantation", "anesthesia", "suture",
)
NON_CLINICAL_HINTS = (
    "logo", "branding", "brand", "marketing", "advert", "advertising", "banner",
    "equipment only", "equipment", "clinic exterior", "building", "reception",
    "graphic", "poster", "template", "icon", "watermark", "administrative",
    "invoice", "document scan", "certificate", "signage",
)


def _norm(text: Optional[str]) -> str:
    return (text or "").strip().lower()


@dataclass
class AssetEvidence:
    """Stored-metadata evidence for one asset (no media, no live inference)."""

    asset_id: str
    filename: str = ""
    source_folder: str = ""
    source_name: str = ""
    description_summary: str = ""
    content_type: str = ""
    ocr_text: str = ""
    transcript_text: str = ""
    clinical_visual_text: str = ""
    anatomy_text: str = ""
    has_semantic_evidence: bool = False
    has_people_evidence: bool = False


def suggest_classification(ev: AssetEvidence) -> tuple[str, str, str]:
    """Return (suggested_classification, reason, confidence) — advisory ONLY.

    Uses only already-stored text. Never guesses: insufficient evidence yields
    ``UNRESOLVED`` so it can never silently become a production decision.
    """
    haystacks = {
        "source_folder": _norm(ev.source_folder),
        "source_name": _norm(ev.source_name),
        "filename": _norm(ev.filename),
        "description": _norm(ev.description_summary),
        "content_type": _norm(ev.content_type),
        "ocr": _norm(ev.ocr_text),
        "transcript": _norm(ev.transcript_text),
        # Stored 18-layer observation prose (people/anatomy/clinical-visual). Only clinical
        # KEYWORDS inside this text count — the mere presence of an anatomy/people assertion
        # (nearly every asset has one) must never by itself push a suggestion to CLINICAL.
        "clinical_visual": _norm(ev.clinical_visual_text),
        "anatomy": _norm(ev.anatomy_text),
    }
    joined = " | ".join(v for v in haystacks.values() if v)

    clinical_hits = sorted({h for h in CLINICAL_HINTS if h in joined})
    non_clinical_hits = sorted({h for h in NON_CLINICAL_HINTS if h in joined})

    # A folder/source signal is the strongest available stored evidence.
    strong_clinical = any(h in (haystacks["source_folder"] + " " + haystacks["source_name"]) for h in CLINICAL_HINTS)

    if clinical_hits and not non_clinical_hits:
        conf = "MEDIUM" if strong_clinical else "LOW"
        return "CLINICAL", f"clinical keyword evidence: {', '.join(clinical_hits)}", conf
    if non_clinical_hits and not clinical_hits:
        return "NON_CLINICAL", f"non-clinical keyword evidence: {', '.join(non_clinical_hits)}", "LOW"
    if clinical_hits and non_clinical_hits:
        return "UNRESOLVED", f"conflicting evidence (clinical: {', '.join(clinical_hits)}; non-clinical: {', '.join(non_clinical_hits)})", "LOW"
    return "UNRESOLVED", "insufficient stored evidence to suggest a classification", "NONE"


def decision_to_acl(decision: str, current: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """Map a reviewed decision to the ACL fields to write.

    Returns None for UNRESOLVED/SKIP (never written). Never emits a key outside
    ALLOWED_WRITE_KEYS. ``internal_usage_status`` is intentionally preserved
    (not returned).
    """
    decision = (decision or "").strip().upper()
    if decision not in APPLYING_DECISIONS:
        return None
    if decision == "CLINICAL":
        target: dict[str, Any] = {
            "is_clinical": True,
            "sensitivity_level": "CLINICAL",
            "requires_clinical_permission": True,
            "classification_status": "VERIFIED",
        }
    else:  # NON_CLINICAL
        cur_sensitivity = str(current.get("sensitivity_level") or "GENERAL").upper()
        sensitivity = cur_sensitivity if cur_sensitivity in NON_CLINICAL_SENSITIVITIES else "GENERAL"
        target = {
            "is_clinical": False,
            "sensitivity_level": sensitivity,
            "requires_clinical_permission": False,
            "classification_status": "VERIFIED",
        }
    # Safety invariant: never emit a forbidden or unknown column.
    assert set(target).issubset(ALLOWED_WRITE_KEYS - {"metadata"}), target
    assert not (set(target) & FORBIDDEN_WRITE_KEYS), target
    return target


def merge_provenance(current_metadata: Any, provenance: Mapping[str, Any]) -> dict[str, Any]:
    """Merge an ``acl_classification_backfill`` provenance block into metadata,
    preserving every existing key (e.g. an earlier ``privacy_review``)."""
    base = dict(current_metadata) if isinstance(current_metadata, dict) else {}
    base["acl_classification_backfill"] = dict(provenance)
    return base


def validate_row(row: Mapping[str, Any]) -> list[str]:
    """Structural validation of one worksheet row (decision/reviewer/timestamp)."""
    errors: list[str] = []
    decision = str(row.get("review_decision") or "").strip().upper()
    if not decision:
        errors.append("review_decision is blank")
    elif decision not in REVIEW_DECISIONS:
        errors.append(f"invalid review_decision '{decision}'")
    if not str(row.get("asset_id") or "").strip():
        errors.append("asset_id is blank")
    if decision in APPLYING_DECISIONS:
        if not str(row.get("reviewer") or "").strip():
            errors.append("reviewer is required for an applying decision")
        if not str(row.get("reviewed_at") or "").strip():
            errors.append("reviewed_at is required for an applying decision")
    return errors


def predict_visible_after_apply(
    effective_acl: Mapping[str, Any],
    source_available: bool,
    viewer_can_view_clinical: bool = True,
    upload_status: str = "PENDING",
) -> tuple[bool, str]:
    """Replicate private.can_user_view_asset_for (phase18) for one asset.

    ``effective_acl`` is the merge of the current row and the pending write.
    """
    if str(upload_status).upper() in ("FAILED", "MISSING"):
        return False, f"upload_status={upload_status} is excluded"
    if not source_available:
        return False, "source unavailable (is_asset_source_available=false)"
    internal = str(effective_acl.get("internal_usage_status") or "UNKNOWN").upper()
    if internal != "ALLOWED":
        return False, f"internal_usage_status={internal} (must be ALLOWED)"
    sensitivity = effective_acl.get("sensitivity_level")
    if sensitivity is None:
        return False, "sensitivity_level is null"
    sensitivity = str(sensitivity).upper()
    is_clinical = effective_acl.get("is_clinical")
    if is_clinical is None:
        return False, "is_clinical is null (fails the RLS gate)"
    requires_clinical = bool(effective_acl.get("requires_clinical_permission"))
    # Non-clinical branch
    if is_clinical is False and requires_clinical is False and sensitivity in NON_CLINICAL_SENSITIVITIES:
        return True, "visible via non-clinical branch (all staff)"
    # Clinical branch
    if viewer_can_view_clinical and (is_clinical is True or requires_clinical or sensitivity in CLINICAL_SENSITIVITIES):
        return True, "visible via clinical branch (requires can_view_clinical)"
    return False, "does not satisfy either visibility branch for this viewer"


@dataclass
class RowPlan:
    asset_id: str
    action: str  # APPLY | SKIP_UNRESOLVED | SKIP_DECISION | ALREADY_APPLIED | STALE | ERROR
    target: Optional[dict[str, Any]] = None
    predicted_visible: Optional[bool] = None
    visibility_reason: str = ""
    reason: str = ""
    errors: list[str] = field(default_factory=list)


def plan_row(
    row: Mapping[str, Any],
    current_acl: Optional[Mapping[str, Any]],
    source_available: bool,
    *,
    allow_reclassification: bool = False,
    viewer_can_view_clinical: bool = True,
) -> RowPlan:
    """Decide the action for one reviewed row against live current state.

    Pure and DB-free: the caller supplies ``current_acl`` (or None if the asset
    row no longer exists). This encodes staleness, no-blind-overwrite,
    idempotency, decision handling and RLS prediction in one place.
    """
    asset_id = str(row.get("asset_id") or "").strip()
    errors = validate_row(row)
    if errors:
        return RowPlan(asset_id, "ERROR", errors=errors, reason="row failed validation")

    decision = str(row["review_decision"]).strip().upper()
    if decision == "UNRESOLVED":
        return RowPlan(asset_id, "SKIP_UNRESOLVED", reason="UNRESOLVED is never applied")
    if decision == "SKIP":
        return RowPlan(asset_id, "SKIP_DECISION", reason="reviewer chose SKIP")

    if current_acl is None:
        return RowPlan(asset_id, "STALE", reason="asset_access_control row no longer exists")

    current_is_clinical = current_acl.get("is_clinical")
    # No-blind-overwrite: default only touches rows still NULL.
    if current_is_clinical is not None and not allow_reclassification:
        # Idempotency: if it already matches what we would write, report applied.
        target_preview = decision_to_acl(decision, current_acl) or {}
        already = all(current_acl.get(k) == v for k, v in target_preview.items() if k != "classification_status")
        if already:
            return RowPlan(asset_id, "ALREADY_APPLIED", reason="current values already match the decision")
        return RowPlan(asset_id, "STALE", reason="is_clinical already set; use --allow-reclassification to override")

    target = decision_to_acl(decision, current_acl)
    if target is None:  # defensive; decision already checked
        return RowPlan(asset_id, "SKIP_DECISION", reason="no ACL mapping for decision")

    effective = {**dict(current_acl), **target}
    visible, vreason = predict_visible_after_apply(
        effective, source_available, viewer_can_view_clinical=viewer_can_view_clinical
    )
    return RowPlan(asset_id, "APPLY", target=target, predicted_visible=visible, visibility_reason=vreason,
                   reason=f"apply {decision}")


def duplicate_asset_ids(rows: Iterable[Mapping[str, Any]]) -> list[str]:
    """Return asset_ids appearing more than once (worksheet must reject these)."""
    seen: dict[str, int] = {}
    for r in rows:
        aid = str(r.get("asset_id") or "").strip()
        if aid:
            seen[aid] = seen.get(aid, 0) + 1
    return sorted(a for a, n in seen.items() if n > 1)


def build_update_payload(target: Mapping[str, Any], current_metadata: Any, provenance: Mapping[str, Any]) -> dict[str, Any]:
    """Assemble the exact column write for one asset and assert field safety."""
    payload = dict(target)
    payload["metadata"] = merge_provenance(current_metadata, provenance)
    if not set(payload).issubset(ALLOWED_WRITE_KEYS) or (set(payload) & FORBIDDEN_WRITE_KEYS):
        raise AssertionError(f"payload touches forbidden/unknown columns: {set(payload)}")
    return payload


def apply_plans(db, plans, rows_by_id, current_acl, *, apply: bool, apply_ts: str,
                worksheet_sha256: str, script_version: str = SCRIPT_VERSION) -> dict[str, Any]:
    """Execute (or, when apply=False, do nothing to) the APPLY plans.

    Writes ONLY for RowPlan.action == 'APPLY' and only when ``apply`` is True.
    plan_row already enforces no-blind-overwrite and idempotency, so this is a
    thin, field-safe writer. Returns an audit summary. DB-free when apply=False.
    """
    applied = 0
    records: list[dict[str, Any]] = []
    for pl in plans:
        if pl.action != "APPLY":
            continue
        row = rows_by_id[pl.asset_id]
        cur = current_acl.get(pl.asset_id, {})
        provenance = {
            "decision": str(row["review_decision"]).strip().upper(),
            "reviewer": row.get("reviewer"),
            "reviewed_at": row.get("reviewed_at"),
            "applied_at": apply_ts,
            "script_version": script_version,
            "worksheet_sha256": worksheet_sha256,
        }
        payload = build_update_payload(pl.target, cur.get("metadata"), provenance)
        if apply:
            res = db.table("asset_access_control").update(payload).eq("asset_id", pl.asset_id).execute()
            if getattr(res, "data", None) is None:
                raise RuntimeError(f"update returned no data for {pl.asset_id}")
            applied += 1
            records.append({"asset_id": pl.asset_id,
                            "previous": {k: cur.get(k) for k in pl.target if k != "metadata"},
                            "new": {k: v for k, v in pl.target.items()}, **provenance})
    return {"applied": applied, "planned_apply": sum(1 for pl in plans if pl.action == "APPLY"), "records": records}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Columns the reviewer fills in; excluded from the integrity hash so that
# legitimate human review does not invalidate the manifest, while tampering
# with asset identity/ordinal/suggestions still does.
REVIEW_FIELDS = ("review_decision", "reviewer", "reviewed_at", "review_notes")
IMMUTABLE_FIELDS = [f for f in WORKSHEET_FIELDS if f not in REVIEW_FIELDS]


def canonical_hash(rows: Iterable[Mapping[str, Any]]) -> str:
    """Deterministic SHA-256 over the immutable (generator-owned) projection.

    Stable regardless of row order or later edits to the review columns.
    """
    projection = sorted(
        ({k: ("" if r.get(k) is None else str(r.get(k))) for k in IMMUTABLE_FIELDS} for r in rows),
        key=lambda r: r["asset_id"],
    )
    return sha256_text(json.dumps(projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def worksheet_manifest(
    *,
    project_id: str,
    generated_at: str,
    worksheet_sha256: str,
    cohort: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the integrity manifest that pairs with a generated worksheet."""
    tally = {"CLINICAL": 0, "NON_CLINICAL": 0, "UNRESOLVED": 0}
    source_unavailable = 0
    for row in cohort:
        tally[str(row.get("suggested_classification") or "UNRESOLVED")] = tally.get(
            str(row.get("suggested_classification") or "UNRESOLVED"), 0
        ) + 1
        if str(row.get("source_available")).lower() in ("false", "0", "no"):
            source_unavailable += 1
    return {
        "worksheet_version": WORKSHEET_VERSION,
        "script_version": SCRIPT_VERSION,
        "project_id": project_id,
        "generated_at": generated_at,
        "cohort_count": len(cohort),
        "worksheet_sha256": worksheet_sha256,
        "suggestion_tally": tally,
        "source_unavailable": source_unavailable,
        "approved": False,
        "applied": False,
        "note": "SUGGESTIONS ARE ADVISORY. NOT APPROVED. NOT APPLIED. Human review required.",
    }
