from __future__ import annotations

import gc, hashlib, json, math, os, re, struct, subprocess, sys, tempfile, time, unicodedata, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import dotenv_values
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from PIL import Image
from sentence_transformers import SentenceTransformer
from supabase import create_client

ROOT=Path(__file__).resolve().parents[2]; DASH=ROOT/"dashboard"; OUT=ROOT/"reports"/"semantic-search"/"phase12"; OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
PILOTS=[("IMG_0531.MP4","7f72217d-3839-4920-86b4-ccc33e9e3d95"),("IMG_1238.MP4","babae120-9372-42ad-b535-02a3276ea2be"),("IMG_3429.MP4","c86344e9-5b32-4d86-9205-67952d508651"),("IMG_9871.MOV","444da390-0117-4380-8c87-d7c32f2903ff"),("DSC03753.JPG","37838d30-a0ce-4f90-8cc3-c986db0aaa65"),("DSC08097.JPG","6215ad8b-12be-4a8e-bc49-f6b3dcf55c21"),("IMG_0493.MP4","64712c6a-c02c-46e9-9f73-16786109468b"),("IMG_1148.MP4","47611c6d-7923-42a4-87b6-c2a416a90f5c"),("IMG_2963.MP4","bfae6c51-5d71-47ae-a3e1-6d07092b8896"),("IMG_1160.MP4","753eb5f3-82c7-4148-a226-d5b960fd8619")]
IDS={x[1] for x in PILOTS}; BUNDLE="kdi_embedding_bundle_v1"; VV="kdi_visual_embedding_v1"; TV="kdi_text_embedding_v1"; SPEC="semantic_index_v1"; ONTOLOGY="KDI_SEMANTIC_V2"; VPRE="openclip_exif_rgb_bicubic_v1"; VAGG="l2_mean_pool_l2_v1"; TNORM="unicode_nfkc_whitespace_v1"; E5="intfloat/multilingual-e5-small"; E5VER="hf-main-pinned-runtime-v1"

def env():
    result={}
    for p in (ROOT/".env",ROOT/".env.local",DASH/".env.local"): result.update({k:v for k,v in dotenv_values(p).items() if v})
    result.update(os.environ);return result
def sha(*parts:Any)->str:return hashlib.sha256("\x1f".join(str(x) for x in parts).encode()).hexdigest()
def file_sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(8*1024*1024),b""):h.update(block)
    return h.hexdigest()
def uid(seed:str)->str:return str(uuid.uuid5(uuid.NAMESPACE_URL,"kdi-phase12:"+seed))
def norm(v:list[float])->list[float]:
    a=np.asarray(v,dtype=np.float32);n=float(np.linalg.norm(a));
    if not math.isfinite(n) or n<=1e-9:raise ValueError("invalid vector norm")
    a/=n
    if not np.isfinite(a).all():raise ValueError("non-finite vector")
    return a.tolist()
def aggregate(vs:list[list[float]])->list[float]:return norm(np.mean(np.asarray(vs,dtype=np.float32),axis=0).tolist())
def vfp(model:str,version:str,dims:int,source_fp:str,vector:list[float])->str:
    return hashlib.sha256((model+"\x1f"+version+"\x1f"+str(dims)+"\x1f"+source_fp+"\x1f").encode()+struct.pack("<"+"f"*dims,*vector)).hexdigest()
def text_normalize(s:str)->str:return re.sub(r"\s+"," ",unicodedata.normalize("NFKC",s)).strip()
def download(drive,file_id:str,target:Path):
    req=drive.files().get_media(fileId=file_id,supportsAllDrives=True)
    with target.open("wb") as fh:
        d=MediaIoBaseDownload(fh,req,chunksize=16*1024*1024);done=False
        while not done:_,done=d.next_chunk(num_retries=4)
def frame(ffmpeg:Path,source:Path,timestamp:float,target:Path):
    r=subprocess.run([str(ffmpeg),"-loglevel","error","-ss",f"{timestamp:.6f}","-i",str(source),"-frames:v","1","-q:v","2","-y",str(target)],capture_output=True,timeout=120)
    if r.returncode or not target.exists() or target.stat().st_size==0:raise RuntimeError(f"frame extraction failed at {timestamp}: {r.stderr.decode(errors='ignore')[:300]}")
    with Image.open(target) as im:
        if im.width<=0 or im.height<=0:raise RuntimeError("zero-size frame")
        return im.width,im.height
def cosine(a:list[float],b:list[float])->float:return float(np.dot(np.asarray(a,dtype=np.float32),np.asarray(b,dtype=np.float32)))
def table_all(db,name:str,select="*",filters=()):
    q=db.table(name).select(select)
    for method,args in filters:q=getattr(q,method)(*args)
    return q.limit(1000).execute().data or []

e=env();url=e.get("NEXT_PUBLIC_SUPABASE_URL") or e.get("SUPABASE_URL");key=e.get("SUPABASE_SERVICE_ROLE_KEY");cred=e.get("GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_PATH") or e.get("GOOGLE_APPLICATION_CREDENTIALS")
if not url or not key or not cred:raise RuntimeError("database/drive configuration unavailable")
db=create_client(url,key);drive=build("drive","v3",credentials=service_account.Credentials.from_service_account_file(cred,scopes=["https://www.googleapis.com/auth/drive.readonly"]),cache_discovery=False)
assets={x["id"]:x for x in table_all(db,"assets","id,original_file_name,mime_type,checksum_sha256,content_hash",(("in_",("id",list(IDS))),))};
if set(assets)!=IDS:raise RuntimeError("pilot set mismatch")
manifest=json.loads((ROOT/"reports"/"semantic-search"/"phase11_1"/"phase11_1_import_manifest.json").read_text())
for filename,aid in PILOTS:
    a=assets[aid];fp=a.get("checksum_sha256") or a.get("content_hash")
    if a["original_file_name"]!=filename or any(x["source_fingerprint"]!=fp for x in manifest["records"] if x["asset_id"]==aid):raise RuntimeError(f"fingerprint mismatch {aid}")
    a["source_fingerprint"]=fp
dest={x["asset_id"]:x for x in table_all(db,"asset_destinations","asset_id,destination_google_file_id,upload_status",(("in_",("asset_id",list(IDS))),)) if x.get("upload_status")=="VERIFIED" and x.get("destination_google_file_id")}
if set(dest)!=IDS:raise RuntimeError(f"missing verified media destinations: {IDS-set(dest)}")
scenes=table_all(db,"asset_scenes","id,asset_id,scene_index,start_seconds,end_seconds,semantic_state,review_status,metadata",(("in_",("asset_id",list(IDS))), ("eq",("canonical_active",True))))
events=table_all(db,"asset_events","id,asset_id,scene_id,start_time,end_time,technical_only,semantic_state,canonical_action,review_status",(("in_",("asset_id",list(IDS))),))
keyframes=table_all(db,"asset_keyframes","id,asset_id,scene_id,event_id,timestamp_seconds,frame_index,selection_reason,source_fingerprint",(("in_",("asset_id",list(IDS))), ("eq",("semantic_version",SPEC))))
docs=table_all(db,"search_document_builds","id,asset_id,scene_id,event_id,document_type,search_text,document_fingerprint,review_status,active",(("in_",("asset_id",list(IDS))), ("eq",("active",True))))
trans=table_all(db,"asset_transcript_chunks","id,asset_id,scene_id,event_id,normalized_text,raw_text,source_text_fingerprint,search_status,human_review_status",(("in_",("asset_id",list(IDS))),))
ocr=table_all(db,"ocr_observations","id,asset_id,scene_id,event_id,normalized_text,raw_text,source_text_fingerprint,search_status,metadata",(("in_",("asset_id",list(IDS))),))
if (len(scenes),len(events),len(keyframes),len(docs))!=(11,22,44,37):raise RuntimeError(f"canonical input count mismatch {(len(scenes),len(events),len(keyframes),len(docs))}")
if sum(not x["technical_only"] and x["semantic_state"]=="OBSERVED" for x in events)!=16:raise RuntimeError("semantic event count mismatch")

generated: list[dict[str,Any]]=[]; perf={"download_seconds":0.0,"frame_extraction_seconds":0.0,"keyframe_embedding_seconds":0.0,"scene_aggregation_seconds":0.0,"asset_aggregation_seconds":0.0,"text_embedding_seconds":0.0,"db_write_seconds":0.0}; extracted=[]
from dashboard.visual_indexing.openclip_encoder import OpenClipEncoder,MODEL_NAME,MODEL_VERSION
vstart=time.perf_counter();enc=OpenClipEncoder(); visual_by_kf={}; visual_by_scene={}; visual_by_asset={}
ffmpeg=ROOT/".tools"/"ffmpeg"/"bin"/"ffmpeg.exe"
with tempfile.TemporaryDirectory(prefix="kdi-phase12-") as td:
    temp=Path(td)
    for filename,aid in PILOTS:
        source=temp/(aid+Path(filename).suffix.lower());t=time.perf_counter();download(drive,dest[aid]["destination_google_file_id"],source);perf["download_seconds"]+=time.perf_counter()-t
        if file_sha(source)!=assets[aid]["source_fingerprint"]:raise RuntimeError(f"download fingerprint mismatch {aid}")
        if assets[aid]["mime_type"].startswith("image/"):
            t=time.perf_counter();vec=enc.embed_image(source);perf["asset_aggregation_seconds"]+=time.perf_counter()-t
            sf=sha(assets[aid]["source_fingerprint"],"FULL_IMAGE",VPRE);visual_by_asset[aid]=vec
            generated.append({"id":uid(f"VISUAL_ASSET:{aid}:{sf}:{VV}"),"asset_id":aid,"representation_type":"VISUAL_ASSET","provider":"open_clip","model":MODEL_NAME,"model_version":MODEL_VERSION,"dimensions":512,"embedding":vec,"source_fingerprint":sf,"source_text_fingerprint":None,"source_document_fingerprint":None,"embedding_version":VV,"vector_fingerprint":vfp(MODEL_NAME,MODEL_VERSION,512,sf,vec),"preprocessing_version":VPRE,"metadata":{"source":"FULL_IMAGE","exif_orientation_normalized":True}})
        else:
            for k in sorted((x for x in keyframes if x["asset_id"]==aid),key=lambda x:float(x["timestamp_seconds"])):
                target=temp/(k["id"]+".jpg");t=time.perf_counter();dims=frame(ffmpeg,source,float(k["timestamp_seconds"]),target);perf["frame_extraction_seconds"]+=time.perf_counter()-t
                t=time.perf_counter();vec=enc.embed_image(target);perf["keyframe_embedding_seconds"]+=time.perf_counter()-t
                sf=sha(assets[aid]["source_fingerprint"],k["id"],k["timestamp_seconds"],k.get("frame_index"),VPRE);visual_by_kf[k["id"]]=vec
                generated.append({"id":uid(f"VISUAL_KEYFRAME:{k['id']}:{sf}:{VV}"),"asset_id":aid,"scene_id":k["scene_id"],"event_id":k.get("event_id"),"keyframe_id":k["id"],"representation_type":"VISUAL_KEYFRAME","provider":"open_clip","model":MODEL_NAME,"model_version":MODEL_VERSION,"dimensions":512,"embedding":vec,"source_fingerprint":sf,"source_text_fingerprint":None,"source_document_fingerprint":None,"embedding_version":VV,"vector_fingerprint":vfp(MODEL_NAME,MODEL_VERSION,512,sf,vec),"preprocessing_version":VPRE,"metadata":{"timestamp_seconds":float(k["timestamp_seconds"]),"frame_index":k.get("frame_index"),"decoded_dimensions":dims,"seek_tolerance_seconds":0.25,"selection_reason":k.get("selection_reason")}});extracted.append({"keyframe_id":k["id"],"timestamp":float(k["timestamp_seconds"]),"dimensions":dims,"decoder":"ffmpeg"});target.unlink()
            for s in sorted((x for x in scenes if x["asset_id"]==aid),key=lambda x:x["scene_index"]):
                members=sorted((x for x in keyframes if x["scene_id"]==s["id"]),key=lambda x:float(x["timestamp_seconds"]));t=time.perf_counter();vec=aggregate([visual_by_kf[x["id"]] for x in members]);perf["scene_aggregation_seconds"]+=time.perf_counter()-t
                fps=[next(z["vector_fingerprint"] for z in generated if z.get("keyframe_id")==x["id"]) for x in members];sf=sha(*fps,VAGG);visual_by_scene[s["id"]]=vec
                generated.append({"id":uid(f"VISUAL_SCENE:{s['id']}:{sf}:{VV}"),"asset_id":aid,"scene_id":s["id"],"representation_type":"VISUAL_SCENE","provider":"open_clip","model":MODEL_NAME,"model_version":MODEL_VERSION,"dimensions":512,"embedding":vec,"source_fingerprint":sf,"source_text_fingerprint":None,"source_document_fingerprint":None,"embedding_version":VV,"vector_fingerprint":vfp(MODEL_NAME,MODEL_VERSION,512,sf,vec),"preprocessing_version":VAGG,"metadata":{"aggregation":VAGG,"member_keyframe_ids":[x["id"] for x in members],"start_seconds":float(s["start_seconds"]),"end_seconds":float(s["end_seconds"])}})
            ss=sorted((x for x in scenes if x["asset_id"]==aid),key=lambda x:x["scene_index"]);t=time.perf_counter();vec=aggregate([visual_by_scene[x["id"]] for x in ss]);perf["asset_aggregation_seconds"]+=time.perf_counter()-t
            fps=[next(z["vector_fingerprint"] for z in generated if z.get("scene_id")==x["id"] and z["representation_type"]=="VISUAL_SCENE") for x in ss];sf=sha(*fps,VAGG);visual_by_asset[aid]=vec
            generated.append({"id":uid(f"VISUAL_ASSET:{aid}:{sf}:{VV}"),"asset_id":aid,"representation_type":"VISUAL_ASSET","provider":"open_clip","model":MODEL_NAME,"model_version":MODEL_VERSION,"dimensions":512,"embedding":vec,"source_fingerprint":sf,"source_text_fingerprint":None,"source_document_fingerprint":None,"embedding_version":VV,"vector_fingerprint":vfp(MODEL_NAME,MODEL_VERSION,512,sf,vec),"preprocessing_version":VAGG,"metadata":{"aggregation":VAGG,"member_scene_ids":[x["id"] for x in ss]}})
    qtests={};all_visual=[x for x in generated if x["representation_type"]=="VISUAL_KEYFRAME"]
    for query in ("clinician","patient","scalp","face","clinical procedure"):
        q=enc.embed_text(query);top=sorted(((cosine(q,x["embedding"]),x["asset_id"],x.get("keyframe_id")) for x in all_visual),reverse=True)[:5];qtests[query]=[{"similarity":s,"asset_id":a,"keyframe_id":k} for s,a,k in top]
del enc;gc.collect();perf["visual_total_seconds"]=time.perf_counter()-vstart

tstart=time.perf_counter();tm=SentenceTransformer(E5);text_items=[]
for d in docs:
    rtype={"ASSET":"TEXT_ASSET","SCENE":"TEXT_SCENE","EVENT":"TEXT_EVENT"}[d["document_type"]]
    text_items.append((rtype,d,text_normalize(d["search_text"])))
for x in trans:
    if x["search_status"]=="ACCEPTED_FOR_SEARCH":text_items.append(("TEXT_TRANSCRIPT",x,text_normalize(x.get("normalized_text") or x.get("raw_text") or "")))
for x in ocr:
    if x["search_status"]=="ACCEPTED_FOR_SEARCH":text_items.append(("TEXT_OCR",x,text_normalize(x.get("normalized_text") or x.get("raw_text") or "")))
texts=["passage: "+x[2] for x in text_items];tokens=[len(tm.tokenizer.encode(x,add_special_tokens=True)) for x in texts]
if any(n>tm.max_seq_length for n in tokens):raise RuntimeError("text exceeds model context; compact source construction required")
t=time.perf_counter();vectors=tm.encode(texts,batch_size=8,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False);perf["text_embedding_seconds"]+=time.perf_counter()-t
text_vectors={}
for (rtype,x,txt),tok,rawvec in zip(text_items,tokens,vectors):
    vec=norm(rawvec.tolist());aid=x["asset_id"];docfp=x.get("document_fingerprint");tfp=sha(txt,TNORM,docfp or x.get("source_text_fingerprint"));unit=x.get("id")
    row={"id":uid(f"{rtype}:{unit}:{tfp}:{TV}"),"asset_id":aid,"scene_id":x.get("scene_id"),"event_id":x.get("event_id"),"transcript_chunk_id":x.get("id") if rtype=="TEXT_TRANSCRIPT" else None,"ocr_observation_id":x.get("id") if rtype=="TEXT_OCR" else None,"representation_type":rtype,"provider":"sentence_transformers","model":E5,"model_version":E5VER,"dimensions":384,"embedding":vec,"source_fingerprint":tfp,"source_text_fingerprint":tfp,"source_document_fingerprint":docfp,"embedding_version":TV,"vector_fingerprint":vfp(E5,E5VER,384,tfp,vec),"text_normalization_version":TNORM,"metadata":{"source_unit_id":unit,"token_count":tok,"truncated":False,"construction":"passage_prefix_canonical_search_text_v1" if rtype.startswith("TEXT_") and rtype not in("TEXT_TRANSCRIPT","TEXT_OCR") else "passage_prefix_normalized_source_text_v1","source_kind":"OCR_ONLY" if rtype=="TEXT_OCR" else rtype.removeprefix("TEXT_")}}
    generated.append(row);text_vectors[row["id"]]=vec
perf["text_total_seconds"]=time.perf_counter()-tstart

# Shared immutable metadata and phase-specific analysis-run lineage.
now=datetime.now(timezone.utc).isoformat();cfgv=sha(BUNDLE,VV,TV,VPRE,VAGG,TNORM,MODEL_NAME,MODEL_VERSION,E5,E5VER)
runs=[]
for _,aid in PILOTS:
    for kind,proc,modelver in (("PHASE12_VISUAL_EMBEDDING","kdi_phase12_visual_processor_v1",MODEL_VERSION),("PHASE12_TEXT_EMBEDDING","kdi_phase12_text_processor_v1",E5VER)):
        runs.append({"id":uid(f"run:{kind}:{aid}:{cfgv}"),"asset_id":aid,"run_type":kind,"status":"COMPLETED","semantic_spec_version":SPEC,"ontology_version":ONTOLOGY,"embedding_version":VV if "VISUAL" in kind else TV,"pilot_manifest_version":"kdi_semantic_pilot_v1","processor_version":proc,"configuration_version":"kdi_phase12_embedding_config_v1","configuration_fingerprint":cfgv,"source_fingerprint":assets[aid]["source_fingerprint"],"provider":"open_clip" if "VISUAL" in kind else "sentence_transformers","model":MODEL_NAME if "VISUAL" in kind else E5,"model_version":modelver,"started_at":now,"completed_at":now})
runmap={(x["asset_id"],"VISUAL" if "VISUAL" in x["run_type"] else "TEXT"):x["id"] for x in runs}
for x in generated:
    x.update({"embedding_scope":x["representation_type"],"version":x["embedding_version"],"source_semantic_version":SPEC,"semantic_spec_version":SPEC,"ontology_version":ONTOLOGY,"embedding_bundle_version":BUNDLE,"analysis_run_id":runmap[(x["asset_id"],"VISUAL" if x["representation_type"].startswith("VISUAL") else "TEXT")],"generated_at":now,"active":True,"stale":False,"review_status":"AI_UNREVIEWED"})

# Sanity checks before any database write.
counts={k:sum(x["representation_type"]==k for x in generated) for k in ("VISUAL_ASSET","VISUAL_SCENE","VISUAL_KEYFRAME","TEXT_ASSET","TEXT_SCENE","TEXT_EVENT","TEXT_TRANSCRIPT","TEXT_OCR")}
expected={"VISUAL_ASSET":10,"VISUAL_SCENE":11,"VISUAL_KEYFRAME":44,"TEXT_ASSET":10,"TEXT_SCENE":11,"TEXT_EVENT":16,"TEXT_TRANSCRIPT":3,"TEXT_OCR":1}
if counts!=expected:raise RuntimeError(f"coverage mismatch {counts}")
for x in generated:
    if len(x["embedding"])!=x["dimensions"] or not all(math.isfinite(v) for v in x["embedding"]) or abs(np.linalg.norm(x["embedding"])-1)>1e-4:raise RuntimeError(f"integrity failure {x['id']}")
visual_k=[x for x in generated if x["representation_type"]=="VISUAL_KEYFRAME"]
self_ex=[]
for x in visual_k:
    scores=sorted(((cosine(x["embedding"],y["embedding"]),y["id"]) for y in visual_k),reverse=True);rank=next(i+1 for i,z in enumerate(scores) if z[1]==x["id"])
    if rank!=1:self_ex.append({"id":x["id"],"rank":rank,"top":scores[0]})
text_docs=[x for x in generated if x["representation_type"].startswith("TEXT")]
text_self=[]
for x in text_docs:
    scores=sorted(((cosine(x["embedding"],y["embedding"]),y["id"]) for y in text_docs if y["representation_type"]==x["representation_type"]),reverse=True);rank=next(i+1 for i,z in enumerate(scores) if z[1]==x["id"])
    if rank!=1:text_self.append({"id":x["id"],"rank":rank,"top":scores[0]})
coherence=[]
for s in scenes:
    sv=visual_by_scene[s["id"]];members=[visual_by_kf[k["id"]] for k in keyframes if k["scene_id"]==s["id"]];others=[visual_by_kf[k["id"]] for k in keyframes if k["scene_id"]!=s["id"]]
    coherence.append({"scene_id":s["id"],"member_mean":float(np.mean([cosine(sv,v) for v in members])),"unrelated_mean":float(np.mean([cosine(sv,v) for v in others])) if others else None,"member_count":len(members)})

# Idempotent database write. Historical versions remain untouched.
t=time.perf_counter();db.table("semantic_analysis_runs").upsert(runs,on_conflict="id").execute()
for i in range(0,len(generated),4):db.table("semantic_embeddings").upsert(generated[i:i+4],on_conflict="id").execute()
perf["db_write_seconds"]=time.perf_counter()-t;perf["total_seconds"]=sum(v for k,v in perf.items() if k.endswith("_total_seconds") or k=="db_write_seconds")

# Reports omit raw vectors while retaining complete fingerprints and lineage.
lineage=[{k:v for k,v in x.items() if k!="embedding"} for x in generated]
(OUT/"phase12_embedding_lineage.json").write_text(json.dumps({"generated_at":now,"embedding_bundle_version":BUNDLE,"count":len(lineage),"embeddings":lineage},indent=2)+"\n")
(OUT/"phase12_visual_embeddings.json").write_text(json.dumps({"generated_at":now,"provider":"open_clip","model":MODEL_NAME,"model_version":MODEL_VERSION,"dimensions":512,"counts":{k:v for k,v in counts.items() if k.startswith("VISUAL")},"frame_extraction":extracted,"aggregation":VAGG},indent=2)+"\n")
(OUT/"phase12_text_embeddings.json").write_text(json.dumps({"generated_at":now,"provider":"sentence_transformers","model":E5,"model_version":E5VER,"dimensions":384,"counts":{k:v for k,v in counts.items() if k.startswith("TEXT")},"normalization":TNORM,"ocr_decision":"EMBEDDED","max_tokens":max(tokens),"truncated":0},indent=2)+"\n")
(OUT/"phase12_embedding_integrity.json").write_text(json.dumps({"generated_at":now,"count":len(generated),"expected":expected,"actual":counts,"finite":True,"non_zero":True,"normalized":True,"dimensions":{"visual":512,"text":384},"vector_fingerprints":len({x["vector_fingerprint"] for x in generated}),"source_fingerprints":sum(bool(x["source_fingerprint"]) for x in generated)},indent=2)+"\n")
(OUT/"phase12_similarity_sanity.json").write_text(json.dumps({"generated_at":now,"visual_keyframe_self_retrieval":{"tested":len(visual_k),"rank1":len(visual_k)-len(self_ex),"exceptions":self_ex},"text_self_retrieval":{"tested":len(text_docs),"rank1":len(text_docs)-len(text_self),"exceptions":text_self},"scene_coherence":coherence},indent=2)+"\n")
(OUT/"phase12_cross_modal_sanity.json").write_text(json.dumps({"generated_at":now,"space":"OpenCLIP matching text/image encoders","queries":qtests,"purpose":"sanity only; not an accuracy benchmark"},indent=2)+"\n")
(OUT/"phase12_performance.json").write_text(json.dumps({"generated_at":now,**perf,"units":"seconds","representation_count":len(generated)},indent=2)+"\n")
print(json.dumps({"status":"GENERATED","counts":counts,"total":len(generated),"performance":perf,"visual_self_exceptions":len(self_ex),"text_self_exceptions":len(text_self)},indent=2))
