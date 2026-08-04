from __future__ import annotations

import hashlib
import unittest

from kdi_media.step9_hashing import (
    FailureInfo,
    HashResult,
    HashStatus,
    PartialDownloadError,
    PermanentHashingError,
    RetryableHashingError,
    SourceAccessDeniedError,
    SourceChangedError,
    SourceNotFoundError,
    SourceSnapshot,
    SourceTrashedError,
    Step9HashWorker,
    compare_snapshots,
    hash_chunks,
    hash_drive_file,
    iter_drive_content,
)


def snapshot(**changes: object) -> SourceSnapshot:
    values = {
        "file_id": "file-1",
        "mime_type": "video/mp4",
        "size_bytes": 6,
        "modified_time": "2026-07-30T00:00:00Z",
        "version": "7",
        "revision": None,
        "trashed": False,
        "can_download": True,
    }
    values.update(changes)
    return SourceSnapshot(**values)


class FakeRepository:
    def __init__(self) -> None:
        self.state = HashStatus.NOT_STARTED
        self.owner: str | None = None
        self.expired = False
        self.completed: HashResult | None = None
        self.failure: FailureInfo | None = None
        self.attempt_count = 0
        self.renewals = 0

    def claim(self, source_file_id: str, owner: str, lease: int):
        del source_file_id, lease
        if self.state == HashStatus.HASHED:
            return None
        if self.state == HashStatus.HASHING and not self.expired:
            return None
        self.state = HashStatus.HASHING
        self.owner = owner
        self.expired = False
        self.attempt_count += 1
        return {"hash_status": "HASHING"}

    def record_retry_attempt(self, source_file_id: str, owner: str):
        del source_file_id
        if self.state != HashStatus.HASHING or owner != self.owner:
            return False
        self.attempt_count += 1
        return True

    def renew(self, source_file_id: str, owner: str, lease: int):
        del source_file_id, lease
        if self.state != HashStatus.HASHING or owner != self.owner:
            return False
        self.renewals += 1
        return True

    def complete(self, source_file_id: str, owner: str, result: HashResult):
        del source_file_id
        if self.state != HashStatus.HASHING or owner != self.owner:
            return False
        self.state = HashStatus.HASHED
        self.completed = result
        self.owner = None
        return True

    def fail(self, source_file_id: str, owner: str, failure: FailureInfo):
        del source_file_id
        if self.state != HashStatus.HASHING or owner != self.owner:
            return False
        self.state = failure.status
        self.failure = failure
        self.owner = None
        return True


class HashChunkTests(unittest.TestCase):
    def test_successful_small_file(self) -> None:
        digest, count = hash_chunks([b"abcdef"], expected_bytes=6)
        self.assertEqual(digest, hashlib.sha256(b"abcdef").hexdigest())
        self.assertEqual(count, 6)

    def test_multi_chunk_file(self) -> None:
        digest, count = hash_chunks([b"ab", b"cd", b"ef"], expected_bytes=6)
        self.assertEqual(digest, hashlib.sha256(b"abcdef").hexdigest())
        self.assertEqual(count, 6)

    def test_empty_file(self) -> None:
        digest, count = hash_chunks([], expected_bytes=0)
        self.assertEqual(digest, hashlib.sha256(b"").hexdigest())
        self.assertEqual(count, 0)

    def test_partial_stream_rejected(self) -> None:
        with self.assertRaises(PartialDownloadError):
            hash_chunks([b"abc"], expected_bytes=6)

    def test_byte_count_mismatch_rejected(self) -> None:
        with self.assertRaises(PartialDownloadError):
            hash_chunks([b"abcdefg"], expected_bytes=6)

    def test_identical_streams_have_same_hash(self) -> None:
        one = hash_chunks([b"a", b"bc"], expected_bytes=3)[0]
        two = hash_chunks([b"abc"], expected_bytes=3)[0]
        self.assertEqual(one, two)

    def test_different_streams_have_different_hashes(self) -> None:
        self.assertNotEqual(
            hash_chunks([b"abc"], expected_bytes=3)[0],
            hash_chunks([b"abd"], expected_bytes=3)[0],
        )

    def test_stream_is_consumed_incrementally(self) -> None:
        largest = 0

        def chunks():
            nonlocal largest
            for _ in range(128):
                chunk = b"x" * 1024
                largest = max(largest, len(chunk))
                yield chunk

        _, count = hash_chunks(chunks(), expected_bytes=128 * 1024)
        self.assertEqual(count, 128 * 1024)
        self.assertEqual(largest, 1024)

    def test_drive_downloader_yields_and_releases_each_chunk(self) -> None:
        class Files:
            def get_media(self, *, fileId):
                self.file_id = fileId
                return object()

        class Service:
            def __init__(self):
                self.api = Files()

            def files(self):
                return self.api

        class Downloader:
            def __init__(self, sink, request, *, chunksize):
                del request
                self.sink = sink
                self.chunksize = chunksize
                self.parts = iter((b"abc", b"def"))

            def next_chunk(self, *, num_retries):
                self.assert_zero = num_retries
                try:
                    self.sink.write(next(self.parts))
                    return None, False
                except StopIteration:
                    return None, True

        service = Service()
        chunks = list(
            iter_drive_content(
                service,
                "file-1",
                chunk_size=256 * 1024,
                downloader_factory=Downloader,
            )
        )
        self.assertEqual(chunks, [b"abc", b"def"])
        self.assertEqual(service.api.file_id, "file-1")


class SourceChangeTests(unittest.TestCase):
    def test_source_changed_before_hashing(self) -> None:
        with self.assertRaises(SourceChangedError):
            compare_snapshots(snapshot(), snapshot(size_bytes=9))

    def test_equivalent_utc_timestamp_formats_are_unchanged(self) -> None:
        compare_snapshots(
            snapshot(modified_time="2026-07-30T00:00:00+00:00"),
            snapshot(modified_time="2026-07-30T00:00:00Z"),
        )

    def test_trashed_file(self) -> None:
        with self.assertRaises(SourceTrashedError):
            compare_snapshots(snapshot(), snapshot(trashed=True))

    def test_access_denied_metadata(self) -> None:
        with self.assertRaises(SourceAccessDeniedError):
            compare_snapshots(snapshot(), snapshot(can_download=False))

    def test_source_changed_during_hashing(self) -> None:
        readings = iter([snapshot(), snapshot(version="8")])
        with self.assertRaises(SourceChangedError):
            hash_drive_file(
                object(),
                snapshot(),
                lambda _service, _file_id: next(readings),
                content_reader=lambda *_args, **_kwargs: [b"abcdef"],
            )


class WorkerTests(unittest.TestCase):
    def worker(self, repo: FakeRepository, reader, **kwargs):
        return Step9HashWorker(
            repo,
            object(),
            reader,
            retry_delays=kwargs.pop("retry_delays", (0.0, 0.0)),
            jitter=lambda: 0.0,
            sleeper=kwargs.pop("sleeper", lambda _delay: None),
            **kwargs,
        )

    def test_retryable_failure_then_success(self) -> None:
        repo = FakeRepository()
        calls = 0

        def content(*_args, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RetryableHashingError("temporary")
            return [b"abcdef"]

        result = self.worker(repo, lambda *_: snapshot()).process(
            "row-1", "worker-1", snapshot(), content_reader=content
        )
        self.assertIsNotNone(result)
        self.assertEqual(calls, 2)
        self.assertEqual(repo.attempt_count, 2)

    def test_permanent_failure_not_retried(self) -> None:
        repo = FakeRepository()
        calls = 0

        def reader(*_args):
            nonlocal calls
            calls += 1
            raise PermanentHashingError("permanent")

        self.worker(repo, reader).process("row-1", "worker-1", snapshot())
        self.assertEqual(calls, 1)
        self.assertEqual(repo.state, HashStatus.FAILED_PERMANENT)

    def test_missing_file(self) -> None:
        repo = FakeRepository()
        worker = self.worker(
            repo, lambda *_: (_ for _ in ()).throw(SourceNotFoundError("missing"))
        )
        worker.process("row-1", "worker-1", snapshot())
        self.assertEqual(repo.state, HashStatus.SOURCE_NOT_FOUND)

    def test_access_denied(self) -> None:
        repo = FakeRepository()
        worker = self.worker(
            repo,
            lambda *_: (_ for _ in ()).throw(
                SourceAccessDeniedError("denied")
            ),
        )
        worker.process("row-1", "worker-1", snapshot())
        self.assertEqual(repo.state, HashStatus.SOURCE_ACCESS_DENIED)

    def test_retry_exhaustion(self) -> None:
        repo = FakeRepository()
        worker = self.worker(
            repo,
            lambda *_: (_ for _ in ()).throw(
                RetryableHashingError("temporary")
            ),
            retry_delays=(0.0,),
        )
        worker.process("row-1", "worker-1", snapshot())
        self.assertEqual(repo.state, HashStatus.FAILED_RETRYABLE)

    def test_completed_unchanged_file_skipped(self) -> None:
        repo = FakeRepository()
        repo.state = HashStatus.HASHED
        result = self.worker(repo, lambda *_: snapshot()).process(
            "row-1", "worker-1", snapshot()
        )
        self.assertIsNone(result)

    def test_active_claim_prevents_duplicate_work(self) -> None:
        repo = FakeRepository()
        repo.state = HashStatus.HASHING
        repo.owner = "worker-a"
        result = self.worker(repo, lambda *_: snapshot()).process(
            "row-1", "worker-b", snapshot()
        )
        self.assertIsNone(result)
        self.assertEqual(repo.owner, "worker-a")

    def test_expired_claim_recovery(self) -> None:
        repo = FakeRepository()
        repo.state = HashStatus.HASHING
        repo.owner = "dead-worker"
        repo.expired = True
        result = self.worker(repo, lambda *_: snapshot()).process(
            "row-1",
            "worker-b",
            snapshot(),
            content_reader=lambda *_args, **_kwargs: [b"abcdef"],
        )
        self.assertIsNotNone(result)
        self.assertEqual(repo.state, HashStatus.HASHED)

    def test_long_stream_renews_lease(self) -> None:
        repo = FakeRepository()
        ticks = iter((0.0, 61.0, 122.0))
        worker = self.worker(
            repo,
            lambda *_: snapshot(),
            monotonic=lambda: next(ticks),
            lease_renewal_interval=60.0,
        )
        result = worker.process(
            "row-1",
            "worker-b",
            snapshot(),
            content_reader=lambda *_args, **_kwargs: [b"abc", b"def"],
        )
        self.assertIsNotNone(result)
        self.assertEqual(repo.renewals, 2)


if __name__ == "__main__":
    unittest.main()
