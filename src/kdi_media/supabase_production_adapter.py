"""Idempotent persistence adapter for the canonical semantic index.

All writes are scoped to one run and one explicitly frozen manifest. Rows are
staged inactive and are activated only after the completeness gate succeeds.
This adapter does not alter ACL, consent, marketing approval, or external-AI
eligibility fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

from supabase import Client


@dataclass(frozen=True)
class ManifestScope:
    asset_ids: frozenset[str]
    locked_asset_ids: frozenset[str]

    def assert_allowed(self, asset_id: str) -> None:
        if asset_id not in self.asset_ids:
            raise ValueError(f"asset {asset_id} is outside the frozen production manifest")
        if asset_id in self.locked_asset_ids:
            raise ValueError(f"certified asset {asset_id} is immutable")


def _l2_mean_pool(vectors: list[list[float]]) -> list[float]:
    """Mean pool then L2 normalise, matching the certified scene aggregation."""
    if not vectors:
        return []
    size = len(vectors[0])
    pooled = [sum(vector[i] for vector in vectors) / len(vectors) for i in range(size)]
    norm = sum(x * x for x in pooled) ** 0.5 or 1e-12
    return [x / norm for x in pooled]


class CanonicalSemanticPersistenceAdapter:
    """Concrete adapter used by the trusted background indexing worker."""

    ACTIVE_TABLES = frozenset({
        "asset_semantic_layers", "semantic_assertions", "semantic_narratives",
        "search_document_builds", "semantic_embeddings",
    })

    def __init__(self, client: Client, scope: ManifestScope, *,
                 media_source: Callable[[str], tuple[bytes, dict[str, Any]]] | None = None,
                 evidence_source: Callable[[str], Any] | None = None,
                 text_embedder: Callable[[str], list[float]] | None = None,
                 visual_embedder: Callable[[str], list[float]] | None = None) -> None:
        self.db = client
        self.scope = scope
        self.current_run_id: str | None = None
        # Injected by the trusted worker so this adapter stays free of transport and model concerns.
        self.media_source = media_source
        self.evidence_source = evidence_source
        self.text_embedder = text_embedder
        self.visual_embedder = visual_embedder
        self.last_build: dict[str, Any] = {}

    def eligibility(self, asset_id: str):
        from .production_indexer import AssetEligibility
        self.scope.assert_allowed(asset_id)
        asset = self.db.table("assets").select("id,mime_type").eq("id", asset_id).single().execute().data
        acl = self.db.table("asset_access_control").select(
            "classification_status,internal_usage_status,external_ai_status"
        ).eq("asset_id", asset_id).single().execute().data
        return AssetEligibility(asset_id, str(asset.get("mime_type", "")),
                                str(acl.get("classification_status", "UNKNOWN")),
                                str(acl.get("internal_usage_status", "UNKNOWN")),
                                str(acl.get("external_ai_status", "UNKNOWN")))

    def acquire(self, asset_id: str) -> tuple[bytes, dict[str, Any]]:
        """Read-only master retrieval with checksum verification.

        The bytes are returned for image assets only. A video is never returned whole to the
        semantic provider: `prepare_video_evidence` supplies keyframe JPEGs instead.
        """
        self.scope.assert_allowed(asset_id)
        if self.media_source is None:
            raise NotImplementedError("media acquisition is supplied by the trusted worker")
        return self.media_source(asset_id)

    def prepare_video_evidence(self, asset_id: str):
        """Local evidence for one video, produced entirely on this machine."""
        self.scope.assert_allowed(asset_id)
        if self.evidence_source is None:
            raise NotImplementedError("video evidence preparation is supplied by the trusted worker")
        return self.evidence_source(asset_id)

    def begin_run(self, run: Mapping[str, Any]) -> None:
        self.scope.assert_allowed(str(run["asset_id"]))
        self.current_run_id = str(run["id"])
        self.db.table("semantic_analysis_runs").upsert(dict(run), on_conflict="id").execute()
        self.db.table("search_document_build_runs").upsert({
            "id": self.current_run_id,
            "status": "RUNNING",
            "search_document_version": "kdi_search_document_v1",
            "builder_version": "kdi_search_document_builder_v1",
            "configuration_version": "kdi_search_document_config_v1",
            "configuration_fingerprint": str(run.get("configuration_fingerprint") or self.current_run_id),
            "semantic_spec_version": "semantic_index_v1",
            "ontology_version": "KDI_SEMANTIC_V2",
            "source_semantic_version": "semantic_index_v1",
            "asset_count": 1,
            "asset_document_count": 0,
            "scene_document_count": 0,
            "event_document_count": 0,
            "errors": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="id").execute()

    def stage_rows(self, table: str, rows: Iterable[Mapping[str, Any]], *, asset_id: str) -> None:
        self.scope.assert_allowed(asset_id)
        payload = [dict(row) for row in rows]
        if not payload:
            return
        # Every staged representation is inactive. Existing history is retained.
        for row in payload:
            if table in self.ACTIVE_TABLES:
                row.setdefault("active", False)
            if table in {"semantic_embeddings"}:
                row.setdefault("stale", False)
        self.db.table(table).upsert(payload, on_conflict=self._conflict(table)).execute()

    @staticmethod
    def _conflict(table: str) -> str:
        return {
            "asset_semantic_layers": "asset_id,layer_id,analysis_run_id",
            "semantic_assertions": "idempotency_key",
            "asset_scenes": "asset_id,scene_index,semantic_version",
            "asset_keyframes": "id",
            "asset_transcript_chunks": "id",
            "ocr_observations": "id",
            "semantic_embeddings": "id",
            "search_document_builds": "id",
            "semantic_narratives": "id",
        }.get(table, "id")

    STAGE_ORDER = ("asset_scenes", "asset_keyframes", "asset_semantic_layers", "semantic_assertions",
                   "semantic_assertion_evidence", "semantic_narratives", "search_document_builds",
                   "semantic_embeddings")

    def stage(self, asset_id: str, package: Mapping[str, Any]) -> None:
        """Builds and stages every canonical row for one asset, all inactive."""
        self.scope.assert_allowed(asset_id)
        if "rows" in package:
            for table, rows in package.get("rows", {}).items():
                self.stage_rows(table, rows, asset_id=asset_id)
            return
        rows = self.build_rows(asset_id, package)
        # Assertions land non-critical, evidence attaches, then search_critical is raised: the
        # database evidence guard is a deferred constraint and PostgREST commits per request.
        critical = [r["id"] for r in rows.get("semantic_assertions", []) if r.get("search_critical")]
        for row in rows.get("semantic_assertions", []):
            row["search_critical"] = False
        for table in self.STAGE_ORDER:
            self.stage_rows(table, rows.get(table, []), asset_id=asset_id)
        for assertion_id in critical:
            self.db.table("semantic_assertions").update({"search_critical": True}).eq("id", assertion_id).execute()
        self.last_build[asset_id] = {table: len(rows.get(table, [])) for table in self.STAGE_ORDER}

    def build_rows(self, asset_id: str, package: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
        """Assembles canonical rows from the validated semantic package plus local evidence."""
        from . import canonical_rows as cr
        run_id = self.current_run_id
        if not run_id:
            raise RuntimeError("cannot stage without an active analysis run")
        semantic = package["semantic"]
        evidence = package.get("evidence")
        metadata = package.get("metadata", {})
        source_fp = str(metadata.get("checksum") or metadata.get("source_fingerprint") or asset_id)
        filename = str(metadata.get("filename") or asset_id)
        media_type = "VIDEO" if evidence is not None else str(metadata.get("media_type") or "IMAGE")
        out: dict[str, list[dict[str, Any]]] = {table: [] for table in self.STAGE_ORDER}
        out["asset_semantic_layers"] = cr.layer_rows(asset_id, run_id, semantic)

        scene_packages = semantic.get("scene_packages", [])
        scene_visual: list[tuple[str, list[float]]] = []
        if evidence is not None:
            existing_scene_rows = self.db.table("asset_scenes").select(
                "id,scene_index,semantic_version"
            ).eq("asset_id", asset_id).execute().data or []
            existing_scene_ids = {
                int(row["scene_index"]): str(row["id"])
                for row in existing_scene_rows
                if row.get("semantic_version") == cr.SPEC
            }
            existing_keyframe_rows = self.db.table("asset_keyframes").select(
                "id,scene_id,frame_index,semantic_version"
            ).eq("asset_id", asset_id).execute().data or []
            existing_keyframe_ids = {
                (str(row["scene_id"]), int(row["frame_index"])): str(row["id"])
                for row in existing_keyframe_rows
                if row.get("semantic_version") == cr.SPEC
            }
            for scene, scene_package in zip(evidence.scenes, scene_packages):
                scene_id = existing_scene_ids.get(
                    scene.scene_index,
                    cr.unit_uid(asset_id, source_fp, "scene", scene.scene_index),
                )
                a, e, positives = cr.assertion_rows(asset_id, run_id, scene_package, source_fp,
                                                    scene_id=scene_id,
                                                    start_time=round(scene.start_seconds, 3),
                                                    end_time=round(scene.end_seconds, 3))
                out["semantic_assertions"] += a
                out["semantic_assertion_evidence"] += e
                text = cr.searchable_text(filename + " scene " + str(scene.scene_index + 1), scene_package,
                                          scene.ocr_texts + scene.transcript_texts, positives)
                description = cr.normalize(str(scene_package.get("narrative", "")))[:500]
                if not description:
                    description = "Scene " + str(scene.scene_index + 1) + " of " + filename + "."
                scene_row = cr.scene_row(asset_id, run_id, scene, scene_package, description,
                                         source_fingerprint=source_fp)
                scene_row["id"] = scene_id
                out["asset_scenes"].append(scene_row)
                kfs = cr.keyframe_rows(asset_id, run_id, scene, scene_id, source_fp)
                for keyframe in kfs:
                    keyframe["id"] = existing_keyframe_ids.get(
                        (scene_id, int(keyframe["frame_index"])), keyframe["id"]
                    )
                out["asset_keyframes"] += kfs
                document_id = cr.uid(run_id + ":scenedoc:" + str(scene.scene_index))
                document = cr.document_row(document_id, run_id, asset_id, filename, media_type, text,
                                           positives, document_type="SCENE", scene_id=scene_id,
                                           start_time=round(scene.start_seconds, 3),
                                           end_time=round(scene.end_seconds, 3),
                                           source_fingerprint=source_fp)
                out["search_document_builds"].append(document)
                if self.text_embedder:
                    out["semantic_embeddings"].append(cr.text_embedding_row(
                        cr.uid(run_id + ":textscene:" + str(scene.scene_index)), run_id, asset_id,
                        self.text_embedder("passage: " + text), text, document["document_fingerprint"],
                        scope="TEXT_SCENE", scene_id=scene_id, source_unit_id=document_id))
                if self.visual_embedder:
                    vectors = []
                    for keyframe, path in zip(kfs, scene.keyframe_paths):
                        vector = self.visual_embedder(path)
                        vectors.append(vector)
                        out["semantic_embeddings"].append(cr.visual_embedding_row(
                            cr.unit_uid(asset_id, source_fp, "vkf", keyframe["id"]), run_id, asset_id, vector, source_fp,
                            scope="VISUAL_KEYFRAME", scene_id=scene_id, keyframe_id=keyframe["id"],
                            metadata={"timestamp_seconds": keyframe["timestamp_seconds"]}))
                    if vectors:
                        pooled = _l2_mean_pool(vectors)
                        scene_visual.append((scene_id, pooled))
                        out["semantic_embeddings"].append(cr.visual_embedding_row(
                            cr.unit_uid(asset_id, source_fp, "vscene", scene.scene_index), run_id, asset_id, pooled,
                            source_fp, scope="VISUAL_SCENE", scene_id=scene_id,
                            metadata={"aggregation": "l2_mean_pool_l2_v1",
                                      "member_keyframe_ids": [k["id"] for k in kfs]}))

        grounded = []
        if evidence is not None:
            grounded = [t for scene in evidence.scenes for t in scene.ocr_texts + scene.transcript_texts]
        a, e, positives = cr.assertion_rows(asset_id, run_id, semantic, source_fp)
        out["semantic_assertions"] += a
        out["semantic_assertion_evidence"] += e
        asset_text = cr.searchable_text(filename, semantic, grounded, positives)
        asset_document_id = cr.uid(run_id + ":assetdoc")
        asset_document = cr.document_row(asset_document_id, run_id, asset_id, filename, media_type,
                                         asset_text, positives, document_type="ASSET",
                                         source_fingerprint=source_fp)
        out["search_document_builds"].append(asset_document)
        out["semantic_narratives"].append(cr.narrative_row(
            run_id, asset_id, semantic, str(semantic.get("narrative", "")), positives
        ))
        if self.text_embedder:
            out["semantic_embeddings"].append(cr.text_embedding_row(
                cr.uid(run_id + ":textasset"), run_id, asset_id,
                self.text_embedder("passage: " + asset_text), asset_text,
                asset_document["document_fingerprint"], scope="TEXT_ASSET",
                source_unit_id=asset_document_id))
        if self.visual_embedder and evidence is None and metadata.get("visual_path"):
            out["semantic_embeddings"].append(cr.visual_embedding_row(
                cr.unit_uid(asset_id, source_fp, "vasset"), run_id, asset_id,
                self.visual_embedder(str(metadata["visual_path"])), source_fp,
                scope="VISUAL_ASSET", metadata={"source": "LOCAL_PREPARED_MASTER"}))
        if self.visual_embedder and scene_visual:
            out["semantic_embeddings"].append(cr.visual_embedding_row(
                cr.unit_uid(asset_id, source_fp, "vasset"), run_id, asset_id,
                _l2_mean_pool([vector for _, vector in scene_visual]), source_fp,
                scope="VISUAL_ASSET", metadata={"aggregation": "l2_mean_pool_l2_v1",
                                                "member_scene_ids": [sid for sid, _ in scene_visual]}))
        self.asset_document_text = asset_text
        return out

    def completeness(self, asset_id: str) -> bool:
        self.scope.assert_allowed(asset_id)
        if not self.current_run_id:
            return False
        rows = self.db.table("asset_semantic_layers").select(
            "layer_id,processing_status,semantic_state,active"
        ).eq("asset_id", asset_id).eq("analysis_run_id", self.current_run_id).execute().data or []
        return len(rows) == 18 and all(
            row.get("processing_status") == "COMPLETE" and
            row.get("semantic_state") in {"OBSERVED", "FALSE", "UNKNOWN", "NOT_APPLICABLE"}
            for row in rows
        )

    def publish(self, asset_id: str) -> None:
        self.scope.assert_allowed(asset_id)
        if not self.completeness(asset_id):
            raise RuntimeError("refusing SEARCH_READY publication before completeness")
        if not self.current_run_id:
            raise RuntimeError("cannot publish without an active analysis run")
        rid = self.current_run_id
        # Deactivate prior current records, retain them for provenance, then
        # activate only rows produced by this run. The database view
        # kdi_search_ready_assets_v1 remains the final publication authority.
        for table in ("asset_semantic_layers", "semantic_assertions", "semantic_narratives",
                      "search_document_builds", "semantic_embeddings"):
            self.db.table(table).update({"active": False}).eq("asset_id", asset_id).eq("active", True).execute()
        for table in ("asset_semantic_layers", "semantic_assertions"):
            self.db.table(table).update({"active": True}).eq("asset_id", asset_id).eq("analysis_run_id", rid).execute()
        self.db.table("semantic_narratives").update({"active": True, "stale": False}).eq(
            "asset_id", asset_id).eq("analysis_run_id", rid).execute()
        self.db.table("search_document_builds").update({"active": True, "stale": False}).eq(
            "asset_id", asset_id).eq("build_run_id", rid).execute()
        self.db.table("semantic_embeddings").update({"active": True, "stale": False}).eq(
            "asset_id", asset_id).eq("analysis_run_id", rid).execute()
        self.db.table("search_document_build_runs").update({
            "status": "COMPLETE", "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", rid).execute()
        # Scenes carry their own canonical flag rather than `active`. They are unit-keyed, so the
        # rows this run touched are exactly the ones local preparation created for this checksum.
        self.db.table("asset_scenes").update({"canonical_active": False}).eq("asset_id", asset_id).eq("canonical_active", True).execute()
        self.db.table("asset_scenes").update({"canonical_active": True}).eq("asset_id", asset_id).eq("semantic_analysis_run_id", rid).execute()
        self.db.table("semantic_analysis_runs").update({
            "status": "COMPLETED", "completed_at": datetime.now(timezone.utc).isoformat(),
            "error_code": None, "error_message": None,
        }).eq("id", rid).execute()

    def fail(self, asset_id: str, code: str, detail: str) -> None:
        self.scope.assert_allowed(asset_id)
        self.db.table("semantic_analysis_runs").update({
            "status": "FAILED", "error_code": code, "error_message": detail[:1000]
        }).eq("asset_id", asset_id).eq("status", "RUNNING").execute()
        if self.current_run_id:
            self.db.table("search_document_build_runs").update({
                "status": "FAILED", "errors": [detail[:1000]],
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", self.current_run_id).execute()
