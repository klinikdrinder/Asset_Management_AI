"""Deterministic evidence-grounded narrative rendering and validation."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json, uuid
from pathlib import Path
from typing import Any

NAMESPACE=uuid.UUID("aac1c112-e7a3-47ad-803c-6b831bbcfbe5")

def canonical_fingerprint(value:Any)->str:return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

@dataclass(frozen=True)
class NarrativeConfig:
    values:dict[str,Any]; fingerprint:str
    @classmethod
    def load(cls,path:Path)->"NarrativeConfig":
        values=json.loads(path.read_text(encoding="utf-8"))
        if values.get("generator_version")!="kdi_narrative_generator_v1":raise ValueError("NARRATIVE_VERSION_MISMATCH")
        if not values.get("shadow_mode") or values.get("production_database_writes") or values.get("search_document_writes") or values.get("embedding_generation") or values.get("external_payload_transmission"):raise ValueError("NARRATIVE_SHADOW_SAFETY_MISMATCH")
        return cls(values,canonical_fingerprint(values))
    def __getitem__(self,key:str)->Any:return self.values[key]

def claim_id(asset_id:str,level:str,text:str)->str:return str(uuid.uuid5(NAMESPACE,f"{asset_id}:{level}:{text}"))
def evidence_id(source:str,identifier:str)->str:return f"{source}:{identifier}"
def natural(code:str)->str:return code.lower().replace("_"," ")

def observed_facts(package:dict[str,Any],minimum:float=.75)->list[dict[str,Any]]:
    rows=[]
    for layer in package["layers"]:
        for fact in layer["structured_facts"]:
            if fact.get("state")=="OBSERVED" and fact.get("fact_id") and isinstance(fact.get("confidence"),(int,float)) and fact["confidence"]>=minimum:
                rows.append({**fact,"layer_number":layer["layer_number"],"layer_id":layer["layer_id"]})
    return rows

def concepts_by_layer(facts:list[dict[str,Any]])->dict[int,list[dict[str,Any]]]:
    result={}
    for fact in facts:result.setdefault(fact["layer_number"],[]).append(fact)
    return result

def make_claim(asset_id:str,level:str,text:str,supports:list[str],modality:str="VISUAL",confidence:float=.8,accepted:bool=True)->dict[str,Any]:
    return {"claim_id":claim_id(asset_id,level,text),"text":text,"supports":supports,"assertion_type":modality,"confidence":round(confidence,3),"status":"SUPPORTED" if supports else "UNSUPPORTED","accepted":bool(accepted and supports)}

def render_search_sentence(by_layer:dict[int,list[dict[str,Any]]])->tuple[str,list[str],float]:
    roles=[x for x in by_layer.get(4,[]) if x.get("value") is True]; actions=[x for x in by_layer.get(8,[]) if x.get("value") is True]; anatomy=[x for x in by_layer.get(6,[]) if x.get("value") is True]; treatments=[x for x in by_layer.get(7,[]) if x.get("value") is True]; environments=[x for x in by_layer.get(11,[]) if x.get("value") is True]
    role_text=" and ".join(natural(x["concept"]) for x in roles[:3]) or "visible subject"
    action_text=natural(actions[0]["concept"]) if actions else "shown in the media"
    anatomy_text=" around "+natural(anatomy[0]["concept"]) if anatomy else ""
    treatment_text=" in a "+natural(treatments[0]["concept"])+" context" if treatments else ""
    environment_text=" inside a "+natural(environments[0]["concept"]) if environments else ""
    text=f"{role_text.capitalize()} {action_text}{anatomy_text}{treatment_text}{environment_text}."
    used=(roles[:3]+actions[:1]+anatomy[:1]+treatments[:1]+environments[:1]); supports=[x["fact_id"] for x in used]; confidence=min((x["confidence"] for x in used),default=.75)
    return text,supports,confidence

def validate_claims(claims:list[dict[str,Any]],evidence_ids:set[str],allowed_ocr:set[str],allowed_transcript:set[str])->dict[str,Any]:
    failures=[]
    for claim in claims:
        missing=[x for x in claim["supports"] if x not in evidence_ids]
        if missing:failures.append({"claim_id":claim["claim_id"],"reason":"MISSING_EVIDENCE","missing":missing})
        if claim["assertion_type"]=="OCR" and not set(claim["supports"])<=allowed_ocr:failures.append({"claim_id":claim["claim_id"],"reason":"UNACCEPTED_OCR"})
        if claim["assertion_type"]=="TRANSCRIPT" and not set(claim["supports"])<=allowed_transcript:failures.append({"claim_id":claim["claim_id"],"reason":"UNACCEPTED_TRANSCRIPT"})
    return {"valid":not failures,"failures":failures,"total_claims":len(claims),"supported_claims":len(claims)-len({x["claim_id"] for x in failures}),"unsupported_claims":len({x["claim_id"] for x in failures})}

def functional_output(value:dict[str,Any])->dict[str,Any]:return {k:v for k,v in value.items() if k not in {"generated_at","performance","idempotency"}}
