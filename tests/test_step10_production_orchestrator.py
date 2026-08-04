from pathlib import Path
import unittest

from kdi_media.step10_production import ProductionOptions, ProductionOrchestrator


ROOT = "1CdmowWV5TAk5R9D5yl2cOT8Plx3ihZgl"


def options(**changes):
    values = {
        "execute": False,
        "authorize": False,
        "expected_total": 878,
        "expected_completed": 8,
        "expected_remaining": 870,
        "root_id": ROOT,
        "source_profile": "source_readonly",
        "destination_profile": "destination_write",
        "batch_size": 50,
        "report_path": Path("report.json"),
        "pilot_report_path": Path("pilot.json"),
        "spool_root": Path("spool"),
    }
    values.update(changes)
    return ProductionOptions(**values)


class ProductionGateTests(unittest.TestCase):
    def test_default_is_plan_only(self):
        report = ProductionOrchestrator(None, options()).plan()
        self.assertEqual(report["mode"], "PLAN_ONLY")
        self.assertEqual(report["database_writes"], 0)
        self.assertEqual(report["drive_requests"], 0)

    def test_execute_requires_authorization(self):
        with self.assertRaisesRegex(ValueError, "authorization"):
            options(execute=True).validate()

    def test_total_count_is_exact(self):
        with self.assertRaisesRegex(ValueError, "878/8/870"):
            options(expected_total=879).validate()

    def test_completed_count_is_exact(self):
        with self.assertRaisesRegex(ValueError, "878/8/870"):
            options(expected_completed=7).validate()

    def test_remaining_count_is_exact(self):
        with self.assertRaisesRegex(ValueError, "878/8/870"):
            options(expected_remaining=869).validate()

    def test_batch_size_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 50"):
            options(batch_size=51).validate()

    def test_source_profile_is_isolated(self):
        with self.assertRaisesRegex(ValueError, "source_readonly"):
            options(source_profile="destination_write").validate()

    def test_destination_profile_is_isolated(self):
        with self.assertRaisesRegex(ValueError, "destination_write"):
            options(destination_profile="source_readonly").validate()

    def test_outside_root_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "approved KDI Master"):
            options(root_id="outside").validate()

    def test_live_plan_retains_conservative_concurrency(self):
        report = ProductionOrchestrator(
            None, options(execute=True, authorize=True)
        ).plan()
        self.assertEqual(report["concurrency"], 1)
        self.assertEqual(report["batch_size"], 50)


if __name__ == "__main__":
    unittest.main()
