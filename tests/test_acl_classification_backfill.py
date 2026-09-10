"""Tests for the ACL-only reviewed classification backfill (no DB, no secrets)."""
from __future__ import annotations

import unittest

from kdi_media.acl_classification import (
    ALLOWED_WRITE_KEYS,
    FORBIDDEN_WRITE_KEYS,
    AssetEvidence,
    apply_plans,
    canonical_hash,
    decision_to_acl,
    duplicate_asset_ids,
    plan_row,
    predict_visible_after_apply,
    suggest_classification,
)

REVIEWER = {"reviewer": "KDI_OPERATOR", "reviewed_at": "2026-09-10T00:00:00Z"}
NULL_ACL = {"is_clinical": None, "sensitivity_level": "GENERAL", "internal_usage_status": "ALLOWED",
            "requires_clinical_permission": None, "metadata": {}}


def row(asset_id="a1", decision="CLINICAL", **kw):
    r = {"asset_id": asset_id, "review_decision": decision, "reviewer": "KDI_OPERATOR",
         "reviewed_at": "2026-09-10T00:00:00Z", "review_notes": ""}
    r.update(kw)
    return r


class FakeQuery:
    def __init__(self, client, table):
        self.client, self.table_name, self._payload = client, table, None

    def update(self, payload):
        self._payload = payload
        return self

    def eq(self, *_):
        return self

    def is_(self, *_):
        return self

    def execute(self):
        self.client.updates.append({"table": self.table_name, "payload": self._payload})

        class R:
            data = [{"ok": True}]

        return R()


class FakeClient:
    def __init__(self):
        self.updates = []

    def table(self, name):
        return FakeQuery(self, name)


class DecisionMappingTests(unittest.TestCase):
    def test_1_null_to_clinical(self):
        pl = plan_row(row(decision="CLINICAL"), NULL_ACL, source_available=True)
        self.assertEqual(pl.action, "APPLY")
        self.assertEqual(pl.target["is_clinical"], True)
        self.assertEqual(pl.target["sensitivity_level"], "CLINICAL")
        self.assertEqual(pl.target["requires_clinical_permission"], True)
        self.assertTrue(pl.predicted_visible)  # admin can_view_clinical

    def test_2_null_to_non_clinical(self):
        pl = plan_row(row(decision="NON_CLINICAL"), NULL_ACL, source_available=True)
        self.assertEqual(pl.action, "APPLY")
        self.assertEqual(pl.target["is_clinical"], False)
        self.assertIn(pl.target["sensitivity_level"], ("GENERAL", "INTERNAL"))
        self.assertEqual(pl.target["requires_clinical_permission"], False)
        self.assertTrue(pl.predicted_visible)  # non-clinical branch, all staff

    def test_3_unresolved_no_write(self):
        pl = plan_row(row(decision="UNRESOLVED"), NULL_ACL, source_available=True)
        self.assertEqual(pl.action, "SKIP_UNRESOLVED")
        self.assertIsNone(pl.target)

    def test_4_skip_no_write(self):
        pl = plan_row(row(decision="SKIP"), NULL_ACL, source_available=True)
        self.assertEqual(pl.action, "SKIP_DECISION")
        self.assertIsNone(pl.target)

    def test_5_existing_classified_skipped_by_default(self):
        current = {**NULL_ACL, "is_clinical": True, "sensitivity_level": "CLINICAL", "requires_clinical_permission": True}
        # matching decision -> already applied (a form of skip)
        self.assertEqual(plan_row(row(decision="CLINICAL"), current, True).action, "ALREADY_APPLIED")
        # conflicting decision -> stale, still not overwritten by default
        self.assertEqual(plan_row(row(decision="NON_CLINICAL"), current, True).action, "STALE")
        # explicit override allowed
        self.assertEqual(plan_row(row(decision="NON_CLINICAL"), current, True, allow_reclassification=True).action, "APPLY")

    def test_6_duplicate_asset_id_detected(self):
        rows = [row(asset_id="dup"), row(asset_id="dup"), row(asset_id="unique")]
        self.assertEqual(duplicate_asset_ids(rows), ["dup"])

    def test_7_missing_reviewer_rejected(self):
        pl = plan_row(row(decision="CLINICAL", reviewer=""), NULL_ACL, True)
        self.assertEqual(pl.action, "ERROR")
        self.assertTrue(any("reviewer" in e for e in pl.errors))

    def test_8_missing_reviewed_at_rejected(self):
        pl = plan_row(row(decision="CLINICAL", reviewed_at=""), NULL_ACL, True)
        self.assertEqual(pl.action, "ERROR")
        self.assertTrue(any("reviewed_at" in e for e in pl.errors))

    def test_9_stale_db_state(self):
        # asset_access_control row no longer exists
        self.assertEqual(plan_row(row(decision="CLINICAL"), None, True).action, "STALE")

    def test_10_dry_run_zero_writes(self):
        db = FakeClient()
        plans = [plan_row(row(asset_id="a1", decision="CLINICAL"), NULL_ACL, True),
                 plan_row(row(asset_id="a2", decision="NON_CLINICAL"), NULL_ACL, True)]
        rows_by_id = {"a1": row(asset_id="a1", decision="CLINICAL"), "a2": row(asset_id="a2", decision="NON_CLINICAL")}
        out = apply_plans(db, plans, rows_by_id, {"a1": NULL_ACL, "a2": NULL_ACL},
                          apply=False, apply_ts="t", worksheet_sha256="h")
        self.assertEqual(out["applied"], 0)
        self.assertEqual(len(db.updates), 0)  # ZERO production writes in dry-run

    def test_11_unrelated_fields_untouched(self):
        for decision in ("CLINICAL", "NON_CLINICAL"):
            target = decision_to_acl(decision, NULL_ACL)
            self.assertTrue(set(target).issubset(ALLOWED_WRITE_KEYS - {"metadata"}))
            self.assertFalse(set(target) & FORBIDDEN_WRITE_KEYS)
            for forbidden in ("external_ai_status", "marketing_usage_status", "consent_status",
                              "download_allowed", "internal_usage_status"):
                self.assertNotIn(forbidden, target)

    def test_12_idempotent_rerun(self):
        db = FakeClient()
        r = row(asset_id="a1", decision="CLINICAL")
        # first apply against NULL state
        plans1 = [plan_row(r, NULL_ACL, True)]
        apply_plans(db, plans1, {"a1": r}, {"a1": NULL_ACL}, apply=True, apply_ts="t", worksheet_sha256="h")
        self.assertEqual(len(db.updates), 1)
        # simulate post-apply live state, rerun same worksheet
        applied_state = {**NULL_ACL, "is_clinical": True, "sensitivity_level": "CLINICAL", "requires_clinical_permission": True}
        db2 = FakeClient()
        plans2 = [plan_row(r, applied_state, True)]
        self.assertEqual(plans2[0].action, "ALREADY_APPLIED")
        out = apply_plans(db2, plans2, {"a1": r}, {"a1": applied_state}, apply=True, apply_ts="t", worksheet_sha256="h")
        self.assertEqual(out["applied"], 0)
        self.assertEqual(len(db2.updates), 0)  # no additional changes

    def test_13_invalid_decision_rejected(self):
        pl = plan_row(row(decision="MAYBE"), NULL_ACL, True)
        self.assertEqual(pl.action, "ERROR")

    def test_14_source_unavailable_predicts_hidden(self):
        pl = plan_row(row(decision="CLINICAL"), NULL_ACL, source_available=False)
        self.assertEqual(pl.action, "APPLY")           # classification still valid
        self.assertFalse(pl.predicted_visible)          # but would remain hidden
        self.assertIn("source", pl.visibility_reason.lower())


class SuggestionTests(unittest.TestCase):
    def test_fixture_A_hair_transplant_clinical(self):
        s, _, _ = suggest_classification(AssetEvidence("A", source_folder="ALL PATIENT REVIEW", filename="fue_graft.mp4"))
        self.assertEqual(s, "CLINICAL")

    def test_fixture_B_consultation_clinical(self):
        s, _, _ = suggest_classification(AssetEvidence("B", filename="patient_consultation.mp4"))
        self.assertEqual(s, "CLINICAL")

    def test_fixture_C_equipment_non_clinical(self):
        s, _, _ = suggest_classification(AssetEvidence("C", source_folder="Branding", filename="clinic_logo.png"))
        self.assertEqual(s, "NON_CLINICAL")

    def test_fixture_D_ambiguous_unresolved(self):
        s, _, conf = suggest_classification(AssetEvidence("D", filename="IMG_0554.MP4"))
        self.assertEqual(s, "UNRESOLVED")
        self.assertEqual(conf, "NONE")

    def test_conflicting_evidence_unresolved(self):
        s, _, _ = suggest_classification(AssetEvidence("E", source_folder="patient", filename="clinic_logo.png"))
        self.assertEqual(s, "UNRESOLVED")


class PredictionAndHashTests(unittest.TestCase):
    def test_null_is_clinical_hidden(self):
        vis, reason = predict_visible_after_apply(NULL_ACL, True)
        self.assertFalse(vis)
        self.assertIn("is_clinical", reason)

    def test_internal_usage_not_allowed_hidden(self):
        acl = {"is_clinical": True, "sensitivity_level": "CLINICAL", "internal_usage_status": "UNKNOWN",
               "requires_clinical_permission": True}
        vis, reason = predict_visible_after_apply(acl, True)
        self.assertFalse(vis)
        self.assertIn("internal_usage_status", reason)

    def test_clinical_requires_can_view_clinical(self):
        acl = {"is_clinical": True, "sensitivity_level": "CLINICAL", "internal_usage_status": "ALLOWED",
               "requires_clinical_permission": True}
        self.assertTrue(predict_visible_after_apply(acl, True, viewer_can_view_clinical=True)[0])
        self.assertFalse(predict_visible_after_apply(acl, True, viewer_can_view_clinical=False)[0])

    def test_canonical_hash_ignores_review_edits(self):
        base = {f: "" for f in ("asset_id", "ordinal", "filename", "original_filename", "media_type",
                                "source_name", "source_folder", "source_reference",
                                "current_internal_usage_status", "current_sensitivity_level",
                                "current_is_clinical", "current_requires_clinical_permission",
                                "current_download_allowed", "source_available",
                                "existing_description_summary", "existing_content_type",
                                "existing_treatment", "existing_subject", "existing_clinical_visual_summary",
                                "existing_semantic_evidence_available", "existing_people_evidence_available",
                                "suggested_classification", "suggestion_reason", "suggestion_confidence")}
        base["asset_id"] = "a1"
        r_clean = dict(base, review_decision="", reviewer="", reviewed_at="", review_notes="")
        r_reviewed = dict(base, review_decision="CLINICAL", reviewer="X", reviewed_at="t", review_notes="ok")
        self.assertEqual(canonical_hash([r_clean]), canonical_hash([r_reviewed]))  # review edits don't change hash
        tampered = dict(r_reviewed, suggested_classification="NON_CLINICAL")
        self.assertNotEqual(canonical_hash([r_clean]), canonical_hash([tampered]))  # tampering does


if __name__ == "__main__":
    unittest.main()
