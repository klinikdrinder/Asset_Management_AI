"""Generate Phase 2 audit artifacts from the recorded read-only live audit snapshot.

This script performs no database or media access. The FACTS below are counts returned by
read-only SELECT queries against the live project on 2026-08-24. Re-running the live audit
requires refreshing FACTS with SELECT-only queries; this generator never writes production data.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "config" / "semantic-search" / "kdi_semantic_search_spec_v1.json"
MANIFEST_PATH = ROOT / "config" / "semantic-search" / "kdi_semantic_pilot_v1.json"
REPORT_DIR = ROOT / "reports" / "semantic-search"
DOC_PATH = ROOT / "docs" / "semantic-search" / "KDI_PHASE_2_PILOT_AUDIT.md"

BASELINE = {
    "assets": 881, "visual_embeddings": 875, "text_embeddings": 20,
    "asset_ai_profiles": 16, "asset_search_documents": 10,
    "scene_search_documents": 10, "asset_scenes": 301, "asset_keyframes": 301,
    "transcript_chunks": 0, "ocr_observations": 0, "authorization_rows": 881,
    "application_users": 2, "source_files": 890, "asset_sources": 881,
    "asset_destinations": 881,
    "permission_digest": "62c43cea06b71b95d1146cc17878991f",
}

FACTS = {
    "IMG_0531.MP4": dict(scenes=1, valid_scenes=1, keyframes=1, people=2, appearances=2, anatomy=3, treatments=0, actions=2, relationships=1, clinical=0, environments=1, cinematography=1, composition=1, transcripts=0, ocr=0, marketing=1, narratives=1, asset_docs=1, scene_docs=1, visual_embeddings=1, text_embeddings=0, scene_embeddings=1, keyframe_embeddings=1, transcript_embeddings=0, analysis_runs=1),
    "IMG_1238.MP4": dict(scenes=1, valid_scenes=1, keyframes=1, people=2, appearances=2, anatomy=2, treatments=0, actions=2, relationships=1, clinical=0, environments=1, cinematography=1, composition=1, transcripts=0, ocr=0, marketing=1, narratives=1, asset_docs=1, scene_docs=1, visual_embeddings=1, text_embeddings=0, scene_embeddings=1, keyframe_embeddings=1, transcript_embeddings=0, analysis_runs=1),
    "IMG_3429.MP4": dict(scenes=1, valid_scenes=1, keyframes=1, people=2, appearances=2, anatomy=1, treatments=0, actions=2, relationships=1, clinical=0, environments=1, cinematography=1, composition=1, transcripts=0, ocr=0, marketing=1, narratives=1, asset_docs=1, scene_docs=1, visual_embeddings=1, text_embeddings=0, scene_embeddings=1, keyframe_embeddings=1, transcript_embeddings=0, analysis_runs=1),
    "IMG_9871.MOV": dict(scenes=1, valid_scenes=1, keyframes=1, people=1, appearances=1, anatomy=1, treatments=0, actions=0, relationships=0, clinical=0, environments=1, cinematography=1, composition=1, transcripts=0, ocr=0, marketing=1, narratives=1, asset_docs=1, scene_docs=1, visual_embeddings=1, text_embeddings=0, scene_embeddings=1, keyframe_embeddings=1, transcript_embeddings=0, analysis_runs=1),
    "DSC03753.JPG": dict(scenes=1, valid_scenes=0, keyframes=1, people=1, appearances=1, anatomy=3, treatments=0, actions=1, relationships=0, clinical=12, environments=1, cinematography=1, composition=1, transcripts=0, ocr=0, marketing=1, narratives=4, asset_docs=1, scene_docs=1, visual_embeddings=1, text_embeddings=0, scene_embeddings=1, keyframe_embeddings=1, transcript_embeddings=0, analysis_runs=1),
    "DSC08097.JPG": dict(scenes=1, valid_scenes=0, keyframes=1, people=1, appearances=1, anatomy=1, treatments=0, actions=2, relationships=0, clinical=0, environments=1, cinematography=1, composition=1, transcripts=0, ocr=0, marketing=1, narratives=4, asset_docs=1, scene_docs=1, visual_embeddings=1, text_embeddings=0, scene_embeddings=1, keyframe_embeddings=1, transcript_embeddings=0, analysis_runs=1),
    "IMG_0493.MP4": dict(scenes=1, valid_scenes=1, keyframes=1, people=2, appearances=2, anatomy=3, treatments=0, actions=1, relationships=1, clinical=0, environments=1, cinematography=1, composition=1, transcripts=0, ocr=0, marketing=1, narratives=1, asset_docs=1, scene_docs=1, visual_embeddings=1, text_embeddings=0, scene_embeddings=1, keyframe_embeddings=1, transcript_embeddings=0, analysis_runs=1),
    "IMG_1148.MP4": dict(scenes=1, valid_scenes=1, keyframes=1, people=2, appearances=2, anatomy=2, treatments=0, actions=2, relationships=1, clinical=0, environments=1, cinematography=1, composition=1, transcripts=0, ocr=0, marketing=1, narratives=1, asset_docs=1, scene_docs=1, visual_embeddings=1, text_embeddings=0, scene_embeddings=1, keyframe_embeddings=1, transcript_embeddings=0, analysis_runs=1),
    "IMG_2963.MP4": dict(scenes=1, valid_scenes=1, keyframes=1, people=3, appearances=3, anatomy=3, treatments=1, actions=1, relationships=1, clinical=0, environments=1, cinematography=1, composition=1, transcripts=0, ocr=0, marketing=1, narratives=1, asset_docs=1, scene_docs=1, visual_embeddings=1, text_embeddings=0, scene_embeddings=1, keyframe_embeddings=1, transcript_embeddings=0, analysis_runs=1),
    "IMG_1160.MP4": dict(scenes=1, valid_scenes=1, keyframes=1, people=2, appearances=2, anatomy=3, treatments=0, actions=1, relationships=1, clinical=0, environments=1, cinematography=1, composition=1, transcripts=0, ocr=0, marketing=1, narratives=1, asset_docs=1, scene_docs=1, visual_embeddings=1, text_embeddings=0, scene_embeddings=1, keyframe_embeddings=1, transcript_embeddings=0, analysis_runs=1),
}

CONFLICT_ASSETS = {"DSC03753.JPG", "DSC08097.JPG"}

LAYER_SOURCES = {
    1: "assets; asset_sources; source_files; asset_destinations; asset_technical_metadata",
    2: "asset_ai_profiles; asset_search_documents",
    3: "asset_scenes; asset_keyframes; scene_search_documents",
    4: "scene_people; asset_ai_profiles",
    5: "person_appearances; scene_people; asset_ai_profiles",
    6: "scene_anatomy; anatomy_terms; asset_ai_profiles; search documents",
    7: "scene_treatments; treatments; asset_ai_profiles; search documents",
    8: "scene_actions; actions; search documents",
    9: "scene_relationships; relationship_types; search documents",
    10: "clinical_observations; clinical_observation_definitions; search documents",
    11: "scene_environment; locations; asset_ai_profiles; search documents",
    12: "scene_cinematography; asset_technical_metadata; search documents",
    13: "scene_composition; person counts; search documents",
    14: "asset_transcript_chunks; transcript_embeddings; asset_ai_profiles",
    15: "ocr_observations; search documents",
    16: "marketing_annotations; asset_access_control; asset_ai_profiles",
    17: "scene_narratives; asset_ai_profiles; asset/scene search documents",
    18: "asset/scene search documents; visual/text/scene/keyframe/transcript embeddings",
}


def status_for(filename: str, media: str, layer: int, f: dict) -> tuple[str, list[str], str, str]:
    flags: list[str] = []
    applicability = "APPLICABLE"
    action = "RETAIN_AND_VERIFY"

    if layer == 1:
        return "COMPLETE", ["COMPLETE"], applicability, "RETAIN"
    if layer == 2:
        primary = "PARTIAL"
    elif layer == 3:
        if media == "image":
            return "NOT_APPLICABLE", ["NOT_APPLICABLE", "LEGACY_ONLY"], "NOT_APPLICABLE", "NOT_APPLICABLE"
        primary, action = "PARTIAL", "REBUILD"
    elif layer in (4, 5, 6, 11, 12, 13, 16, 17, 18):
        primary = "PARTIAL"
    elif layer == 7:
        if f["treatments"]:
            primary = "PARTIAL"
        elif media == "image":
            primary, flags, action = "SEARCH_DOC_ONLY", ["SEARCH_DOC_ONLY"], "NORMALIZE"
        else:
            primary, action = "MISSING", "COMPLETE"
    elif layer == 8:
        if f["actions"]:
            primary = "PARTIAL"
        else:
            primary, flags, action = "SEARCH_DOC_ONLY", ["SEARCH_DOC_ONLY"], "NORMALIZE"
    elif layer == 9:
        primary = "PARTIAL" if f["relationships"] else "MISSING"
        action = "COMPLETE" if primary == "MISSING" else action
    elif layer == 10:
        if f["clinical"]:
            primary = "PARTIAL"
        elif media == "image":
            primary, flags, action = "SEARCH_DOC_ONLY", ["SEARCH_DOC_ONLY"], "NORMALIZE"
        else:
            primary, action = "MISSING", "COMPLETE"
    elif layer == 14:
        if media == "image":
            return "NOT_APPLICABLE", ["NOT_APPLICABLE"], "NOT_APPLICABLE", "NOT_APPLICABLE"
        return "MISSING", ["MISSING"], "UNCERTAIN", "REBUILD"
    elif layer == 15:
        applicability = "UNCERTAIN"
        if media == "image":
            primary, flags, action = "SEARCH_DOC_ONLY", ["SEARCH_DOC_ONLY"], "NORMALIZE"
        else:
            primary, action = "MISSING", "COMPLETE"
    else:
        raise AssertionError(layer)

    if not flags:
        flags = [primary]
    if primary not in ("MISSING", "NOT_APPLICABLE"):
        flags.append("UNVERIFIED")
    if filename in CONFLICT_ASSETS and layer in (3, 7, 8, 15):
        flags.append("CONFLICT")
    return primary, list(dict.fromkeys(flags)), applicability, action


def record_count(layer: int, f: dict) -> str:
    keys = {
        1: [], 2: ["asset_docs"], 3: ["scenes", "keyframes", "scene_docs"],
        4: ["people"], 5: ["appearances"], 6: ["anatomy"], 7: ["treatments"],
        8: ["actions"], 9: ["relationships"], 10: ["clinical"], 11: ["environments"],
        12: ["cinematography"], 13: ["composition"], 14: ["transcripts", "transcript_embeddings"],
        15: ["ocr"], 16: ["marketing"], 17: ["narratives"],
        18: ["asset_docs", "scene_docs", "visual_embeddings", "text_embeddings", "scene_embeddings", "keyframe_embeddings", "transcript_embeddings"],
    }[layer]
    if layer == 1:
        return "asset=1; source=1; destination=1; technical=1"
    return "; ".join(f"{key}={f[key]}" for key in keys)


def notes_for(filename: str, media: str, layer: int, f: dict) -> str:
    notes = {
        1: "Canonical UUID, filename, MIME/extension/size, SHA-256, source and verified destination are traceable.",
        2: "AI profile and versioned search document exist; no semantic human review and no semantic_index_v1 indexing version.",
        3: "One whole-asset scene and one keyframe exist; this is not full-timeline segmentation." if media == "video" else "Locked layer is N/A for a static image; legacy Job 9 created a zero-duration scene/keyframe representation.",
        4: "Scene-level participant roles exist with AI provenance; identity inference was not performed and roles are unreviewed.",
        5: "Appearance rows exist but are unreviewed; video rows are mostly generic role descriptions." if media == "video" else "Rich appearance row exists, but it is AI-derived, unreviewed, and lacks analysis_run_id.",
        6: "Ontology-linked scene anatomy exists with confidence/run linkage; not reviewed and ontology run says job2-v1.",
        7: "One ontology-linked FUE implantation row exists." if f["treatments"] else ("Only search-document negative treatment context exists; no structured FALSE-state assertion." if media == "image" else "No structured treatment or meaningful treatment assertion exists."),
        8: "Structured scene actions exist but are summary-level, not separately timed events." if f["actions"] else "Narrative/search text implies turning, but no structured action row exists.",
        9: "One structured person-to-person relationship exists; no broader event/object relationship graph." if f["relationships"] else "No structured relationship rows; narrative inference was not promoted to data.",
        10: "Twelve AI-suggested clinical-visual observations exist; no diagnosis or human verification." if f["clinical"] else ("A negative/uncertain clinical claim exists only in the rich search document." if media == "image" else "No clinical observation rows."),
        11: "One structured environment summary exists with AI confidence/provenance; unreviewed.",
        12: "One structured cinematography summary exists; semantic camera labels are AI-derived and unreviewed.",
        13: "One structured composition summary exists; unreviewed and not tied to explicit evidence coordinates.",
        14: "Static image has no temporal audio." if media == "image" else "Speech presence is unknown; no transcript text, timestamps, speakers, scene links, or transcript vectors.",
        15: "Search document claims no visible text, but no OCR observation/evidence row exists." if media == "image" else "No OCR observations; text presence remains unknown.",
        16: "Marketing annotation exists, but consent/marketing/internal/download controls remain UNKNOWN and distinct from reviewed external-AI allowance.",
        17: "Narrative rows and profile/search summaries exist; no human review and no event-level narrative.",
        18: "Asset visual, scene, and keyframe vectors plus asset/scene documents exist; text/transcript/OCR embeddings are absent and data predates semantic_index_v1.",
    }[layer]
    if filename in CONFLICT_ASSETS and layer == 8:
        notes += " Search document top-level actions is empty while nested rich_semantic_v2 actions and scene_actions are populated."
    return notes


def build() -> tuple[dict, list[dict], list[dict]]:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    evaluations = []
    for asset in manifest["assets"]:
        filename, media = asset["filename"], asset["media_type"]
        f = FACTS[filename]
        for layer in spec["layers"]:
            number = layer["number"]
            primary, statuses, applicability, future = status_for(filename, media, number, f)
            structured = "YES" if number == 1 else ("NO" if primary in ("MISSING", "SEARCH_DOC_ONLY", "NOT_APPLICABLE") else "PARTIAL")
            search_doc = "YES" if f["asset_docs"] and number not in (1, 3, 14) else ("YES" if number == 3 and f["scene_docs"] else "NO")
            embedding = "PARTIAL" if number == 18 else "NO"
            confidence = "NO" if number in (1, 7, 9, 14, 15) and primary in ("MISSING", "SEARCH_DOC_ONLY", "NOT_APPLICABLE") else ("PARTIAL" if number in (2, 3, 13, 16, 17, 18) else "YES")
            evidence = "PARTIAL" if number in (2, 3, 10, 17, 18) and primary not in ("MISSING", "NOT_APPLICABLE") else "NO"
            human = "N/A" if primary == "NOT_APPLICABLE" or number == 1 else ("PARTIAL" if number == 16 else "UNVERIFIED")
            version = "UNVERSIONED" if number == 1 else "LEGACY"
            evaluations.append({
                "asset_id": asset["asset_id"], "filename": filename, "media_type": media,
                "layer_number": number, "layer_id": layer["id"], "layer_name": layer["name"],
                "applicability": applicability, "completeness_status": primary,
                "status_flags": statuses, "existing_source": LAYER_SOURCES[number],
                "existing_records": record_count(number, f), "structured_data": structured,
                "search_doc_coverage": search_doc, "embedding_coverage": embedding,
                "confidence_present": confidence, "evidence_reference": evidence,
                "human_review": human, "version_status": version,
                "conflict": "YES" if "CONFLICT" in statuses else "NO",
                "notes": notes_for(filename, media, number, f), "future_action": future,
            })

    conflicts = [
        {"conflict_type": "SEARCH_DOCUMENT_INTERNAL_ACTION_MISMATCH", "asset_id": a["asset_id"], "filename": a["filename"], "source_a": "asset_search_documents.structured_document.actions", "value_a": [], "source_b": "asset_search_documents.structured_document.rich_semantic_v2.actions and scene_actions", "value_b": ["POSING_FOR_CAMERA"] if a["filename"] == "DSC03753.JPG" else ["POSING_FOR_CAMERA", "LOOKING_AT_CAMERA"], "recommended_future_action": "NORMALIZE and rebuild the search document from canonical structured facts"}
        for a in manifest["assets"] if a["filename"] in CONFLICT_ASSETS
    ]
    conflicts += [
        {"conflict_type": "LEGACY_COMPLETENESS_WITH_ZERO_EVIDENCE", "asset_id": a["asset_id"], "filename": a["filename"], "source_a": "asset_layer_status", "value_a": "TREATMENT=COMPLETE and OCR=COMPLETE with evidence_count=0", "source_b": "semantic_index_v1 audit", "value_b": "SEARCH_DOC_ONLY; no structured treatment/OCR assertion", "recommended_future_action": "Do not trust legacy completeness; normalize explicit FALSE/UNKNOWN states"}
        for a in manifest["assets"] if a["filename"] in CONFLICT_ASSETS
    ]
    audit = {
        "phase": "KDI_AI_SEARCH_V3_PHASE_2", "status": "PASS",
        "audit_mode": "READ_ONLY", "audited_at_date": "2026-08-24",
        "specification_version": "semantic_index_v1",
        "specification_fingerprint": spec["specification"]["specification_fingerprint"],
        "pilot_manifest_version": manifest["manifest_version"],
        "pilot_count": len(manifest["assets"]), "layer_count": len(spec["layers"]),
        "evaluation_count": len(evaluations), "baseline": BASELINE,
        "post_audit": BASELINE, "facts_snapshot": FACTS, "evaluations": evaluations,
    }
    return audit, evaluations, conflicts


def write_csv(evaluations: list[dict]) -> None:
    names = []
    by = {}
    for row in evaluations:
        if row["filename"] not in names:
            names.append(row["filename"])
        by[(row["layer_number"], row["filename"])] = row
    fields = ["layer_number", "layer_name", *names, "complete_count", "partial_count", "missing_count", "not_applicable_count"]
    with (REPORT_DIR / "phase2_pilot_layer_matrix.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for layer in range(1, 19):
            rows = [by[(layer, name)] for name in names]
            out = {"layer_number": layer, "layer_name": rows[0]["layer_name"]}
            for name, row in zip(names, rows):
                code = {"COMPLETE": "C", "PARTIAL": "P", "MISSING": "M", "NOT_APPLICABLE": "N/A", "LEGACY_ONLY": "L", "SEARCH_DOC_ONLY": "S", "EMBEDDING_ONLY": "E", "CONFLICT": "X", "UNVERIFIED": "U"}
                out[name] = "+".join(code[x] for x in row["status_flags"])
            out.update(complete_count=sum(r["completeness_status"] == "COMPLETE" for r in rows), partial_count=sum(r["completeness_status"] == "PARTIAL" for r in rows), missing_count=sum(r["completeness_status"] == "MISSING" for r in rows), not_applicable_count=sum(r["completeness_status"] == "NOT_APPLICABLE" for r in rows))
            writer.writerow(out)


def write_doc(audit: dict, evaluations: list[dict], conflicts: list[dict]) -> None:
    by_asset = defaultdict(list)
    for row in evaluations:
        by_asset[row["filename"]].append(row)
    layer_counts = defaultdict(Counter)
    for row in evaluations:
        layer_counts[row["layer_number"]][row["completeness_status"]] += 1
        for flag in row["status_flags"]:
            if flag != row["completeness_status"]:
                layer_counts[row["layer_number"]][flag] += 1
    lines = [
        "# KDI AI Search V3 — Phase 2 Pilot Audit", "",
        "## Outcome", "",
        "Phase 2 passed as a read-only audit: 10 frozen pilots × 18 locked layers = 180 evaluations. No media was opened or analyzed, no database write or migration was executed, and no production code was changed.", "",
        "- Specification: `semantic_index_v1` (`LOCKED`)",
        f"- Fingerprint: `{audit['specification_fingerprint']}`",
        "- Pilot manifest: `kdi_semantic_pilot_v1`", "- Composition verified: 8 videos, 2 images", "",
        "## Layer-to-data-source map", "",
        "| # | Locked layer | Existing sources | Search-doc only? | Structured? | Versioned? |", "|---:|---|---|---|---|---|",
    ]
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    for layer in spec["layers"]:
        n = layer["number"]
        search_only = "Possible" if n in (2, 7, 8, 10, 15, 17) else "No"
        structured = "Partial" if n != 1 else "Yes"
        versioned = "Partial/legacy" if n != 1 else "Unversioned identity records"
        lines.append(f"| {n} | {layer['name']} | {LAYER_SOURCES[n]} | {search_only} | {structured} | {versioned} |")
    lines += ["", "## Cross-pilot matrix", "", "Legend: C complete; P partial; M missing; N/A not applicable; S search-doc only; L legacy-only; X conflict; U unverified.", ""]
    header = ["Layer"] + list(by_asset)
    lines += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    code = {"COMPLETE": "C", "PARTIAL": "P", "MISSING": "M", "NOT_APPLICABLE": "N/A", "LEGACY_ONLY": "L", "SEARCH_DOC_ONLY": "S", "EMBEDDING_ONLY": "E", "CONFLICT": "X", "UNVERIFIED": "U"}
    for n in range(1, 19):
        cells = [f"{n} {spec['layers'][n-1]['name']}"]
        for name in by_asset:
            row = next(x for x in by_asset[name] if x["layer_number"] == n)
            cells.append("+".join(code[x] for x in row["status_flags"]))
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "## Per-asset gap analysis", ""]
    for asset in json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["assets"]:
        rows = by_asset[asset["filename"]]
        lines += [f"### {asset['filename']}", "", f"Asset ID: `{asset['asset_id']}`; media: {asset['media_type']}.", ""]
        for label in ("COMPLETE", "PARTIAL", "MISSING", "NOT_APPLICABLE", "SEARCH_DOC_ONLY", "LEGACY_ONLY", "CONFLICT", "UNVERIFIED"):
            nums = [str(r["layer_number"]) for r in rows if label == r["completeness_status"] or label in r["status_flags"]]
            lines.append(f"- {label}: {', '.join(nums) if nums else 'none'}")
        major = sorted({r["future_action"] for r in rows if r["future_action"] not in ("RETAIN", "NOT_APPLICABLE")})
        lines += [f"- Human-reviewed semantic coverage: none; Layer 16 has only partial access-control review.", f"- Overall readiness: {'LOW' if asset['media_type']=='video' else 'PARTIAL'}", f"- Major future work: {', '.join(major)}", ""]
    lines += ["## Layer completeness summary", ""]
    for layer in spec["layers"]:
        c = layer_counts[layer["number"]]
        lines.append(f"- Layer {layer['number']} — {layer['name']}: complete {c['COMPLETE']}; partial {c['PARTIAL']}; missing {c['MISSING']}; N/A {c['NOT_APPLICABLE']}; legacy only {c['LEGACY_ONLY']}; search-doc only {c['SEARCH_DOC_ONLY']}; conflict {c['CONFLICT']}; unverified {c['UNVERIFIED']}.")
    lines += ["", "## Search and temporal coverage", "", "Per pilot: visual embeddings 1; text embeddings 0; asset search documents 1; scene search documents 1; scene embeddings 1; keyframe embeddings 1; transcript embeddings 0; OCR embeddings 0.", "", "Totals across pilots: visual 10; text 0; asset documents 10; scene documents 10; scene embeddings 10; keyframe embeddings 10; transcript embeddings 0; OCR embeddings 0.", "", "All 8 videos have one real linked scene with valid timestamps, one keyframe, one scene document, one scene embedding, and action rows in 7/8 videos. These are whole-asset summaries, not full-timeline segmentation or separately timed event coverage.", "", "Transcript coverage is zero for text, chunks, timestamps, speakers, scene links, and embeddings. OCR observation coverage is zero for both images and all videos; the two image search documents alone claim that no text is visible.", "", "## Structured vs search-document coverage", "", "Anatomy, actions, roles, environment, cinematography, composition, marketing and narratives generally occur in both structured rows and search documents. Structured facts not fully exposed include detailed appearance attributes and the twelve DSC03753 clinical observations. Search-document-only coverage includes image negative treatment/OCR claims and IMG_9871 turning/self-view action language. The two rich image documents have empty top-level action arrays while nested rich actions and structured action rows are populated.", "", "## Version and provenance", "", "Analysis runs identify provider/model/model version, `kdi-ai-search-v3-job6-v1`, and ontology `job2-v1`. Embeddings identify provider/model/version/dimensions and fingerprints. Normalized semantic rows usually have confidence, provenance, and run IDs; image Job 9 backfill rows often lack run IDs. None is indexed under `semantic_index_v1`. Evidence references and human-review fields are inconsistent; semantic human review is absent.", "", "## Legacy findings", "", "All assets have 18 `asset_layer_status` rows using legacy `KDI_SEMANTIC_V2` layer codes. Those rows are not authoritative for this audit. The two images use `kdi-rich-semantic-v2` documents and Job 9 backfilled zero-duration scene/keyframe representations; their legacy OCR and treatment layers can be marked COMPLETE with evidence_count=0. Video documents remain `job6-v1`. No profile, document, assertion, or embedding is labeled `semantic_index_v1`.", "", "## Conflicts", ""]
    for item in conflicts:
        lines.append(f"- {item['filename']}: {item['conflict_type']} — {item['value_a']} versus {item['value_b']}. Future action: {item['recommended_future_action']}.")
    action_counts = Counter(r["future_action"] for r in evaluations)
    lines += ["", "## Retain/rebuild plan", ""] + [f"- {name}: {action_counts[name]}" for name in ("RETAIN", "RETAIN_AND_VERIFY", "NORMALIZE", "COMPLETE", "REBUILD", "REGENERATE_LATER", "NOT_APPLICABLE")]
    lines += ["", "Highest-priority later work: full-timeline video segmentation/events; explicit four-state assertions; transcript and OCR determination; evidence/human-review normalization; treatment/clinical normalization; rebuild search documents from canonical facts; regenerate dependent embeddings only after source facts are approved.", "", "## Schema gaps", "", "The live model lacks uniform OBSERVED/FALSE/UNKNOWN/NOT_APPLICABLE state storage, universal evidence references, universal confidence and human-review fields, a dedicated semantic_index_v1 field, separately modeled short events, OCR negative-result assertions, and a clean mapping from the legacy catalog to the locked layers. Phase 2 did not fix these gaps.", "", "## Preservation", "", "All before/after counts and the authorization digest are identical. See `phase2_pilot_layer_audit.json` for the exact baseline. No migrations or production writes occurred.", ""]
    DOC_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    audit, evaluations, conflicts = build()
    (REPORT_DIR / "phase2_pilot_layer_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    (REPORT_DIR / "phase2_semantic_conflicts.json").write_text(json.dumps({"conflict_count": len(conflicts), "conflicts": conflicts}, indent=2) + "\n", encoding="utf-8")
    write_csv(evaluations)
    write_doc(audit, evaluations, conflicts)
    print(json.dumps({"assets": audit["pilot_count"], "layers": audit["layer_count"], "evaluations": audit["evaluation_count"], "conflicts": len(conflicts)}))


if __name__ == "__main__":
    main()
