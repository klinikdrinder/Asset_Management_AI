from __future__ import annotations

import argparse, hashlib, json, math, os, re, struct, time, unicodedata, uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from dotenv import dotenv_values
from sentence_transformers import SentenceTransformer
from supabase import create_client

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"reports"/"semantic-search"/"completeness"/"kdi_selective_remediation_plan.json"
SPEC="kdi_semantic_18_layer_v1"
SPEC_FP="6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7"
BATCH="29bdc5b9-7256-4ef3-a305-c6358e311bbb"
BUILDER="kdi_selective_search_builder_v1"
CONFIG="kdi_selective_remediation_config_v1"
DOC_VERSION="kdi_search_document_v1_spec_locked"
E5="intfloat/multilingual-e5-small"
E5VER="hf-main-pinned-runtime-v1"
EMBED_VERSION="kdi_text_embedding_v1_spec_locked"
TNORM="unicode_nfkc_whitespace_v1"
PILOTS=("DSC03753.JPG","DSC08097.JPG","IMG_0493.MP4","IMG_0531.MP4","IMG_1148.MP4","IMG_1160.MP4","IMG_1238.MP4","IMG_2963.MP4","IMG_3429.MP4","IMG_9871.MOV")

MASTER={
"DSC03753.JPG":"Static landscape medium close-up of a single adult subject facing the camera against a plain light background, with the face, frontal scalp, and frontal hairline prominent. Visible frontal hair thinning is documented while the subject poses in a white collared shirt. No treatment or procedure can be identified reliably from the stored evidence.",
"DSC08097.JPG":"Static landscape close-up portrait of a single adult subject facing and looking at the camera against a dark neutral background. The subject wears dark clothing and a dark head covering, with the face centered and prominent in the frame. No clinical observation or treatment can be identified reliably from the stored evidence.",
"IMG_0493.MP4":"Static vertical medium clinical footage showing an adult patient reclining while a masked clinician touches and works around the cheek and lower face in a treatment room. Both people are visible and the facial treatment area is partially shown, with the face under active clinical attention. The specific treatment or procedure cannot be identified reliably from the stored evidence.",
"IMG_0531.MP4":"Static vertical medium close-up clinical footage showing an adult patient reclining while a gloved clinician performs an injection at the lower face and lips in a treatment room. The patient's face is prominent and the clinician's hands occupy the foreground, with a visible lower-face injection documented. The evidence supports an injectable procedure, but does not identify a specific product or formulation.",
"IMG_1148.MP4":"Handheld vertical medium clinical footage showing an adult patient reclining while a masked clinician touches the frontal scalp and uses a visible device in a treatment room. The patient's head and clinician dominate the frame, eye protection is visible, and the scalp is under active clinical attention. The specific treatment or procedure cannot be identified reliably from the stored evidence.",
"IMG_1160.MP4":"Handheld vertical extreme close-up showing a gloved clinician cleansing and touching an adult reclining patient's cheek and lower face in a treatment room. The cheek and lower face dominate the frame, with a swab prominent in the foreground and skin cleansing visibly in progress. The specific treatment or procedure cannot be identified reliably from the stored evidence.",
"IMG_1238.MP4":"Handheld vertical medium close-up clinical footage showing an adult patient reclining while a masked, gloved clinician touches the frontal scalp and uses a device in a treatment room. The patient's head is prominent with the clinician and device in frame, and the scalp is under active clinical attention. The specific treatment or procedure cannot be identified reliably from the stored evidence.",
"IMG_2963.MP4":"Handheld vertical medium close-up operating-room footage showing an adult reclining patient with clinicians and staff working on a prepared frontal scalp and recipient region. Multiple clinical hands are visible while grafts are implanted, and the frontal scalp is central in the frame. Stored evidence identifies this as FUE hair-transplant implantation footage.",
"IMG_3429.MP4":"Handheld vertical extreme close-up clinical footage showing an adult patient reclining while gloved clinical hands administer an injection to the neck in a treatment room. The neck treatment area dominates the frame, with the clinician's hands and syringe prominent in the foreground and a visible neck injection documented. The evidence supports an injectable procedure, but the specific injectable treatment cannot be determined reliably.",
"IMG_9871.MOV":"Handheld vertical close-up self-recorded video of a single adult subject facing and looking at the camera in an indoor room. The face is centered and prominent while the subject records the video, with no supported clinician or patient role. No clinical observation or treatment can be identified reliably from the stored evidence."
}

def env():
    d={}
    for p in (ROOT/".env",ROOT/".env.local",ROOT/"dashboard"/".env.local"):
        d.update({k:v for k,v in dotenv_values(p).items() if v})
    d.update(os.environ); return d
def sha(value:str)->str:return hashlib.sha256(value.encode()).hexdigest()
def uid(seed:str)->str:return str(uuid.uuid5(uuid.NAMESPACE_URL,"kdi-selective-v1:"+seed))
def norm_text(s:str)->str:return re.sub(r"\s+"," ",unicodedata.normalize("NFKC",s)).strip()
def vector_fp(source_fp:str,vec:list[float])->str:
    return hashlib.sha256((E5+"\x1f"+E5VER+"\x1f384\x1f"+source_fp+"\x1f").encode()+struct.pack("<"+"f"*384,*vec)).hexdigest()

def main(stage:bool):
    e=env(); url=e.get("NEXT_PUBLIC_SUPABASE_URL") or e.get("SUPABASE_URL"); key=e.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key: raise RuntimeError("Supabase service configuration unavailable")
    db=create_client(url,key)
    assets=db.table("assets").select("id,file_name,mime_type").in_("file_name",list(PILOTS)).execute().data
    if len(assets)!=10 or {x["file_name"] for x in assets}!=set(PILOTS):raise RuntimeError("pilot gate failed")
    byname={x["file_name"]:x for x in assets}; ids=[x["id"] for x in assets]
    layers=db.table("asset_semantic_layers").select("asset_id,layer_id,completeness_status").in_("asset_id",ids).eq("active",True).execute().data
    partial={(next(a["file_name"] for a in assets if a["id"]==x["asset_id"]),x["layer_id"]) for x in layers if x["completeness_status"]=="PARTIAL"}
    expected={(f,l) for f in PILOTS for l in ("GLOBAL_ASSET_UNDERSTANDING","SEMANTIC_NARRATIVE","SEARCH_EMBEDDINGS")}|{("IMG_1238.MP4","TEMPORAL_SCENE_STRUCTURE")}
    if partial!=expected:raise RuntimeError("31-row remediation gate failed")
    profiles={x["asset_id"]:x for x in db.table("asset_ai_profiles").select("asset_id,short_description,detailed_description").in_("asset_id",ids).execute().data}
    assertions=db.table("semantic_assertions").select("id,asset_id,layer_id,predicate,semantic_state,confidence,search_critical").in_("asset_id",ids).eq("active",True).execute().data
    evidence=db.table("semantic_assertion_evidence").select("id,assertion_id").in_("assertion_id",[x["id"] for x in assertions]).execute().data
    evidence_by_assertion={}
    for x in evidence:evidence_by_assertion.setdefault(x["assertion_id"],[]).append(x["id"])
    accepted_trans=db.table("asset_transcript_chunks").select("asset_id,normalized_text,raw_text,id").in_("asset_id",ids).eq("search_status","ACCEPTED_FOR_SEARCH").execute().data
    accepted_ocr=db.table("ocr_observations").select("asset_id,normalized_text,raw_text,id").in_("asset_id",ids).eq("search_status","ACCEPTED_FOR_SEARCH").execute().data
    cfgfp=sha("|".join((SPEC,SPEC_FP,BUILDER,CONFIG,DOC_VERSION,E5,E5VER,EMBED_VERSION,TNORM)))
    now=datetime.now(timezone.utc).isoformat()
    plan={"batch_id":BATCH,"spec_version":SPEC,"spec_fingerprint":SPEC_FP,"configuration_fingerprint":cfgfp,"assets":[]}
    for filename in PILOTS:
        a=byname[filename]; aid=a["id"]; short=profiles[aid]["short_description"]; master=MASTER[filename]
        if not short or master==short or len(master)<len(short)+80:raise RuntimeError(f"description quality failed: {filename}")
        facts=sorted((x for x in assertions if x["asset_id"]==aid),key=lambda x:(x["layer_id"],x["predicate"]))
        observed=[x for x in facts if x["semantic_state"]=="OBSERVED"]
        concepts=sorted({x["predicate"] for x in observed})
        extras=[x.get("normalized_text") or x.get("raw_text") for x in accepted_trans+accepted_ocr if x["asset_id"]==aid]
        search_text=norm_text(f"{filename}. {short} {master} Concepts: {'; '.join(c.replace('_',' ').lower() for c in concepts)}. {' '.join(extras)}")
        source_semantic_fp=sha(json.dumps([(x["id"],x["semantic_state"],x["predicate"]) for x in facts],separators=(",",":")))
        docfp=sha(search_text)
        narrative_id=uid("narrative:"+aid+":"+sha(master))
        doc_id=uid("document:"+aid+":"+docfp)
        run_id=uid("run:"+aid+":"+cfgfp)
        item={"asset_id":aid,"filename":filename,"short_description":short,"master_description":master,
              "narrative_id":narrative_id,"document_id":doc_id,"analysis_run_id":run_id,
              "search_text":search_text,"document_fingerprint":docfp,"source_semantic_fingerprint":source_semantic_fp,
              "claims":[],"concepts":[]}
        sentences=[x.strip()+"." for x in master.split(". ") if x.strip()]
        for i,sentence in enumerate(sentences):
            groups=({"GLOBAL_ASSET_UNDERSTANDING","PEOPLE_ROLES","PERSON_APPEARANCE","ANATOMY","ACTIONS_EVENTS","TREATMENT_PROCEDURE"},
                    {"ENVIRONMENT","CINEMATOGRAPHY","COMPOSITION","CLINICAL_VISUAL_OBSERVATIONS","RELATIONSHIPS"},
                    {"TREATMENT_PROCEDURE","CLINICAL_VISUAL_OBSERVATIONS","SPEECH_TRANSCRIPT_AUDIO","OCR_VISIBLE_TEXT"})
            linked=[x for x in facts if x["layer_id"] in groups[min(i,2)]]
            item["claims"].append({"id":uid(f"claim:{narrative_id}:{i}:{sentence}"),"text":sentence,
                "assertions":[{"assertion_id":x["id"],"evidence_ids":evidence_by_assertion.get(x["id"],[])} for x in linked]})
        for x in observed:
            item["concepts"].append({"id":uid("concept:"+doc_id+":"+x["id"]),"assertion_id":x["id"],"layer_id":x["layer_id"],
                                    "code":x["predicate"],"confidence":x["confidence"],"search_critical":x["search_critical"],
                                    "evidence_ids":evidence_by_assertion.get(x["id"],[])})
        plan["assets"].append(item)
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    if not stage:
        print(json.dumps({"status":"DRY_RUN","assets":10,"allowed_rows":31,"plan":str(OUT),"description_duplicates":0},indent=2));return
    started=time.time(); tm=SentenceTransformer(E5)
    texts=["passage: "+x["search_text"] for x in plan["assets"]]
    vectors=tm.encode(texts,batch_size=10,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)
    completed=time.time(); generated_at=datetime.now(timezone.utc).isoformat()
    build_run_id=uid("build-run:"+cfgfp)
    db.table("search_document_build_runs").upsert({"id":build_run_id,"status":"COMPLETE","search_document_version":DOC_VERSION,
      "builder_version":BUILDER,"configuration_version":CONFIG,"configuration_fingerprint":cfgfp,"semantic_spec_version":SPEC,
      "ontology_version":"KDI_SEMANTIC_V2","source_semantic_version":SPEC,"asset_count":10,"asset_document_count":10,
      "scene_document_count":0,"event_document_count":0,"errors":[],"started_at":now,"completed_at":generated_at},on_conflict="id").execute()
    for item,rawvec in zip(plan["assets"],vectors):
        aid=item["asset_id"]; vec=np.asarray(rawvec,dtype=np.float32); vec/=np.linalg.norm(vec); values=vec.tolist()
        tfp=sha(norm_text(item["search_text"])+"|"+TNORM+"|"+item["document_fingerprint"])
        emb_id=uid("embedding:"+item["document_id"]+":"+tfp)
        item["embedding_id"]=emb_id
        db.table("semantic_analysis_runs").upsert({"id":item["analysis_run_id"],"asset_id":aid,"run_type":"SELECTIVE_V1_REMEDIATION",
          "status":"COMPLETED","semantic_spec_version":SPEC,"semantic_spec_fingerprint":SPEC_FP,"ontology_version":"KDI_SEMANTIC_V2",
          "indexing_version":DOC_VERSION,"embedding_version":EMBED_VERSION,"processor_version":BUILDER,
          "configuration_version":CONFIG,"configuration_fingerprint":cfgfp,"source_fingerprint":item["source_semantic_fingerprint"],
          "provider":"sentence_transformers","model":E5,"model_version":E5VER,"started_at":now,"completed_at":generated_at,
          "metadata":{"description_generation":"deterministic_template_no_model","remediation_batch_id":BATCH}},on_conflict="id").execute()
        db.table("semantic_narratives").upsert({"id":item["narrative_id"],"asset_id":aid,"narrative_type":"ASSET_NARRATIVE",
          "text":item["master_description"],"search_status":"ACCEPTED_FOR_SEARCH","input_evidence_fingerprint":item["source_semantic_fingerprint"],
          "generator_version":"kdi_grounded_template_v1","configuration_version":CONFIG,"analysis_run_id":item["analysis_run_id"],
          "human_review_status":"AI_UNREVIEWED","source_narrative_key":"kdi-v1-master:"+aid+":"+sha(item["master_description"]),
          "semantic_spec_version":SPEC,"semantic_spec_fingerprint":SPEC_FP,"narrative_fingerprint":sha(item["master_description"]),
          "active":False,"stale":False,"updated_at":generated_at},on_conflict="id").execute()
        for claim in item["claims"]:
            db.table("narrative_claims").upsert({"id":claim["id"],"narrative_id":item["narrative_id"],"claim_text":claim["text"],
              "modality_source":"STRUCTURED_SEMANTIC_EVIDENCE","confidence":None,"search_critical":True,"review_status":"AI_UNREVIEWED"},on_conflict="id").execute()
            rows=[]
            for link in claim["assertions"]:
                evs=link["evidence_ids"] or [None]
                for evid in evs:rows.append({"id":uid(f"claim-evidence:{claim['id']}:{link['assertion_id']}:{evid}"),"claim_id":claim["id"],"assertion_id":link["assertion_id"],"evidence_id":evid})
            if rows:db.table("narrative_claim_evidence").upsert(rows,on_conflict="id").execute()
        doc={"id":item["document_id"],"asset_id":aid,"search_document_version":DOC_VERSION,"source_semantic_version":SPEC,
          "source_fingerprint":item["source_semantic_fingerprint"],"document_fingerprint":item["document_fingerprint"],"status":"READY",
          "build_run_id":build_run_id,"document_type":"ASSET","filename":item["filename"],"media_type":byname[item["filename"]]["mime_type"],
          "normalized_document":{"short_description":item["short_description"],"master_description":item["master_description"],"construction":"trusted_available_evidence_v1"},
          "search_text":item["search_text"],"positive_concepts":[x["code"] for x in item["concepts"]],"negative_concepts":[],
          "builder_version":BUILDER,"configuration_version":CONFIG,"configuration_fingerprint":cfgfp,"semantic_spec_version":SPEC,
          "semantic_spec_fingerprint":SPEC_FP,"ontology_version":"KDI_SEMANTIC_V2","source_semantic_fingerprint":item["source_semantic_fingerprint"],
          "review_status":"AI_UNREVIEWED","human_approved":False,"review_required":False,"active":False,"stale":False,"generated_at":generated_at}
        db.table("search_document_builds").upsert(doc,on_conflict="id").execute()
        for c in item["concepts"]:
            db.table("search_document_concepts").upsert({"id":c["id"],"document_id":item["document_id"],"asset_id":aid,
              "concept_type":c["layer_id"],"canonical_code":c["code"],"display_text":c["code"].replace("_"," ").lower(),
              "semantic_state":"OBSERVED","confidence":c["confidence"],"origin":"DETERMINISTIC_PROCESSOR","resolution_source":"DIRECT",
              "review_status":"AI_UNREVIEWED","assertion_id":c["assertion_id"],"search_critical":c["search_critical"]},on_conflict="id").execute()
            evs=c["evidence_ids"] or [None]
            db.table("search_document_evidence").upsert([{"id":uid(f"doc-evidence:{c['id']}:{ev}"),"document_id":item["document_id"],
              "concept_id":c["id"],"assertion_id":c["assertion_id"],"assertion_evidence_id":ev,"asset_id":aid,"evidence_type":"ASSET_LEVEL"} for ev in evs],on_conflict="id").execute()
        db.table("semantic_embeddings").upsert({"id":emb_id,"asset_id":aid,"embedding_scope":"TEXT_ASSET","provider":"sentence_transformers",
          "model":E5,"version":EMBED_VERSION,"dimensions":384,"embedding":values,"source_text_fingerprint":tfp,"source_semantic_version":SPEC,
          "analysis_run_id":item["analysis_run_id"],"stale":False,"representation_type":"TEXT_ASSET","model_version":E5VER,
          "source_fingerprint":tfp,"source_document_fingerprint":item["document_fingerprint"],"semantic_spec_version":SPEC,
          "semantic_spec_fingerprint":SPEC_FP,"ontology_version":"KDI_SEMANTIC_V2","embedding_version":EMBED_VERSION,
          "embedding_bundle_version":"kdi_embedding_bundle_v1_spec_locked","vector_fingerprint":vector_fp(tfp,values),
          "text_normalization_version":TNORM,"generated_at":generated_at,"active":False,"review_status":"AI_UNREVIEWED",
          "metadata":{"source_unit_id":item["document_id"],"construction":"passage_prefix_canonical_search_text_v1","remediation_batch_id":BATCH}},on_conflict="id").execute()
        db.table("semantic_remediation_model_calls").upsert({"id":uid("model-call:"+aid),"remediation_batch_id":BATCH,"asset_id":aid,
          "layer_id":"SEARCH_EMBEDDINGS","purpose":"REGENERATE_CHANGED_ASSET_TEXT_EMBEDDING","provider":"sentence_transformers",
          "model":E5,"model_version":E5VER,"started_at":datetime.fromtimestamp(started,timezone.utc).isoformat(),
          "completed_at":datetime.fromtimestamp(completed,timezone.utc).isoformat(),"duration_ms":round((completed-started)*1000),
          "input_tokens":None,"output_tokens":None,"cost_amount":None,"cost_currency":None,
          "unavailable_reason":"Local sentence-transformers API does not report token usage or billable cost; one batched encode generated ten vectors.",
          "spec_version":SPEC,"spec_fingerprint":SPEC_FP},on_conflict="remediation_batch_id,asset_id,layer_id,purpose").execute()
    OUT.write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"STAGED","assets":10,"text_embeddings":10,"visual_embeddings_generated":0,"model_calls_recorded":10,"plan":str(OUT)},indent=2))

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--stage",action="store_true");args=ap.parse_args();main(args.stage)
