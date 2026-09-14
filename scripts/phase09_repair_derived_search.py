"""Repair only the canary's derived search-document/E5 lineage; no media analysis."""
import hashlib,json,math,os,re,struct,unicodedata,uuid
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from dotenv import dotenv_values
from sentence_transformers import SentenceTransformer
from supabase import create_client
R=Path(__file__).resolve().parents[1]; A='a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd'; RUN='eb033c75-7964-453e-ba2e-b10a659375e0'
SPEC='kdi_semantic_18_layer_v1'; SPEC_FP='6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7'; DOCV='kdi_search_document_v1_spec_locked'; EMBV='kdi_text_embedding_v1_spec_locked'; BUNDLE='kdi_embedding_bundle_v1_spec_locked'; E5='intfloat/multilingual-e5-small'; E5VER='hf-main-pinned-runtime-v1'; TNORM='unicode_nfkc_whitespace_v1'
def uid(seed): return str(uuid.uuid5(uuid.NAMESPACE_URL,'kdi-phase9:'+seed))
def sha(*xs): return hashlib.sha256('\x1f'.join(str(x) for x in xs).encode()).hexdigest()
def env():
 e={}
 for f in (R/'.env',R/'.env.local',R/'dashboard/.env.local'):
  if f.exists(): e.update({k:v for k,v in dotenv_values(f).items() if v})
 e.update(os.environ); return e
e=env(); c=create_client(e.get('SUPABASE_URL') or e['NEXT_PUBLIC_SUPABASE_URL'],e['SUPABASE_SERVICE_ROLE_KEY']); ts=datetime.now(timezone.utc).isoformat()
asset=c.table('assets').select('id,file_name,mime_type,content_hash,checksum_sha256').eq('id',A).single().execute().data; source=asset.get('content_hash') or asset.get('checksum_sha256')
legacy=c.table('asset_search_documents').select('*').eq('asset_id',A).single().execute().data; text=re.sub(r'\s+',' ',unicodedata.normalize('NFKC',legacy['searchable_text'])).strip(); concepts=legacy['search_concepts']; docfp=hashlib.sha256(text.encode()).hexdigest(); build=uid('build'); docid=uid('document:'+docfp)
c.table('search_document_build_runs').upsert({'id':build,'status':'COMPLETE','search_document_version':DOCV,'builder_version':'kdi_phase9_grounded_builder_v1','configuration_version':'kdi_phase9_search_certification_v1','configuration_fingerprint':sha(DOCV,EMBV,SPEC_FP),'semantic_spec_version':SPEC,'ontology_version':'KDI_SEMANTIC_V2','source_semantic_version':SPEC,'asset_count':1,'asset_document_count':1,'scene_document_count':0,'event_document_count':0,'errors':[],'started_at':ts,'completed_at':ts},on_conflict='id').execute()
doc={'id':docid,'build_run_id':build,'asset_id':A,'document_type':'ASSET','filename':asset['file_name'],'media_type':asset['mime_type'],'normalized_document':legacy['structured_document'],'search_text':text,'positive_concepts':[x.upper().replace(' ','_').replace(',','').replace('/','_') for x in concepts],'negative_concepts':[],'search_document_version':DOCV,'builder_version':'kdi_phase9_grounded_builder_v1','configuration_version':'kdi_phase9_search_certification_v1','configuration_fingerprint':sha(DOCV,EMBV,SPEC_FP),'semantic_spec_version':SPEC,'semantic_spec_fingerprint':SPEC_FP,'ontology_version':'KDI_SEMANTIC_V2','source_semantic_version':SPEC,'source_fingerprint':source,'source_semantic_fingerprint':source,'document_fingerprint':docfp,'status':'READY','review_status':'AI_UNREVIEWED','human_approved':False,'review_required':False,'active':True,'stale':False,'generated_at':ts}
c.table('search_document_builds').upsert(doc,on_conflict='id').execute()
assertions=c.table('semantic_assertions').select('id,layer_id,canonical_concept_code,value_text,confidence').eq('asset_id',A).eq('analysis_run_id',RUN).eq('active',True).eq('semantic_state','OBSERVED').execute().data or []
for a in assertions:
 cid=uid('concept:'+a['id']); c.table('search_document_concepts').upsert({'id':cid,'document_id':docid,'asset_id':A,'concept_type':a['layer_id'],'canonical_code':a['canonical_concept_code'],'display_text':a['value_text'],'semantic_state':'OBSERVED','confidence':a['confidence'],'origin':'DETERMINISTIC_PROCESSOR','resolution_source':'DIRECT','review_status':'AI_UNREVIEWED','assertion_id':a['id'],'search_critical':False},on_conflict='id').execute()
 for ev in c.table('semantic_assertion_evidence').select('id,evidence_type,keyframe_id').eq('assertion_id',a['id']).execute().data or []:
  c.table('search_document_evidence').upsert({'id':uid('evidence:'+ev['id']),'document_id':docid,'concept_id':cid,'assertion_id':a['id'],'assertion_evidence_id':ev['id'],'asset_id':A,'keyframe_id':ev.get('keyframe_id'),'evidence_type':ev['evidence_type']},on_conflict='id').execute()
snaps=sorted((Path.home()/'.cache/huggingface/hub/models--intfloat--multilingual-e5-small/snapshots').glob('*')); model=SentenceTransformer(str(snaps[-1]),local_files_only=True); vec=np.asarray(model.encode('passage: '+text,normalize_embeddings=True),dtype=np.float32); values=vec.tolist(); tfp=sha(text,TNORM,docfp); vfp=hashlib.sha256((E5+'\x1f'+E5VER+'\x1f384\x1f'+tfp+'\x1f').encode()+struct.pack('<'+'f'*384,*values)).hexdigest()
row=c.table('semantic_embeddings').select('id').eq('asset_id',A).eq('analysis_run_id',RUN).eq('stale',False).single().execute().data
c.table('semantic_embeddings').update({'embedding_scope':'TEXT_ASSET','representation_type':'TEXT_ASSET','provider':'sentence_transformers','model':E5,'version':EMBV,'model_version':E5VER,'dimensions':384,'embedding':values,'source_fingerprint':tfp,'source_text_fingerprint':tfp,'source_document_fingerprint':docfp,'source_semantic_version':SPEC,'semantic_spec_version':SPEC,'semantic_spec_fingerprint':SPEC_FP,'ontology_version':'KDI_SEMANTIC_V2','embedding_version':EMBV,'embedding_bundle_version':BUNDLE,'vector_fingerprint':vfp,'text_normalization_version':TNORM,'generated_at':ts,'active':True,'stale':False,'review_status':'AI_UNREVIEWED','metadata':{'source_unit_id':docid,'construction':'passage_prefix_canonical_search_text_v1','phase9_derived_repair':True}}).eq('id',row['id']).execute()
print(json.dumps({'status':'PASS','derived_only':True,'document_id':docid,'document_fingerprint':docfp,'embedding_id':row['id'],'dimensions':384,'model_version':E5VER,'media_analysis':0}))
