from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import tempfile
import unittest
import json
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch


SCRIPT = Path("scripts/deploy_step10_legacy_status_fix.py")
SPEC = importlib.util.spec_from_file_location("step10_status_deploy", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def arguments(report: Path, **changes):
    values = {
        "execute": True,
        "diagnostic": False,
        "database_only": True,
        "expected_migration": MODULE.MIGRATION,
        "report_path": report,
        "supabase_region": None,
        "database_host": None,
        "database_port": None,
        "database_user": None,
    }
    values.update(changes)
    return argparse.Namespace(**values)


class FakeCursor:
    def __init__(self):
        self.statements = []
        self.description = None
        self._result_sets = []
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql):
        self.statements.append(sql)
        if sql.strip().lower() == "select 1":
            self._rows = [(1,)]
            self.description = ("result",)
            return
        if "STEP_10_LEGACY_STATUS_MAPPING_VERIFIED" in sql:
            self._result_sets = [[(MODULE.MARKER,)]]
        else:
            self._result_sets = []
        self.description = None

    def nextset(self):
        if not self._result_sets:
            self.description = None
            return False
        self._rows = self._result_sets.pop(0)
        self.description = ("result",)
        return True

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0]


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


class StatusDeploymentRunnerTests(unittest.TestCase):
    def test_missing_execute_gate_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(MODULE.DeploymentSafetyError):
                MODULE.validate_scope(
                    arguments(Path(tmp) / "report.json", execute=False)
                )

    def test_missing_database_only_gate_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(MODULE.DeploymentSafetyError):
                MODULE.validate_scope(
                    arguments(Path(tmp) / "report.json", database_only=False)
                )

    def test_only_004_migration_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(MODULE.DeploymentSafetyError):
                MODULE.validate_scope(
                    arguments(
                        Path(tmp) / "report.json",
                        expected_migration=Path(
                            "supabase/migrations/"
                            "202607310003_fix_step10_legacy_status_mapping.sql"
                        ),
                    )
                )

    def test_project_connection_must_match(self):
        with self.assertRaises(MODULE.DeploymentSafetyError):
            MODULE.connection_candidates(
                "https://abcdefghijklmnopqrst.supabase.co", None,
                {"SUPABASE_DB_URL": "postgresql://postgres:secret@db.other.supabase.co/postgres"},
            )

    def test_project_reference_extraction_and_malformed_url_rejection(self):
        self.assertEqual(
            MODULE.project_reference("https://abcdefghijklmnopqrst.supabase.co"),
            "abcdefghijklmnopqrst",
        )
        for value in (
            "http://abcdefghijklmnopqrst.supabase.co",
            "https://too-short.supabase.co",
            "https://abcdefghijklmnopqrst.supabase.co.evil.example",
        ):
            with self.subTest(value=value), self.assertRaises(MODULE.DeploymentSafetyError):
                MODULE.project_reference(value)

    def test_non_postgres_connection_is_rejected(self):
        with self.assertRaises(MODULE.DeploymentSafetyError):
            MODULE.connection_candidates(
                "https://abcdefghijklmnopqrst.supabase.co", None,
                {"SUPABASE_DB_URL": "https://abcdefghijklmnopqrst.supabase.co"},
            )

    def test_deploy_executes_only_migration_and_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            connection = FakeConnection()
            factory_calls = []

            def factory(url, **kwargs):
                factory_calls.append((url, kwargs))
                return connection

            environment = {
                "SUPABASE_URL": "https://abcdefghijklmnopqrst.supabase.co",
                "SUPABASE_DB_URL": (
                    "postgresql://postgres:secret@"
                    "db.abcdefghijklmnopqrst.supabase.co/postgres"
                ),
            }
            with patch.dict("os.environ", environment, clear=False):
                report = MODULE.deploy(
                    arguments(Path(tmp) / "report.json"), factory
                )
            self.assertTrue(report["deployed"])
            self.assertEqual(report["verification_marker"], MODULE.MARKER)
            self.assertEqual(report["unrelated_migrations_applied"], 0)
            self.assertEqual(len(connection.cursor_instance.statements), 3)
            self.assertEqual(factory_calls[0][1], {"autocommit": True})
            self.assertTrue(connection.closed)

    def test_report_contains_checksum_not_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            connection = FakeConnection()
            environment = {
                "SUPABASE_URL": "https://abcdefghijklmnopqrst.supabase.co",
                "SUPABASE_DB_URL": (
                    "postgresql://postgres:secret@"
                    "db.abcdefghijklmnopqrst.supabase.co/postgres"
                ),
            }
            with patch.dict("os.environ", environment, clear=False):
                report = MODULE.deploy(
                    arguments(Path(tmp) / "report.json"),
                    lambda *_args, **_kwargs: connection,
                )
            serialized = str(report)
            self.assertNotIn("secret", serialized)
            self.assertEqual(len(report["migration_sha256"]), 64)

    def test_safe_error_redacts_database_url(self):
        secret = "postgresql://postgres:secret@db.abcdefghijklmnopqrst.supabase.co/db"
        with patch.dict(
            "os.environ", {"SUPABASE_DB_URL": secret}, clear=False
        ):
            safe = MODULE.safe_error(RuntimeError(secret))
        self.assertNotIn(secret, safe)
        self.assertIn("REDACTED", safe)

    def test_direct_and_pooler_candidates_have_correct_contract(self):
        candidates = MODULE.connection_candidates(
            "https://abcdefghijklmnopqrst.supabase.co", "p@ss word",
            {"SUPABASE_REGION": "ap-southeast-1"},
        )
        session, transaction, direct = candidates
        self.assertEqual((direct.host, direct.port, direct.username),
                         ("db.abcdefghijklmnopqrst.supabase.co", 5432, "postgres"))
        self.assertEqual((session.host, session.port, session.username),
                         ("aws-0-ap-southeast-1.pooler.supabase.com", 5432,
                          "postgres.abcdefghijklmnopqrst"))
        self.assertEqual(transaction.port, 6543)
        self.assertTrue(transaction.transaction_pooler)
        for candidate in candidates:
            self.assertIn("sslmode=require", candidate.dsn)
            self.assertIn("connect_timeout=5", candidate.dsn)
            self.assertNotIn("p@ss word", candidate.dsn)

    def test_missing_region_is_rejected(self):
        with self.assertRaisesRegex(MODULE.DeploymentSafetyError, "Missing Supabase region"):
            MODULE.connection_candidates(
                "https://abcdefghijklmnopqrst.supabase.co", "secret", {}
            )

    def test_explicit_region_constructs_session_and_transaction_poolers(self):
        candidates = MODULE.connection_candidates(
            "https://abcdefghijklmnopqrst.supabase.co", "secret", {},
            region="ap-southeast-1",
        )
        self.assertEqual(
            [(item.endpoint_type, item.host, item.port, item.username) for item in candidates[:2]],
            [
                ("session_pooler", "aws-0-ap-southeast-1.pooler.supabase.com", 5432,
                 "postgres.abcdefghijklmnopqrst"),
                ("transaction_pooler", "aws-0-ap-southeast-1.pooler.supabase.com", 6543,
                 "postgres.abcdefghijklmnopqrst"),
            ],
        )

    def test_explicit_host_override_and_port_validation(self):
        candidates = MODULE.connection_candidates(
            "https://abcdefghijklmnopqrst.supabase.co", "secret", {},
            database_host="custom.abcdefghijklmnopqrst.database.example",
            database_port=5432,
            database_user="postgres.abcdefghijklmnopqrst",
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].endpoint_type, "explicit")
        for port in (0, 65536):
            with self.subTest(port=port), self.assertRaises(MODULE.DeploymentSafetyError):
                MODULE.connection_candidates(
                    "https://abcdefghijklmnopqrst.supabase.co", "secret", {},
                    database_host="custom.abcdefghijklmnopqrst.database.example",
                    database_port=port,
                    database_user="postgres.abcdefghijklmnopqrst",
                )

    def test_ssl_is_forced_and_candidate_reporting_is_sanitized(self):
        summary = MODULE.candidate_summary(
            "https://abcdefghijklmnopqrst.supabase.co", {},
            region="ap-southeast-1",
        )
        serialized = json.dumps(summary)
        self.assertTrue(all(item["sslmode"] == "require" for item in summary))
        self.assertNotIn("abcdefghijklmnopqrst", serialized)
        self.assertIn("postgres.[project-ref]", serialized)
        self.assertNotIn("__ENDPOINT_PREFLIGHT_ONLY__", serialized)

    def test_endpoint_configuration_classification_is_distinct(self):
        self.assertEqual(
            MODULE._blocked_verdict("configuration"),
            "BLOCKED_DATABASE_ENDPOINT_CONFIGURATION",
        )
        self.assertEqual(
            MODULE._blocked_verdict("postgresql"),
            "BLOCKED_DATABASE_OPERATION",
        )

    def test_candidate_summary_can_be_printed_without_password_logging(self):
        stream = StringIO()
        secret = "never-log-this-password"
        with redirect_stderr(stream):
            print(json.dumps({"connection_candidates": MODULE.candidate_summary(
                "https://abcdefghijklmnopqrst.supabase.co",
                {"SUPABASE_REGION": "ap-southeast-1"},
            )}), file=stream)
        self.assertNotIn(secret, stream.getvalue())
        self.assertNotIn("abcdefghijklmnopqrst", stream.getvalue())

    def test_dns_and_authentication_failures_are_classified(self):
        self.assertEqual(
            MODULE.classify_exception(OSError("getaddrinfo failed")),
            "network_dns",
        )
        InvalidPassword = type("InvalidPassword", (Exception,), {})
        self.assertEqual(
            MODULE.classify_exception(InvalidPassword("password authentication failed")),
            "authentication",
        )

    def test_pooler_fallback_stops_on_first_success(self):
        candidates = MODULE.connection_candidates(
            "https://abcdefghijklmnopqrst.supabase.co", "secret",
            {"SUPABASE_REGION": "ap-southeast-1"},
        )
        calls = []
        connection = FakeConnection()
        def factory(dsn, **_kwargs):
            calls.append(dsn)
            if len(calls) == 1:
                raise OSError("getaddrinfo failed")
            return connection
        selected, candidate, attempts = MODULE._connect_first(
            candidates, factory, "secret"
        )
        self.assertIs(selected, connection)
        self.assertEqual(candidate.endpoint_type, "transaction_pooler")
        self.assertEqual(len(calls), 2)
        self.assertEqual(attempts[0]["failure_category"], "network_dns")

    def test_transaction_pooler_is_only_used_for_compatible_sql(self):
        self.assertTrue(MODULE.transaction_pooler_compatible("begin; alter table x add y int; commit;"))
        self.assertFalse(MODULE.transaction_pooler_compatible("listen deployment_events;"))

    def test_empty_prompt_password_is_rejected(self):
        with patch("getpass.getpass", return_value=""):
            with self.assertRaises(MODULE.DeploymentSafetyError):
                MODULE.prompt_password()


class ExactMigrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MODULE.MIGRATION.read_text(encoding="utf-8").lower()
        cls.verifier = MODULE.VERIFIER.read_text(encoding="utf-8").lower()

    def test_original_eight_and_only_three_new_statuses(self):
        for value in (
            "queued",
            "running",
            "success",
            "skipped",
            "duplicate",
            "failed",
            "retrying",
            "cancelled",
            "info",
            "warning",
            "error",
        ):
            self.assertIn(f"'{value}'", self.sql)
        self.assertNotIn("'pending'", self.sql)

    def test_exact_constraint_name_is_used(self):
        self.assertIn(
            "drop constraint migration_events_status_check", self.sql
        )
        self.assertIn(
            "add constraint migration_events_status_check", self.sql
        )

    def test_existing_rows_are_preflighted(self):
        self.assertIn(
            "existing migration_events rows violate", self.sql
        )

    def test_reapplication_is_safe(self):
        self.assertIn("replacement_values", self.sql)
        self.assertIn("if not (", self.sql)

    def test_verifier_uses_pg_catalog_strpos(self):
        self.assertIn("pg_catalog.strpos(", self.verifier)
        self.assertNotIn("pg_catalog.position(", self.verifier)

    def test_verification_probes_are_rolled_back(self):
        self.assertTrue(self.verifier.rstrip().endswith("rollback;"))
        self.assertIn("insert into public.migration_events", self.verifier)
        invalid_probe = self.verifier.rsplit(
            "'step10_arbitrary_invalid_event'", 1
        )[1][:160]
        self.assertIn("'info'", invalid_probe)


if __name__ == "__main__":
    unittest.main()
