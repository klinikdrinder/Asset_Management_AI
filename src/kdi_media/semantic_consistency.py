"""Cross-layer graph and deterministic compatibility rules for Phase 9."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,uuid
from pathlib import Path
from typing import Any

NAMESPACE=uuid.UUID("bdc59793-00d6-408a-9ec0-daa461582189")
def canonical_fingerprint(value:Any)->str:return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

@dataclass(frozen=True)
class ConsistencyConfig:
    values:dict[str,Any];fingerprint:str
    @classmethod
    def load(cls,path:Path)->"ConsistencyConfig":
        values=json.loads(path.read_text())
        if values.get("validator_version")!="kdi_semantic_consistency_v1":raise ValueError("CONSISTENCY_VERSION_MISMATCH")
        if not values.get("shadow_mode") or values.get("database_writes") or values.get("media_analysis") or values.get("database_migrations"):raise ValueError("CONSISTENCY_SAFETY_MISMATCH")
        return cls(values,canonical_fingerprint(values))
    def __getitem__(self,key:str)->Any:return self.values[key]

def observed_codes(package:dict[str,Any],layer_number:int)->set[str]:
    layer=next(x for x in package["layers"] if x["layer_number"]==layer_number)
    return {x["concept"] for x in layer["structured_facts"] if x.get("state")=="OBSERVED" and x.get("value") is True}

def rule(rule_id:str,state:str,severity:str|None,summary:str,evidence:list[str]|None=None,issues:list[dict[str,Any]]|None=None)->dict[str,Any]:
    return {"rule_id":rule_id,"state":state,"severity":severity,"summary":summary,"evidence_references":evidence or [],"issues":issues or []}

def compatibility(left:set[str],right:set[str],mapping:dict[str,list[str]])->tuple[bool,list[str]]:
    bad=[]
    for concept in left:
        allowed=set(mapping.get(concept,[]))
        if allowed and right and not (allowed&right):bad.append(concept)
    return not bad,bad

def build_graph(asset_id:str,semantic:dict[str,Any],timeline:dict[str,Any]|None,narrative:dict[str,Any])->dict[str,Any]:
    nodes=[{"id":f"asset:{asset_id}","type":"ASSET"}];edges=[]
    for layer in semantic["layers"]:
        for fact in layer["structured_facts"]:
            if fact.get("fact_id"):
                nodes.append({"id":f"fact:{fact['fact_id']}","type":"FACT","layer_id":layer["layer_id"],"state":fact.get("state"),"concept":fact.get("concept")});edges.append({"from":f"asset:{asset_id}","to":f"fact:{fact['fact_id']}","type":"HAS_FACT"})
                for evidence in fact.get("evidence",[]):
                    eid=canonical_fingerprint(evidence)[:20];nodes.append({"id":f"evidence:{eid}","type":"EVIDENCE","evidence_type":evidence.get("type")});edges.append({"from":f"fact:{fact['fact_id']}","to":f"evidence:{eid}","type":"SUPPORTED_BY"})
    if timeline:
        for scene in timeline["scene_candidates"]:nodes.append({"id":f"scene:{scene['scene_id']}","type":"SCENE"});edges.append({"from":f"asset:{asset_id}","to":f"scene:{scene['scene_id']}","type":"HAS_SCENE"})
        for event in timeline["event_candidates"]:nodes.append({"id":f"event:{event['event_id']}","type":"EVENT"});edges.append({"from":f"scene:{event['scene_id']}","to":f"event:{event['event_id']}","type":"HAS_EVENT"})
    for claim in narrative["claims"]:
        nodes.append({"id":f"claim:{claim['claim_id']}","type":"NARRATIVE_CLAIM","status":claim["status"]})
        for support in claim["supports"]:edges.append({"from":f"claim:{claim['claim_id']}","to":support if support.startswith(("scene:","event:")) else f"fact:{support}" if len(support)==36 else support,"type":"SUPPORTED_BY"})
    unique={x["id"]:x for x in nodes};return {"nodes":list(unique.values()),"edges":edges,"node_count":len(unique),"edge_count":len(edges)}

def functional_output(value:dict[str,Any])->dict[str,Any]:return {k:v for k,v in value.items() if k not in {"generated_at","performance","idempotency"}}
