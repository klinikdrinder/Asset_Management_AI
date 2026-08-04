from __future__ import annotations

import unittest

from kdi_media.step9_canonicalization import (
    CanonicalizationError,
    build_canonical_groups,
    canonicalize_groups,
)


HASH_A = "a" * 64
HASH_B = "b" * 64


def row(
    source_id: str,
    *,
    content_hash: str = HASH_A,
    folder: str = "folder-a",
    google_id: str | None = None,
    name: str = "same.jpg",
    status: str = "HASHED",
    decision: str = "TAKE",
) -> dict:
    return {
        "id": source_id,
        "source_folder_id": folder,
        "google_file_id": google_id or f"google-{source_id}",
        "file_name": name,
        "mime_type": "image/jpeg",
        "file_extension": "jpg",
        "size_bytes": 3,
        "hash_algorithm": "SHA-256",
        "content_sha256": content_hash,
        "hash_status": status,
        "decision": decision,
        "processing_status": "READY" if decision == "TAKE" else "SKIPPED",
        "relative_path": f"private/{source_id}",
    }


class MemoryRepository:
    def __init__(self) -> None:
        self.assets = {}
        self.links = {}
        self.asset_inserts = 0
        self.link_inserts = 0
        self.fail_after_links: int | None = None

    def create_or_reuse_asset(self, values):
        content_hash = values["content_hash"]
        if content_hash not in self.assets:
            self.asset_inserts += 1
            self.assets[content_hash] = {"id": f"asset-{content_hash[:4]}", **values}
        return self.assets[content_hash]

    def create_or_reuse_link(
        self, *, asset_id, source_file_id, relationship_type
    ):
        if (
            self.fail_after_links is not None
            and self.link_inserts >= self.fail_after_links
        ):
            raise RuntimeError("simulated interruption")
        existing = self.links.get(source_file_id)
        if existing and existing["asset_id"] != asset_id:
            raise CanonicalizationError("conflicting link")
        if not existing:
            self.link_inserts += 1
            existing = {
                "asset_id": asset_id,
                "source_file_id": source_file_id,
                "relationship_type": relationship_type,
            }
            self.links[source_file_id] = existing
        return existing


class GroupPlanningTests(unittest.TestCase):
    def test_unique_hash_creates_one_group(self):
        group = build_canonical_groups([row("one")])
        self.assertEqual(len(group), 1)
        self.assertEqual(len(group[0].sources), 1)

    def test_matching_hashes_form_one_group(self):
        group = build_canonical_groups([row("one"), row("two")])
        self.assertEqual(len(group), 1)
        self.assertEqual(len(group[0].sources), 2)

    def test_matching_hashes_across_source_folders(self):
        group = build_canonical_groups(
            [row("one", folder="b"), row("two", folder="a")]
        )[0]
        self.assertEqual(group.representative.source_folder_id, "a")

    def test_different_filenames_do_not_split_hash(self):
        groups = build_canonical_groups(
            [row("one", name="first.jpg"), row("two", name="second.jpg")]
        )
        self.assertEqual(len(groups), 1)

    def test_identical_filename_different_hashes_are_separate(self):
        groups = build_canonical_groups(
            [row("one", content_hash=HASH_A), row("two", content_hash=HASH_B)]
        )
        self.assertEqual(len(groups), 2)

    def test_malformed_hash_rejected(self):
        with self.assertRaises(CanonicalizationError):
            build_canonical_groups([row("one", content_hash="bad")])

    def test_non_hashed_rejected(self):
        with self.assertRaises(CanonicalizationError):
            build_canonical_groups([row("one", status="NOT_STARTED")])

    def test_excluded_source_rejected(self):
        with self.assertRaises(CanonicalizationError):
            build_canonical_groups([row("one", decision="SKIP")])

    def test_stable_representative_is_not_filename_based(self):
        group = build_canonical_groups(
            [
                row("one", folder="b", name="aaa.jpg"),
                row("two", folder="a", name="zzz.jpg"),
            ]
        )[0]
        self.assertEqual(group.representative.source_file_id, "two")
        self.assertEqual(group.asset_values()["file_name"], "zzz.jpg")

    def test_deployed_legacy_asset_aliases_match_canonical_values(self):
        values = build_canonical_groups([row("one")])[0].asset_values()
        self.assertEqual(values["checksum_sha256"], values["content_hash"])
        self.assertEqual(values["original_file_name"], values["file_name"])
        self.assertEqual(values["file_size_bytes"], values["size_bytes"])
        self.assertEqual(values["migration_status"], "PENDING")
        self.assertEqual(values["upload_attempts"], 0)


class ExecutionTests(unittest.TestCase):
    def test_one_unique_hash_creates_asset_and_link(self):
        repo = MemoryRepository()
        canonicalize_groups(build_canonical_groups([row("one")]), repo)
        self.assertEqual((len(repo.assets), len(repo.links)), (1, 1))

    def test_duplicate_hash_creates_one_asset_two_links(self):
        repo = MemoryRepository()
        canonicalize_groups(
            build_canonical_groups([row("one"), row("two")]), repo
        )
        self.assertEqual((len(repo.assets), len(repo.links)), (1, 2))
        self.assertEqual(
            CounterLike(x["relationship_type"] for x in repo.links.values()),
            {"ORIGINAL": 1, "DUPLICATE": 1},
        )

    def test_rerun_creates_no_duplicate_assets_or_links(self):
        repo = MemoryRepository()
        groups = build_canonical_groups([row("one"), row("two")])
        canonicalize_groups(groups, repo)
        canonicalize_groups(groups, repo)
        self.assertEqual((repo.asset_inserts, repo.link_inserts), (1, 2))

    def test_interrupted_run_resumes(self):
        repo = MemoryRepository()
        groups = build_canonical_groups([row("one"), row("two")])
        repo.fail_after_links = 1
        canonicalize_groups(groups, repo)
        repo.fail_after_links = None
        canonicalize_groups(groups, repo)
        self.assertEqual((len(repo.assets), len(repo.links)), (1, 2))

    def test_concurrent_equivalent_attempts_reuse_asset(self):
        repo = MemoryRepository()
        groups = build_canonical_groups([row("one")])
        canonicalize_groups(groups, repo)
        canonicalize_groups(groups, repo)
        self.assertEqual(repo.asset_inserts, 1)

    def test_checkpoint_runs_once_per_group(self):
        repo = MemoryRepository()
        checkpoints = []
        groups = build_canonical_groups(
            [row("one", content_hash=HASH_A), row("two", content_hash=HASH_B)]
        )
        canonicalize_groups(groups, repo, checkpoint=checkpoints.append)
        self.assertEqual(len(checkpoints), 2)

    def test_source_identity_and_path_are_not_mutated(self):
        source = row("one")
        original = dict(source)
        repo = MemoryRepository()
        canonicalize_groups(build_canonical_groups([source]), repo)
        self.assertEqual(source, original)

    def test_module_requires_no_drive_or_upload_dependency(self):
        import inspect
        import kdi_media.step9_canonicalization as module

        text = inspect.getsource(module).lower()
        self.assertNotIn("googleapiclient", text)
        self.assertNotIn("get_media", text)
        self.assertNotIn("destination_folder", text)


def CounterLike(values):
    result = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


if __name__ == "__main__":
    unittest.main()
