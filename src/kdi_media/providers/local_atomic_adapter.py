"""Bounded atomic visual questions for conservative local semantic extraction."""
from __future__ import annotations
from typing import Any, Sequence
import re

QUESTION_BANK = (
    ("people", "Is one or more people or body parts clearly visible? Answer only YES, NO, or UNCERTAIN."),
    ("objects", "Are a handheld object, tool, or instrument and protective clothing/gloves clearly visible? Answer only YES, NO, or UNCERTAIN."),
    ("anatomy", "Is a distinct exposed body region clearly visible? Answer only YES, NO, or UNCERTAIN."),
    ("action", "Is a physical contact, holding, or manipulation action clearly visible? Answer only YES, NO, or UNCERTAIN."),
    ("environment", "Is a broad indoor or outdoor environment clearly visible? Answer only YES, NO, or UNCERTAIN."),
)
UNSAFE_TERMS={"surgery","transplant","fue","implantation","extraction","prp","laser treatment"}

def parse_atomic(text: str) -> str:
    tokens=re.findall(r"\b(YES|NO|UNCERTAIN)\b",text.upper())
    if not tokens: return "UNKNOWN"
    if tokens[-1] in {"YES","NO"}: return "OBSERVED" if tokens[-1]=="YES" else "FALSE"
    return "UNKNOWN"

def merge_atomic(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    clean=[]
    for r in results:
        value=str(r.get("raw_response", ""))
        if any(t in value.lower() for t in UNSAFE_TERMS):
            r={**r,"state":"UNKNOWN","claim_type":"INFERENCE_CANDIDATE","clinical_specificity":"NAMED_SURGERY","limitations":"Specific clinical term rejected by gate."}
        clean.append(r)
    return {"schema_version":"kdi_visual_observation_v1","prompt_version":"kdi_atomic_observation_multipass_v1","observations":clean}

class LocalAtomicObservationProvider:
    provider_name="LOCAL_TRANSFORMERS"
    def __init__(self, model_path: str, max_new_tokens: int=12):
        from transformers import AutoProcessor, AutoModelForImageTextToText
        import torch
        self.torch=torch; self.processor=AutoProcessor.from_pretrained(model_path,local_files_only=True); self.model=AutoModelForImageTextToText.from_pretrained(model_path,local_files_only=True,torch_dtype=torch.float32); self.model.eval(); self.max_new_tokens=max_new_tokens
    def analyze_image_atomic(self, image: Any) -> dict[str, Any]:
        out=[]
        for category,question in QUESTION_BANK:
            messages=[{"role":"user","content":[
                {"type":"image"},
                {"type":"text","text":question+" Do not name a diagnosis, treatment, procedure, or identity."},
            ]}]
            prompt=self.processor.apply_chat_template(messages,add_generation_prompt=True)
            inputs=self.processor(text=prompt,images=[image],return_tensors='pt')
            with self.torch.no_grad(): generated=self.model.generate(**inputs,max_new_tokens=self.max_new_tokens,do_sample=False)
            # Decoder-only multimodal models return prompt + completion.  Parse
            # only newly generated tokens so answer choices in the question do
            # not get mistaken for the model's answer.
            completion=generated[:,inputs["input_ids"].shape[1]:]
            raw=self.processor.batch_decode(completion,skip_special_tokens=True)[0].strip()
            out.append({'category':category,'claim_type':'DIRECT_OBSERVATION','concept':category,'state':parse_atomic(raw),'confidence':'MEDIUM','evidence_type':'KEYFRAME','raw_response':raw[:160],'clinical_specificity':'NONE'})
        return merge_atomic(out)
