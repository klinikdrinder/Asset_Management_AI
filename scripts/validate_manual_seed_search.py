"""Run the manual seed query set through local embeddings + the live hybrid RPC.

Creates an ephemeral session for the repository's already-provisioned restricted
reader. Tokens and embedding vectors are never printed or persisted.
"""

from __future__ import annotations

import base64
import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values, load_dotenv
from supabase import create_client

from kdi_media.providers.base import get_embedding_provider


PROJECT = "wcqqjpndlwsvatjuqnol"
READER_EMAIL = "kdimediaautomation@gmail.com"
LEGACY_QUERIES = (
    "show me videos inside the clinic",
    "empty clinic room",
    "clinic corridor",
    "clinic seating area",
    "clinic wall",
    "interior of the clinic",
    "show me a hallway inside the clinic",
    "where patients can sit inside the clinic",
    "an unoccupied room in the clinic",
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--benchmark", type=Path)
    result.add_argument("--fallback", action="store_true", help="Run without query embeddings")
    return result


def main() -> int:
    args = parser().parse_args()
    load_dotenv()
    dashboard = dotenv_values(Path("dashboard") / ".env.local")
    url = str(
        dashboard.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL") or ""
    ).rstrip("/")
    anon_key = str(dashboard.get("NEXT_PUBLIC_SUPABASE_ANON_KEY") or "")
    if url != f"https://{PROJECT}.supabase.co" or not anon_key:
        raise SystemExit("Restricted reader public configuration is unavailable")

    admin = create_client(_required("SUPABASE_URL"), _required("SUPABASE_SERVICE_ROLE_KEY"))
    link = admin.auth.admin.generate_link({"type": "magiclink", "email": READER_EMAIL})
    reader = create_client(url, anon_key)
    auth = reader.auth.verify_otp({
        "token_hash": link.properties.hashed_token,
        "type": "email",
    })
    if not auth.session:
        raise SystemExit("Restricted reader session was not created")
    claims = _claims(auth.session.access_token)
    metadata = claims.get("app_metadata") or {}
    if (
        claims.get("aud") != "authenticated"
        or metadata.get("kdi_media_reader") != "true"
        or metadata.get("kdi_media_access") is not True
    ):
        raise SystemExit("Restricted reader claims are invalid")

    embedding = get_embedding_provider()
    if (
        embedding.provider_name != "ollama"
        or embedding.model_name != "qwen3-embedding:0.6b"
        or embedding.embedding_dimensions != 1024
    ):
        raise SystemExit("Search validation requires local 1024-dimensional Ollama embeddings")

    if args.benchmark:
        benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
        query_rows = benchmark.get("queries", [])
        if len(query_rows) != 20 or any(row.get("status") != "ready" for row in query_rows):
            raise SystemExit("Benchmark must contain exactly 20 ready queries")
    else:
        query_rows = [{"number": number, "type": "legacy", "query": query, "expected_asset_ids": []} for number, query in enumerate(LEGACY_QUERIES, 1)]

    results: list[dict[str, Any]] = []
    for benchmark_row in query_rows:
        query = str(benchmark_row["query"])
        vector = None if args.fallback else embedding.embed_text(query)[0]
        rows = reader.rpc("hybrid_search_assets", {
            "search_query": query,
            "query_embedding": vector,
            "query_embedding_provider": embedding.provider_name,
            "query_embedding_model": embedding.model_name,
            "query_embedding_version": embedding.version,
            "filter_category": None,
            "filter_extension": None,
            "result_limit": 3,
            "result_offset": 0,
        }).execute().data or []
        ids = [str(row["asset_id"]) for row in rows]
        names: dict[str, str] = {}
        if ids:
            assets = reader.table("assets").select("id,file_name").in_("id", ids).execute().data or []
            names = {str(asset["id"]): str(asset["file_name"]) for asset in assets}
        expected = {str(value) for value in benchmark_row.get("expected_asset_ids", [])}
        expected_rank = next((rank for rank, row in enumerate(rows, 1) if str(row["asset_id"]) in expected), None)
        results.append({
            "number": benchmark_row["number"],
            "type": benchmark_row["type"],
            "query": query,
            "expected_asset_ids": sorted(expected),
            "expected_rank": expected_rank,
            "pass": expected_rank is not None if expected else None,
            "results": [
                {
                    "rank": rank,
                    "asset_id": str(row["asset_id"]),
                    "filename": names.get(str(row["asset_id"]), "[permission-filtered]"),
                    "hybrid_score": float(row.get("match_score") or 0),
                    "vector_score": float(row.get("semantic_score") or 0),
                    "text_score": float(row.get("text_score") or 0),
                    "structured_score": float(row.get("structured_score") or 0),
                    "filename_score": float(row.get("filename_score") or 0),
                }
                for rank, row in enumerate(rows, 1)
            ],
        })
    scored = [row for row in results if row["pass"] is not None]
    paraphrase = [row for row in scored if row["type"] in {"semantic_paraphrase", "natural_conversational"}]
    print(json.dumps({
        "provider": embedding.provider_name,
        "model": embedding.model_name,
        "dimensions": embedding.embedding_dimensions,
        "embedding_available": not args.fallback,
        "permission_filtered_rpc": True,
        "summary": {
            "passed": sum(row["pass"] is True for row in scored),
            "total": len(scored),
            "paraphrase_passed": sum(row["pass"] is True for row in paraphrase),
            "paraphrase_total": len(paraphrase),
        },
        "queries": results,
    }, indent=2))
    return 0


def _claims(token: str) -> dict[str, Any]:
    part = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required configuration: {name}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
