"""Dry-run or import explicitly human-reviewed semantic metadata.

No media is read and no description/vision provider is constructed. Execute
uses only the configured local Ollama embedding provider and existing semantic
claim/persistence architecture.
"""

from __future__ import annotations

import argparse
import json
import os
import time

from dotenv import load_dotenv
from supabase import create_client

from kdi_media.manual_semantic_pilot import (
    ManualPilotValidationError,
    build_manual_index_result,
    compute_manual_fingerprint,
    dry_run_report,
    load_and_review_manifest,
)
from kdi_media.providers.base import get_embedding_provider
from kdi_media.semantic_indexing import (
    FailureInfo,
    IndexingStatus,
    SupabaseSemanticIndexRepository,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    result.add_argument("--manifest", required=True)
    result.add_argument("--confirm-manual-import", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.execute and not args.confirm_manual_import:
        raise SystemExit("--execute requires --confirm-manual-import")
    load_dotenv()
    reviews = load_and_review_manifest(args.manifest)
    client = create_client(_required("SUPABASE_URL"), _required("SUPABASE_SERVICE_ROLE_KEY"))
    repository = SupabaseSemanticIndexRepository(client)
    repository.require_schema()
    candidates = {
        review.asset_id: repository.fetch_candidate(review.asset_id)
        for review in reviews if review.asset_id
    }
    semantic_rows = client.table("asset_semantic_index").select("asset_id").execute().data or []
    embedding_rows = (
        client.table("asset_embeddings").select("asset_id")
        .eq("embedding_provider", "ollama")
        .eq("embedding_model", "qwen3-embedding:0.6b")
        .eq("embedding_version", "v1")
        .execute().data or []
    )
    report = dry_run_report(
        reviews,
        candidates,
        existing_semantic_ids={str(row["asset_id"]) for row in semantic_rows},
        existing_embedding_ids={str(row["asset_id"]) for row in embedding_rows},
    )
    if args.dry_run:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if report["entries_invalid"] or report["assets_missing_or_noncanonical"]:
        raise SystemExit("Manual pilot rejected: every entry must be reviewed and canonical")
    if not 1 <= len(reviews) <= 20:
        raise SystemExit("Manual benchmark execute is limited to 1-20 assets")

    embedding_provider = get_embedding_provider()
    if (
        embedding_provider.provider_name != "ollama"
        or embedding_provider.model_name != "qwen3-embedding:0.6b"
        or embedding_provider.embedding_dimensions != 1024
    ):
        raise SystemExit("Manual pilot requires local qwen3-embedding:0.6b at 1024 dimensions")

    entries = {review.asset_id: review.entry for review in reviews if review.entry}
    ready: list[str] = []
    skipped: list[str] = []
    for asset_id, entry in entries.items():
        candidate = candidates[asset_id]
        expected = compute_manual_fingerprint(entry, candidate, embedding_provider)
        response = (
            client.table("asset_semantic_index")
            .select("indexing_status,source_fingerprint")
            .eq("asset_id", asset_id).limit(1).execute()
        )
        rows = response.data or []
        if rows and rows[0].get("indexing_status") == "INDEXED" and rows[0].get("source_fingerprint") == expected:
            skipped.append(asset_id)
            continue
        if rows and rows[0].get("indexing_status") == "INDEXED":
            repository.requeue_changed([asset_id])
        ready.append(asset_id)

    repository.seed_pending(ready)
    owner = f"manual-semantic-{os.getpid()}-{int(time.time())}"
    claims = repository.claim_batch(owner, len(ready), 900, asset_ids=ready) if ready else []
    claimed = {str(row["asset_id"]) for row in claims}
    if claimed != set(ready):
        raise SystemExit("Manual pilot claim did not exactly match the reviewed allowlist")
    indexed = 0
    for asset_id in ready:
        try:
            result = build_manual_index_result(entries[asset_id], candidates[asset_id], embedding_provider)
            if not repository.complete(asset_id, owner, result):
                raise ManualPilotValidationError("Semantic claim was lost before persistence")
            indexed += 1
        except Exception as exc:
            repository.fail(asset_id, owner, FailureInfo(
                IndexingStatus.FAILED_RETRYABLE,
                "MANUAL_EMBEDDING_FAILED",
                str(exc)[:300],
                True,
            ))
            raise
    description_provenance = sorted({
        (entry.description_provider, entry.description_model, entry.description_version)
        for entry in entries.values()
    })
    print(json.dumps({
        "mode": "EXECUTE",
        "description_provenance": [
            {"provider": provider, "model": model, "version": version}
            for provider, model, version in description_provenance
        ],
        "embedding_provider": embedding_provider.provider_name,
        "embedding_model": embedding_provider.model_name,
        "embedding_dimensions": embedding_provider.embedding_dimensions,
        "indexed": indexed,
        "unchanged_skipped": len(skipped),
        "vision_calls": 0,
    }, sort_keys=True))
    return 0


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required configuration: {name}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
