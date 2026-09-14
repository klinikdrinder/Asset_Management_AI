"""Read-only coverage report: resolve the existing asset_search_concepts_v2 codes
through OntologyResolver and tabulate resolution by concept_type.

Writes nothing to the database. Emits JSON to stdout and to
reports/ai-search-v3/ontology_resolution_pilot_report.json.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import dotenv_values
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kdi_media.ontology_resolver import OntologyResolver  # noqa: E402


def env() -> dict:
    e: dict = {}
    for f in (ROOT / ".env", ROOT / ".env.local", ROOT / "dashboard" / ".env.local"):
        if f.exists():
            e.update({k: v for k, v in dotenv_values(f).items() if v})
    e.update(os.environ)
    return e


def main() -> int:
    e = env()
    url = e.get("SUPABASE_URL") or e.get("NEXT_PUBLIC_SUPABASE_URL")
    key = e.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")
    db = create_client(url, key)
    resolver = OntologyResolver.from_supabase(db)

    rows = db.table("asset_search_concepts_v2").select(
        "concept_type,canonical_code").execute().data or []

    by_type: dict[str, dict] = defaultdict(lambda: {
        "rows": 0, "resolved": 0, "exact": 0, "alias": 0, "normalized": 0,
        "unresolved": 0, "no_ontology_domain": 0,
        "unresolved_codes": set(), "resolved_examples": {},
    })
    for r in rows:
        ct, code = r["concept_type"], r["canonical_code"]
        res = resolver.resolve(code, ct)
        bucket = by_type[ct]
        bucket["rows"] += 1
        bucket[res.match_method] += 1
        if res.resolved:
            bucket["resolved"] += 1
            bucket["resolved_examples"].setdefault(code, res.resolved_code)
        else:
            bucket["unresolved_codes"].add(code)

    total = {"rows": len(rows), "resolved": sum(b["resolved"] for b in by_type.values())}
    out = {"total": total, "by_concept_type": {}}
    for ct, b in sorted(by_type.items(), key=lambda kv: -kv[1]["rows"]):
        out["by_concept_type"][ct] = {
            "rows": b["rows"], "resolved": b["resolved"],
            "resolved_pct": round(100 * b["resolved"] / b["rows"], 1) if b["rows"] else 0,
            "exact": b["exact"], "alias": b["alias"], "normalized": b["normalized"],
            "unresolved": b["unresolved"], "no_ontology_domain": b["no_ontology_domain"],
            "unresolved_codes": sorted(b["unresolved_codes"]),
        }
    out_dir = ROOT / "reports" / "ai-search-v3"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ontology_resolution_pilot_report.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
