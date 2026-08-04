import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from scripts.provision_dashboard_reader import (
    APPROVED_EMAIL,
    confirm_existing_email,
    REQUIRED_METADATA,
    claims_are_exact,
    find_user,
    sanitized_result,
    validate_request,
)


class ProvisioningSafetyTests(unittest.TestCase):
    def test_claim_payload_has_exact_types(self):
        self.assertEqual(REQUIRED_METADATA["kdi_media_reader"], "true")
        self.assertIs(REQUIRED_METADATA["kdi_media_access"], True)

    def test_refuses_without_explicit_authorization(self):
        with self.assertRaisesRegex(RuntimeError, "authorization"):
            validate_request(APPROVED_EMAIL, False)

    def test_refuses_unapproved_email(self):
        with self.assertRaisesRegex(RuntimeError, "approved identity"):
            validate_request("other@example.com", True)

    def test_duplicate_user_handling(self):
        users = [
            SimpleNamespace(email=APPROVED_EMAIL),
            SimpleNamespace(email=APPROVED_EMAIL),
        ]
        with self.assertRaisesRegex(RuntimeError, "Duplicate"):
            find_user(users, APPROVED_EMAIL)

    def test_existing_user_is_reused(self):
        user = SimpleNamespace(email=APPROVED_EMAIL)
        self.assertIs(find_user([user], APPROVED_EMAIL), user)

    def test_unintended_kdi_claim_is_rejected(self):
        metadata = dict(REQUIRED_METADATA, kdi_admin=True)
        self.assertFalse(claims_are_exact(metadata))

    def test_sanitized_output_contains_no_token_or_password(self):
        result = sanitized_result("OK", True)
        parsed = json.loads(result)
        self.assertNotIn("token", result.lower())
        self.assertNotIn("password", result.lower())
        self.assertEqual(parsed["reader_email"], "kd***@gmail.com")

    def test_confirmation_only_refuses_missing_user(self):
        with self.assertRaisesRegex(RuntimeError, "existing reader"):
            confirm_existing_email(Mock(), None)

    def test_confirmation_only_preserves_user_and_claims(self):
        existing = SimpleNamespace(
            id="reader-id",
            app_metadata=dict(REQUIRED_METADATA),
        )
        confirmed = SimpleNamespace(
            id="reader-id",
            app_metadata=dict(REQUIRED_METADATA),
            email_confirmed_at="sanitized-present-marker",
        )
        admin = Mock()
        admin.auth.admin.update_user_by_id.return_value = SimpleNamespace(
            user=confirmed
        )

        result = confirm_existing_email(admin, existing)

        self.assertIs(result, confirmed)
        admin.auth.admin.update_user_by_id.assert_called_once_with(
            "reader-id",
            {"email_confirm": True},
        )

    def test_confirmation_only_rejects_claim_changes(self):
        existing = SimpleNamespace(
            id="reader-id",
            app_metadata=dict(REQUIRED_METADATA),
        )
        changed = SimpleNamespace(
            id="reader-id",
            app_metadata=dict(REQUIRED_METADATA, kdi_admin=True),
            email_confirmed_at="sanitized-present-marker",
        )
        admin = Mock()
        admin.auth.admin.update_user_by_id.return_value = SimpleNamespace(
            user=changed
        )
        with self.assertRaisesRegex(RuntimeError, "metadata"):
            confirm_existing_email(admin, existing)


if __name__ == "__main__":
    unittest.main()
