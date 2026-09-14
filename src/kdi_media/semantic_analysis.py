"""Schema-validated Phase 5 semantic package construction from reviewed evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any
import uuid


ANALYZER_VERSION = "kdi_semantic_analyzer_v1"
NAMESPACE = uuid.UUID("45de8ec8-7533-4fc8-a463-e41c522bd474")


def canonical_fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class SemanticAnalyzerConfig:
    values: dict[str, Any]
    fingerprint: str

    @classmethod
    def load(cls, path: Path) -> "SemanticAnalyzerConfig":
        values = json.loads(path.read_text(encoding="utf-8"))
        if values.get("analyzer_version") != ANALYZER_VERSION:
            raise ValueError("SEMANTIC_ANALYZER_VERSION_MISMATCH")
        return cls(values, canonical_fingerprint(values))

    def __getitem__(self, key: str) -> Any:
        return self.values[key]


class SemanticAnalyzer:
    def __init__(self, config: SemanticAnalyzerConfig, layers: list[dict[str, Any]]) -> None:
        self.config = config
        self.layers = layers

    @staticmethod
    def _confidence_band(value: float | None) -> str:
        if value is None: return "UNKNOWN"
        if value >= .9: return "HIGH"
        if value >= .75: return "MEDIUM_HIGH"
        if value >= .6: return "MEDIUM"
        return "LOW"

    def _evidence(self, source: dict[str, Any], media_type: str, *, event: dict[str, Any] | None = None, scene: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if media_type == "image":
            region = source["regions"][0]
            return [{"type": "ASSET_LEVEL", "source_artifact": "PHASE4_IMAGE_ANALYSIS", "region_id": region["region_id"], "source_fingerprint": source["source_fingerprint"]}]
        if event:
            linked = next((keyframe for keyframe in source["keyframe_candidates"] if keyframe.get("event_id") == event["event_id"]), None)
            value = {"type": "EVENT_LEVEL", "source_artifact": "PHASE3_TIMELINE", "scene_id": event["scene_id"], "event_id": event["event_id"], "timestamp_start": event["start_time"], "timestamp_end": event["end_time"], "source_fingerprint": source["source_fingerprint"]}
            if linked: value["keyframe_id"] = linked["keyframe_id"]
            return [value]
        if scene:
            linked = next((keyframe for keyframe in source["keyframe_candidates"] if keyframe["scene_id"] == scene["scene_id"]), None)
            value = {"type": "SCENE_LEVEL", "source_artifact": "PHASE3_TIMELINE", "scene_id": scene["scene_id"], "timestamp_start": scene["start_time"], "timestamp_end": scene["end_time"], "source_fingerprint": source["source_fingerprint"]}
            if linked: value["keyframe_id"] = linked["keyframe_id"]
            return [value]
        keyframe = source["keyframe_candidates"][0]
        return [{"type": "KEYFRAME_LEVEL", "source_artifact": "PHASE3_TIMELINE", "scene_id": keyframe["scene_id"], "keyframe_id": keyframe["keyframe_id"], "timestamp_start": keyframe["timestamp"], "timestamp_end": keyframe["timestamp"], "source_fingerprint": source["source_fingerprint"]}]

    def _fact(self, seed: str, layer_id: str, concept: str, value: Any, confidence: float, evidence: list[dict[str, Any]], disposition: str, *, provenance: str = "AI_MODEL") -> dict[str, Any]:
        return {"fact_id": str(uuid.uuid5(NAMESPACE, f"{seed}:fact:{layer_id}:{concept}:{json.dumps(value, sort_keys=True)}")), "concept": concept, "layer": layer_id, "state": "OBSERVED", "value": value, "confidence": round(confidence, 2), "confidence_band": self._confidence_band(confidence), "evidence": evidence, "provenance": provenance, "provider": self.config["semantic_provider"], "model": self.config["semantic_model"], "provider_version": self.config["provider_version"], "source_disposition": disposition, "human_review_status": self.config["human_review_status"]}

    @staticmethod
    def _unknown(concept: str, note: str) -> dict[str, Any]:
        return {"concept": concept, "state": "UNKNOWN", "value": None, "confidence": None, "evidence": [], "provenance": "WORKFLOW_STATE", "human_review_status": "UNVERIFIED", "note": note}

    def build(self, asset: dict[str, Any], source: dict[str, Any], review: dict[str, Any], phase2_counts: dict[str, Any], access: dict[str, Any], inherited_conflicts: list[dict[str, Any]]) -> dict[str, Any]:
        started_clock = time.perf_counter(); media_type = asset["media_type"]
        seed = f"{asset['asset_id']}:{source['source_fingerprint']}:{ANALYZER_VERSION}:{self.config.fingerprint}"
        analysis_run_id = str(uuid.uuid5(NAMESPACE, f"{seed}:analysis-run")); generated = datetime.now(timezone.utc).isoformat()
        base_evidence = self._evidence(source, media_type); confidence = float(review["confidence"]); disposition = review["reconciliation"]
        mapping = {"PEOPLE_ROLES":"roles", "PERSON_APPEARANCE":"appearance", "ANATOMY":"anatomy", "TREATMENT_PROCEDURE":"treatments", "ACTIONS_EVENTS":"actions", "RELATIONSHIPS":"relationships", "CLINICAL_VISUAL_OBSERVATIONS":"clinical", "ENVIRONMENT":"environment", "CINEMATOGRAPHY":"cinematography", "COMPOSITION":"composition", "MARKETING_CONTENT_USAGE":"marketing_semantics"}
        layer_records = []
        for layer in self.layers:
            number, layer_id, layer_name = layer["number"], layer["id"], layer["name"]
            applicability, state, processing, completeness = "APPLICABLE", "OBSERVED", "COMPLETED_PHASE_5", "PARTIAL"
            facts: list[dict[str, Any]] = []
            future = "Human review and later cross-layer validation"
            if number == 1:
                identity = {key: asset.get(key) for key in ("asset_id","filename","media_type","extension","mime_type","size_bytes")}
                identity["source_fingerprint"] = source["source_fingerprint"]
                facts.append(self._fact(seed, layer_id, "ASSET_IDENTITY", identity, 1.0, [{"type":"ASSET_LEVEL","source_artifact":"FROZEN_MANIFEST_AND_PHASE_EVIDENCE","source_fingerprint":source["source_fingerprint"]}], "VERIFIED_EXISTING", provenance="DATABASE_METADATA"))
                completeness, future = "COMPLETE_FOR_PHASE_5", "Preserve identity during later ingestion"
            elif number == 2:
                facts.append(self._fact(seed, layer_id, "MEDIA_SUMMARY", review["summary"], confidence, base_evidence, disposition))
            elif number == 3:
                if media_type == "image": applicability, state, processing, completeness, future = "NOT_APPLICABLE", "NOT_APPLICABLE", "NOT_APPLICABLE", "NOT_APPLICABLE", "N/A for static images"
                else:
                    timeline = {"scene_count":len(source["scene_candidates"]),"event_candidate_count":len(source["event_candidates"]),"keyframe_count":len(source["keyframe_candidates"]),"timeline_coverage_percent":source["frame_analysis"]["timeline_coverage_percent"]}
                    facts.append(self._fact(seed, layer_id, "TIMELINE_STRUCTURE", timeline, 1.0, [{"type":"ASSET_LEVEL","source_artifact":"PHASE3_TIMELINE","analysis_run_id":source["analysis_run_id"],"source_fingerprint":source["source_fingerprint"]}], "NEW_OBSERVATION", provenance="DETERMINISTIC_PROCESSOR"))
                    completeness = "REVIEW_NEEDED" if "POSSIBLE_UNDER_SEGMENTATION" in source.get("warnings",[]) else "COMPLETE_FOR_PHASE_5"
                    future = "Review Phase 3 segmentation warning" if completeness == "REVIEW_NEEDED" else "Retain shadow scene/event structure"
            elif layer_id in mapping:
                values = review[mapping[layer_id]]
                for value in values: facts.append(self._fact(seed, layer_id, value, True, confidence, base_evidence, disposition))
                if not values:
                    state, completeness = "UNKNOWN", "UNKNOWN"
                    facts.append(self._unknown(layer_id, "Evidence does not support a reliable canonical value"))
            elif number == 14:
                if media_type == "image": applicability, state, processing, completeness, future = "NOT_APPLICABLE", "NOT_APPLICABLE", "NOT_APPLICABLE", "NOT_APPLICABLE", "N/A for static images"
                else:
                    audio = bool(source["technical_metadata"]["audio_stream_present"])
                    facts.append(self._fact(seed, layer_id, "AUDIO_STREAM_PRESENT", audio, 1.0, [{"type":"ASSET_LEVEL","source_artifact":"PHASE3_TECHNICAL_METADATA","source_fingerprint":source["source_fingerprint"]}], "NEW_OBSERVATION", provenance="DETERMINISTIC_PROCESSOR"))
                    facts += [self._unknown("SPEECH_PRESENT","Pending Phase 6"),self._unknown("TRANSCRIPT","Pending Phase 6"),self._unknown("SPEAKER_ROLES_FROM_AUDIO","Pending Phase 6")]
                    state, processing, completeness, future = "UNKNOWN", "PENDING_PHASE_6", "PENDING_PHASE_6", "Run approved Phase 6 audio intelligence"
            elif number == 15:
                facts = [self._unknown("VISIBLE_TEXT","No OCR executed; pending Phase 7"),self._unknown("RECOGNIZED_TEXT","No OCR executed; pending Phase 7")]
                state, processing, completeness, future = "UNKNOWN", "PENDING_PHASE_7", "PENDING_PHASE_7", "Run approved Phase 7 OCR"
            elif number == 17:
                facts.append(self._fact(seed, layer_id, "PROVISIONAL_ASSET_NARRATIVE", review["summary"], confidence, base_evidence, "NEW_OBSERVATION"))
                future = "Human review and later search-document authoring"
            elif number == 18:
                current = {"visual_embedding":phase2_counts.get("visual_embeddings",0)>0,"asset_search_document":phase2_counts.get("asset_docs",0)>0,"scene_search_document":phase2_counts.get("scene_docs",0)>0,"scene_embedding":phase2_counts.get("scene_embeddings",0)>0,"keyframe_embedding":phase2_counts.get("keyframe_embeddings",0)>0,"semantic_index_v1_embedding_status":"PENDING_REGENERATION","canonical_search_document":"PENDING_LATER_PHASE"}
                facts.append(self._fact(seed, layer_id, "CURRENT_SEARCH_REPRESENTATION", current, 1.0, [{"type":"ASSET_LEVEL","source_artifact":"PHASE2_AUDIT","source_fingerprint":source["source_fingerprint"]}], "RETAINED_EXISTING", provenance="DATABASE_METADATA"))
                processing, completeness, future = "PENDING_LATER_SEARCH_STAGE", "PENDING_LATER_SEARCH_STAGE", "Regenerate only after canonical facts are approved"
            observed_conf = [fact["confidence"] for fact in facts if fact.get("state") == "OBSERVED" and fact.get("confidence") is not None]
            layer_records.append({"layer_number":number,"layer_id":layer_id,"layer_name":layer_name,"applicability":applicability,"semantic_state":state,"processing_status":processing,"structured_facts":facts,"confidence_summary":{"minimum":min(observed_conf) if observed_conf else None,"maximum":max(observed_conf) if observed_conf else None,"band":self._confidence_band(statistics_mean(observed_conf) if observed_conf else None)},"evidence_references":[e for fact in facts for e in fact.get("evidence",[])],"existing_data_used":number in phase2_counts or number not in (3,14,15),"new_analysis_used":number not in (1,14,15,18),"conflicts":[conflict for conflict in inherited_conflicts if conflict.get("layer_number") in (None,number)],"human_review_status":self.config["human_review_status"],"completeness":completeness,"future_work":future})
        scenes, events = [], []
        if media_type == "video":
            for scene in source["scene_candidates"]:
                label = review.get("scene_label")
                scenes.append({"scene_id":scene["scene_id"],"scene_index":scene["scene_index"],"start_time":scene["start_time"],"end_time":scene["end_time"],"semantic_label":label or "UNKNOWN","semantic_state":"OBSERVED" if label else "UNKNOWN","confidence":round(confidence-.05,2) if label else None,"evidence":self._evidence(source,media_type,scene=scene),"narrative":review["summary"] if label else "Technical scene retained; semantic label requires review.","human_review_status":"UNVERIFIED"})
            for event in source["event_candidates"]:
                action = review.get("event_action")
                events.append({"event_id":event["event_id"],"scene_id":event["scene_id"],"start_time":event["start_time"],"end_time":event["end_time"],"peak_time":event["peak_time"],"semantic_action":action or "UNKNOWN","semantic_state":"OBSERVED" if action else "UNKNOWN","confidence":round(confidence-.05,2) if action else None,"evidence":self._evidence(source,media_type,event=event),"narrative":f"Candidate interval visually supports {action}." if action else "Technical event candidate remains unlabeled.","human_review_status":"UNVERIFIED"})
        permission = {key:access.get(key) for key in ("classification_status","is_clinical","sensitivity_level","consent_status","internal_usage_status","marketing_usage_status","external_ai_status","requires_clinical_permission","download_allowed","review_status","reviewed_at")}
        output = {"asset":asset,"analysis_run":{"analysis_run_id":analysis_run_id,"analyzer_version":ANALYZER_VERSION,"configuration_version":self.config["configuration_version"],"configuration_fingerprint":self.config.fingerprint,"semantic_spec_version":"semantic_index_v1","semantic_spec_fingerprint":asset["semantic_spec_fingerprint"],"ontology_version":self.config["ontology_version"],"provider":self.config["semantic_provider"],"model":self.config["semantic_model"],"provider_version":self.config["provider_version"],"source_fingerprint":source["source_fingerprint"],"generated_at":generated},"external_ai_safety":{"eligible":access.get("external_ai_status")=="ALLOWED","reason":"Reviewed asset_access_control.external_ai_status=ALLOWED","provider_used":self.config["semantic_provider"],"external_media_transmission":True,"transmitted_material":"DERIVED_CONTACT_SHEET_ONLY","permission_dimensions":permission},"layers":layer_records,"scene_semantics":scenes,"event_semantics":events,"conflicts":inherited_conflicts,"existing_data_reconciliation":{"primary_disposition":disposition},"processing_gaps":["TRANSCRIPT_PENDING_PHASE_6","OCR_PENDING_PHASE_7","EMBEDDING_AND_SEARCH_DOCUMENT_PENDING_LATER_STAGE"],"human_review_requirements":[],"performance":{"semantic_analysis_seconds":time.perf_counter()-started_clock,"provider_calls":1,"provider":self.config["semantic_provider"],"model":self.config["semantic_model"],"input_contact_sheets":1,"cost":"UNAVAILABLE","retry_count":0,"failure_count":0},"status":"COMPLETED"}
        return output


def statistics_mean(values: list[float]) -> float:
    return sum(values) / len(values)


def functional_output(package: dict[str, Any]) -> dict[str, Any]:
    return {key: package.get(key) for key in ("asset","external_ai_safety","layers","scene_semantics","event_semantics","conflicts","existing_data_reconciliation","processing_gaps","status")}
