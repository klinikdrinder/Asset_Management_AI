"""Provider-neutral atomic visual-observation adapter for local Transformers."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Sequence

OBSERVATION_SCHEMA_VERSION = "kdi_visual_observation_v1"
PROMPT_VERSION = "kdi_atomic_observation_multipass_v1"
LOCAL_ANALYZER_VERSION = "kdi_local_multimodal_analyzer_v2"
STATES = {"OBSERVED", "FALSE", "UNKNOWN", "NOT_APPLICABLE"}

def observation_schema() -> dict[str, Any]:
    # Keep the model-facing contract deliberately small.  Free-form JSON values
    # are not supported by lm-format-enforcer on this Transformers path; the
    # normalizer can still coerce the bounded string into typed application data.
    bounded = {"type":"string","maxLength":120}
    item = {"type":"object","properties":{"category":bounded,"claim_type":{"type":"string","enum":["DIRECT_OBSERVATION","INFERENCE_CANDIDATE"]},"concept":bounded,"value":bounded,"state":{"type":"string","enum":sorted(STATES)},"confidence":{"type":"string","enum":["HIGH","MEDIUM","LOW","UNKNOWN"]},"evidence_type":{"type":"string","enum":["ASSET","SCENE","FRAME","KEYFRAME","TIME_RANGE","METADATA"]},"clinical_specificity":{"type":"string","enum":["NONE","GENERIC_CLINICAL","SPECIFIC_TREATMENT","SPECIFIC_PROCEDURE","NAMED_SURGERY"]},"limitations":bounded},"required":["category","concept","state","confidence","evidence_type"]}
    return {"type":"object","properties":{"observations":{"type":"array","items":item,"maxItems":4}},"required":["observations"]}

def validate_observations(payload: Any, duration_ms: int | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("observations"), list): raise ValueError("INVALID_OBSERVATION_PACKAGE")
    for obs in payload["observations"]:
        if not isinstance(obs, dict) or obs.get("state") not in STATES: raise ValueError("INVALID_OBSERVATION_STATE")
        if obs.get("claim_type") == "INFERENCE_CANDIDATE" and obs.get("state") == "OBSERVED": raise ValueError("INFERENCE_CANNOT_BE_OBSERVED")
        if obs.get("clinical_specificity") == "NAMED_SURGERY" and obs.get("state") == "OBSERVED": raise ValueError("NAMED_CLINICAL_TERM_REQUIRES_GATE")
        if obs["state"] in {"OBSERVED","FALSE"} and obs.get("evidence_type") is None: raise ValueError("OBSERVATION_EVIDENCE_REQUIRED")
        for key in ("timestamp_ms","start_ms","end_ms"):
            value=obs.get(key)
            if isinstance(value,int) and (value<0 or (duration_ms is not None and value>duration_ms)): raise ValueError("INVALID_OBSERVATION_TIMESTAMP")
        if isinstance(obs.get("start_ms"),int) and isinstance(obs.get("end_ms"),int) and obs["end_ms"]<obs["start_ms"]: raise ValueError("INVALID_OBSERVATION_RANGE")
    return {"schema_version": OBSERVATION_SCHEMA_VERSION, **payload}

class LocalObservationProvider:
    provider_name = "LOCAL_TRANSFORMERS"
    provider_version = LOCAL_ANALYZER_VERSION
    def __init__(self, model_path: str | Path, max_new_tokens: int = 256):
        from transformers import AutoProcessor, AutoModelForImageTextToText
        import torch
        self.torch=torch; self.processor=AutoProcessor.from_pretrained(str(model_path),local_files_only=True); self.model=AutoModelForImageTextToText.from_pretrained(str(model_path),local_files_only=True,torch_dtype=torch.float32); self.model.eval(); self.max_new_tokens=max_new_tokens
    def analyze_image(self, image: Any) -> dict[str, Any]: return self._infer([image], self._observation_prompt(False), None)
    def analyze_video_keyframes(self, frames: Sequence[Any], duration_ms: int) -> dict[str, Any]: return self._infer(list(frames), self._observation_prompt(True, len(frames)), duration_ms)
    @staticmethod
    def _observation_prompt(video: bool, count: int = 1) -> str:
        tags=' '.join('<image>' for _ in range(count))
        return (tags+" Return JSON only matching the atomic observation schema. Report DIRECT_OBSERVATION facts that are plainly visible: people/person count, gloves or PPE, visible body regions, objects/instruments, physical contact or motion, broad indoor/outdoor environment, framing and composition. Use one concise observation per fact and KEYFRAME evidence. Describe objects and physical actions; do not name a medical procedure, diagnosis, identity, role, or treatment. Never output surgery, transplant, FUE, implantation, extraction, or a named procedure as an observed fact; if a clinical interpretation is uncertain omit it. Use UNKNOWN only for an evaluated indeterminate fact; do not turn omission into FALSE. For video, preserve ordered keyframe evidence and timestamps.")
    def _infer(self, images: list[Any], prompt: str, duration_ms: int | None) -> dict[str, Any]:
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
        inputs=self.processor(text=prompt,images=images,return_tensors='pt'); fn=build_transformers_prefix_allowed_tokens_fn(self.processor.tokenizer,JsonSchemaParser(observation_schema()))
        with self.torch.no_grad(): generated=self.model.generate(**inputs,max_new_tokens=self.max_new_tokens,prefix_allowed_tokens_fn=fn,do_sample=False)
        text=self.processor.batch_decode(generated,skip_special_tokens=True)[0]
        start=text.find('{')
        if start < 0: raise ValueError("INVALID_STRUCTURED_OUTPUT")
        try: payload=json.loads(text[start:])
        except json.JSONDecodeError as exc: raise ValueError("INVALID_STRUCTURED_OUTPUT") from exc
        return validate_observations(payload,duration_ms)
