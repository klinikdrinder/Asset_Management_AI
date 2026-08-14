"""Semantic-indexing worker entry point (natural-language search backend).

Both --dry-run and --execute require an explicit reviewed manifest. Dry-run
is provider-free and read-only even when provider credentials are present.
External execution requires --approved-only and selects only manifest rows whose
approved_for_external_ai flag is true. Local execution requires --local-only and
a separate manifest whose approved_for_local_ai flag is true. Neither permission
implies the other; missing approval always fails closed.

Neither mode ever modifies original Drive media or uploads a complete video
file to a provider (see kdi_media.video_frames / the description provider
interface); all writes are confined to asset_semantic_index and
asset_embeddings.

Per the controlled rollout, do not run this with a large --limit against
production without a prior --dry-run review and explicit approval.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import time
from uuid import UUID

from dotenv import load_dotenv
from supabase import create_client

from kdi_media.google_drive import create_service_account_readonly_drive_service
from kdi_media.providers.base import (
    AIProviderNotConfiguredError,
    get_description_provider,
    get_embedding_provider,
)
from kdi_media.semantic_indexing import (
    DriveContentFetcher,
    SemanticIndexingWorker,
    SupabaseSemanticIndexRepository,
)
from kdi_media.semantic_pilot import LocalPilotManifest, PilotManifest, PilotManifestError
from kdi_media.video_frames import FrameExtractionError, resolve_ffmpeg_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument(
        "--manifest",
        help="Required reviewed pilot manifest. Missing manifests fail closed; "
        "there is no implicit all-assets mode.",
    )
    parser.add_argument(
        "--approved-only",
        action="store_true",
        help="Select only manifest rows explicitly approved_for_external_ai=true. "
        "Required for --execute.",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Use the separate approved_for_local_ai manifest gate and require "
        "both configured providers to be local Ollama.",
    )
    parser.add_argument("--tier", choices=("low-risk", "clinical"))
    parser.add_argument(
        "--confirm-clinical-external-processing",
        action="store_true",
        help="Additional explicit gate required for an approved clinical-tier execute.",
    )
    parser.add_argument(
        "--confirm-clinical-local-processing",
        action="store_true",
        help="Additional explicit privacy gate for a clinical-tier local-only pilot.",
    )
    parser.add_argument(
        "--asset-id",
        action="append",
        default=None,
        help="Restrict to specific, manually-reviewed asset IDs. May be repeated. "
        "Every ID must also be present and approved in --manifest for execution.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Skip discovery/seeding and claim only already-seeded rows "
        "(picks up FAILED_RETRYABLE rows via claim_semantic_index_batch).",
    )
    parser.add_argument(
        "--max-cost",
        type=float,
        default=None,
        help="Stop starting new work once this run's estimated cost (USD) is reached.",
    )
    parser.add_argument(
        "--videos-only",
        action="store_true",
        help="Only consider video assets (dry-run preview only; --execute discovery "
        "does not yet filter by media type, use --asset-id for a scoped execute run).",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.execute and args.dry_run:
        raise SystemExit("--execute and --dry-run are mutually exclusive")
    if not args.execute and not args.dry_run:
        raise SystemExit("Specify --dry-run to preview or --execute to write results")
    if not args.manifest:
        raise SystemExit("--manifest is required; semantic indexing fails closed")
    if args.execute and not args.local_only and not args.approved_only:
        raise SystemExit("External --execute requires --approved-only")
    if args.local_only and args.approved_only:
        raise SystemExit("--local-only and --approved-only are separate approval scopes")
    if args.execute and not args.tier:
        raise SystemExit("--execute requires an explicit --tier")
    if not 1 <= args.limit <= 200:
        raise SystemExit("--limit must be between 1 and 200")
    if not 1 <= args.batch_size <= 50:
        raise SystemExit("--batch-size must be between 1 and 50")
    if args.asset_id:
        for value in args.asset_id:
            UUID(value)
    if args.max_cost is not None and args.max_cost <= 0:
        raise SystemExit("--max-cost must be positive")


def main() -> int:
    args = build_parser().parse_args()
    validate_args(args)
    load_dotenv()

    try:
        args.asset_id = select_manifest_asset_ids(args)
    except PilotManifestError as exc:
        raise SystemExit(f"Pilot manifest rejected: {exc}") from exc
    if args.execute and not args.asset_id:
        raise SystemExit("Pilot manifest contains no explicitly approved assets for this scope")
    if args.limit > len(args.asset_id):
        args.limit = len(args.asset_id)

    client = create_client(
        _required_environment("SUPABASE_URL"),
        _required_environment("SUPABASE_SERVICE_ROLE_KEY"),
    )
    repository = SupabaseSemanticIndexRepository(client)
    # Zero-row probe: fail clearly if the migration has not been applied yet,
    # before touching Drive or any AI provider configuration.
    repository.require_schema()

    if args.dry_run:
        return _run_dry_run(args, repository)
    return _run_execute(args, repository)


def select_manifest_asset_ids(args: argparse.Namespace) -> list[str]:
    """Apply exactly one independent approval scope plus clinical precedence."""
    manifest = (
        LocalPilotManifest.load(args.manifest)
        if args.local_only
        else PilotManifest.load(args.manifest)
    )
    if args.tier and args.tier != manifest.tier:
        raise PilotManifestError("Requested tier does not match manifest tier")
    if args.execute and manifest.tier == "clinical":
        confirmation = (
            args.confirm_clinical_local_processing
            if args.local_only
            else args.confirm_clinical_external_processing
        )
        if not confirmation:
            scope = "local" if args.local_only else "external"
            raise PilotManifestError(
                f"Clinical tier requires explicit {scope} clinical confirmation"
            )
    if args.local_only:
        return manifest.selected_ids(requested_ids=args.asset_id)
    return manifest.selected_ids(
        approved_only=args.approved_only, requested_ids=args.asset_id
    )


def _run_dry_run(args: argparse.Namespace, repository: SupabaseSemanticIndexRepository) -> int:
    # Dry-run is deliberately provider-free: it performs database reads only.
    # This remains true even if valid provider credentials happen to be set.
    candidates = []
    for asset_id in args.asset_id[: args.limit]:
        candidate = repository.fetch_candidate(asset_id)
        if candidate is None:
            raise SystemExit(
                f"Manifest asset is unknown, unsupported, or lacks a VERIFIED destination: {asset_id}"
            )
        candidates.append(candidate)
    print(
        json.dumps(
            {
                "mode": "DRY_RUN",
                "status": "OK",
                "external_ai_calls": 0,
                "database_writes": 0,
                "semantic_inserts": 0,
                "embedding_inserts": 0,
                "candidates_ready": [
                    {
                        "asset_id": candidate.asset_id,
                        "file_name": candidate.file_name,
                        "media_category": candidate.media_category,
                        "verified_destination": True,
                    }
                    for candidate in candidates
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _run_execute(args: argparse.Namespace, repository: SupabaseSemanticIndexRepository) -> int:
    # Validate the complete allowlist and local video dependency before provider
    # construction or any semantic state write.
    candidates = []
    for asset_id in args.asset_id:
        candidate = repository.fetch_candidate(asset_id)
        if candidate is None:
            raise SystemExit(
                f"Manifest asset is unknown, unsupported, or lacks a VERIFIED destination: {asset_id}"
            )
        candidates.append(candidate)
    if any(candidate.media_category == "video" for candidate in candidates):
        try:
            resolve_ffmpeg_paths()
        except FrameExtractionError as exc:
            raise SystemExit(
                f"Video pilot runtime unavailable: {exc}; no semantic rows were written"
            ) from exc

    if getattr(args, "local_only", False):
        preflight = local_ai_memory_preflight()
        if not preflight["ok"]:
            print(json.dumps({
                "mode": "EXECUTE",
                "status": "LOCAL_CAPACITY_PREFLIGHT_FAILED",
                "available_ram_mb": preflight["available_mb"],
                "required_ram_mb": preflight["required_mb"],
                "database_writes": 0,
                "message": "Available RAM is below the configured local AI minimum",
            }, sort_keys=True))
            return 0

    try:
        description_provider = get_description_provider()
        embedding_provider = get_embedding_provider()
    except AIProviderNotConfiguredError as exc:
        # Deliberately checked before any discovery/seed/claim call: claiming
        # rows we cannot complete would leave them stuck in PROCESSING.
        print(
            json.dumps(
                {
                    "mode": "EXECUTE",
                    "status": "PROVIDER_NOT_CONFIGURED",
                    "message": str(exc),
                    "database_writes": 0,
                },
                sort_keys=True,
            )
        )
        return 0

    if getattr(args, "local_only", False) and (
        description_provider.provider_name != "ollama"
        or embedding_provider.provider_name != "ollama"
    ):
        raise SystemExit("--local-only requires Ollama description and embedding providers")

    repository.configure_index_identity(description_provider, embedding_provider)

    if not args.retry_failed:
        # Bulk discovery is intentionally never used to select assets for an
        # external AI call while no clinical/patient-identifiable
        # classification exists - only the reviewed --asset-id allowlist
        # (already validated above) is seeded/claimed. seed_pending() is a
        # no-op for assets already seeded/claimed/indexed.
        ready_asset_ids = repository.prepare_explicit_assets(args.asset_id)
        repository.seed_pending(ready_asset_ids)

    service = create_service_account_readonly_drive_service()
    worker = SemanticIndexingWorker(
        repository,
        DriveContentFetcher(service),
        description_provider,
        embedding_provider,
        max_cost_usd=args.max_cost,
    )

    claim_owner = f"semantic-indexing-{os.getpid()}-{int(time.time())}"
    processed = 0
    indexed = 0
    failed = 0
    remaining = args.limit
    while remaining > 0:
        batch_limit = min(args.batch_size, remaining)
        claims = repository.claim_batch(
            claim_owner, batch_limit, 900, asset_ids=args.asset_id
        )
        if not claims:
            break
        for claim in claims:
            result = worker.process_one(str(claim["asset_id"]), claim_owner)
            processed += 1
            if result is not None:
                indexed += 1
            else:
                failed += 1
        remaining -= len(claims)
        if worker.max_cost_usd is not None and worker.total_cost_usd >= worker.max_cost_usd:
            break

    print(
        json.dumps(
            {
                "mode": "EXECUTE",
                "status": "OK",
                "claim_owner": claim_owner,
                "description_provider": description_provider.provider_name,
                "description_model": description_provider.model_name,
                "embedding_provider": embedding_provider.provider_name,
                "embedding_model": embedding_provider.model_name,
                "embedding_dimensions": embedding_provider.embedding_dimensions,
                "processed": processed,
                "indexed": indexed,
                "failed": failed,
                "total_cost_usd": round(worker.total_cost_usd, 6),
            },
            sort_keys=True,
        )
    )
    return 0


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required configuration: {name}")
    return value


def local_ai_memory_preflight(
    *, available_mb: int | None = None, required_mb: int | None = None
) -> dict[str, int | bool]:
    """Check host capacity before provider construction or semantic writes."""
    if required_mb is None:
        raw = os.environ.get("LOCAL_AI_MIN_AVAILABLE_RAM_MB", "3072").strip()
        try:
            required_mb = int(raw)
        except ValueError as exc:
            raise SystemExit("LOCAL_AI_MIN_AVAILABLE_RAM_MB must be an integer") from exc
    if required_mb <= 0:
        raise SystemExit("LOCAL_AI_MIN_AVAILABLE_RAM_MB must be positive")
    if available_mb is None:
        available_mb = _available_memory_mb()
    return {
        "ok": available_mb >= required_mb,
        "available_mb": available_mb,
        "required_mb": required_mb,
    }


def _available_memory_mb() -> int:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise SystemExit("Unable to read available system RAM")
        return int(status.available_physical // (1024 * 1024))
    try:
        with open("/proc/meminfo", encoding="ascii") as memory_info:
            for line in memory_info:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError as exc:
        raise SystemExit("Unable to read available system RAM") from exc
    raise SystemExit("Unable to read available system RAM")


if __name__ == "__main__":
    raise SystemExit(main())
