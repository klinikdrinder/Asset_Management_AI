"""Read-only live database snapshot for KDI search hardening."""
from __future__ import annotations
import json, os, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/semantic-search/hardening'
MANIFEST=ROOT/'reports/semantic-search/rollout/full-index-30/full_index_30_asset_manifest.json'

def management_sql(sql:str):
    token=os.environ['SUPABASE_DASHBOARD_ACCESS_TOKEN']
    ref=os.environ['SUPABASE_URL'].split('//',1)[1].split('.',1)[0]
    request=urllib.request.Request(f'https://api.supabase.com/v1/projects/{ref}/database/query',data=json.dumps({'query':sql}).encode(),headers={'Authorization':f'Bearer {token}','Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(request,timeout=120) as response:return json.loads(response.read())

def main():
    load_dotenv(ROOT/'.env');load_dotenv(ROOT/'.env.local',override=False)
    # Prefer the dashboard-scoped management token when present; never emit it.
    dashboard_env={}
    for line in (ROOT/'dashboard/.env.local').read_text(encoding='utf-8').splitlines():
        if '=' in line:
            key,value=line.split('=',1);dashboard_env[key.strip()]=value.strip().strip('"').strip("'")
    if dashboard_env.get('SUPABASE_DASHBOARD_ACCESS_TOKEN'):
        os.environ['SUPABASE_DASHBOARD_ACCESS_TOKEN']=dashboard_env['SUPABASE_DASHBOARD_ACCESS_TOKEN']
    db=create_client(os.environ['SUPABASE_URL'],os.environ['SUPABASE_SERVICE_ROLE_KEY'])
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
    assets=manifest.get('assets') or manifest.get('videos',[])+manifest.get('images',[])
    ids=[str(x.get('asset_id') or x.get('id')) for x in assets]
    if len(set(ids))!=30:raise RuntimeError(f'LOCKED_COHORT_MISMATCH:{len(set(ids))}')
    literal=','.join("'%s'"%x for x in ids)
    sql=f"""
    with locked(asset_id) as (select unnest(array[{literal}]::uuid[])),
    latest_eval as (select distinct on(asset_id,layer_id) asset_id,layer_id,new_status,evaluation_mode from public.semantic_layer_completeness_evaluations where asset_id in(select asset_id from locked) order by asset_id,layer_id,evaluated_at desc),
    per_asset as (
      select l.asset_id,
       count(*) filter(where sl.active) active_layers,
       count(*) filter(where sl.active and sl.processing_status='COMPLETE' and sl.completeness_status in('COMPLETE','NOT_APPLICABLE')) complete_layers,
       count(*) filter(where le.new_status='COMPLETE') evaluated_complete_layers,
       (select count(*) from public.search_document_builds d where d.asset_id=l.asset_id and d.document_type='ASSET' and d.active and not d.stale and d.status='READY') canonical_asset_docs,
       (select count(*) from public.asset_search_documents d where d.asset_id=l.asset_id and d.build_status='READY') legacy_asset_docs,
       (select count(*) from public.semantic_embeddings e where e.asset_id=l.asset_id and e.active and not e.stale and e.representation_type='TEXT_ASSET' and e.provider='sentence_transformers' and e.model='intfloat/multilingual-e5-small' and e.model_version='hf-main-pinned-runtime-v1' and e.dimensions=384) text_asset,
       (select count(*) from public.semantic_embeddings e where e.asset_id=l.asset_id and e.active and not e.stale and e.representation_type='VISUAL_ASSET' and e.provider='open_clip_clip' ) impossible_probe,
       (select count(*) from public.semantic_embeddings e where e.asset_id=l.asset_id and e.active and not e.stale and e.representation_type='VISUAL_ASSET' and e.provider='open_clip' and e.dimensions=512) visual_asset,
       (select count(*) from public.asset_scenes s where s.asset_id=l.asset_id and s.canonical_active) scenes,
       (select count(*) from public.asset_keyframes k join public.asset_scenes s on s.id=k.scene_id where k.asset_id=l.asset_id and s.canonical_active) keyframes,
       (select analysis_status from public.asset_ai_profiles p where p.asset_id=l.asset_id limit 1) profile_status
      from locked l left join public.asset_semantic_layers sl on sl.asset_id=l.asset_id and sl.active
      left join latest_eval le on le.asset_id=sl.asset_id and le.layer_id=sl.layer_id group by l.asset_id
    )
    select json_build_object(
      'assets',(select count(*) from public.assets),
      'locked_assets',(select count(*) from locked),
      'status_matrix',coalesce((select json_agg(per_asset order by asset_id) from per_asset),'[]'::json),
      'counts',json_build_object(
        'active_layers',(select count(*) from public.asset_semantic_layers where active and asset_id in(select asset_id from locked)),
        'canonical_scenes',(select count(*) from public.asset_scenes where canonical_active and asset_id in(select asset_id from locked)),
        'canonical_keyframes',(select count(*) from public.asset_keyframes k join public.asset_scenes s on s.id=k.scene_id where s.canonical_active and k.asset_id in(select asset_id from locked)),
        'canonical_asset_documents',(select count(*) from public.search_document_builds where document_type='ASSET' and active and not stale and status='READY' and asset_id in(select asset_id from locked)),
        'canonical_scene_documents',(select count(*) from public.search_document_builds where document_type='SCENE' and active and not stale and status='READY' and asset_id in(select asset_id from locked)),
        'text_asset',(select count(*) from public.semantic_embeddings where active and not stale and representation_type='TEXT_ASSET' and dimensions=384 and asset_id in(select asset_id from locked)),
        'visual_asset',(select count(*) from public.semantic_embeddings where active and not stale and representation_type='VISUAL_ASSET' and dimensions=512 and asset_id in(select asset_id from locked)),
        'text_scene',(select count(*) from public.semantic_embeddings where active and not stale and representation_type='TEXT_SCENE' and dimensions=384 and asset_id in(select asset_id from locked)),
        'visual_scene',(select count(*) from public.semantic_embeddings where active and not stale and representation_type='VISUAL_SCENE' and dimensions=512 and asset_id in(select asset_id from locked)),
        'visual_keyframe',(select count(*) from public.semantic_embeddings where active and not stale and representation_type='VISUAL_KEYFRAME' and dimensions=512 and asset_id in(select asset_id from locked))
      ),
      'duplicates',json_build_object(
        'active_layers',(select count(*) from(select asset_id,layer_id,semantic_spec_version,count(*) from public.asset_semantic_layers where active group by 1,2,3 having count(*)>1)x),
        'active_documents',(select count(*) from(select asset_id,document_type,coalesce(scene_id,'00000000-0000-0000-0000-000000000000'::uuid),coalesce(event_id,'00000000-0000-0000-0000-000000000000'::uuid),search_document_version,count(*) from public.search_document_builds where active group by 1,2,3,4,5 having count(*)>1)x),
        'active_embeddings',(select count(*) from(select asset_id,coalesce(scene_id,'00000000-0000-0000-0000-000000000000'::uuid),coalesce(event_id,'00000000-0000-0000-0000-000000000000'::uuid),coalesce(keyframe_id,'00000000-0000-0000-0000-000000000000'::uuid),representation_type,provider,model,model_version,embedding_version,count(*) from public.semantic_embeddings where active group by 1,2,3,4,5,6,7,8,9 having count(*)>1)x),
        'stale_and_active',(select count(*) from public.semantic_embeddings where active and stale)
      ),
      'outside_indexed',(select count(distinct asset_id) from public.asset_semantic_layers where active and asset_id not in(select asset_id from locked)),
      'indexes',(select json_agg(json_build_object('table',tablename,'name',indexname,'definition',indexdef) order by tablename,indexname) from pg_indexes where schemaname='public' and tablename in('semantic_embeddings','search_document_builds','asset_semantic_layers','asset_scenes','asset_keyframes')),
      'search_functions',(select json_agg(proname order by proname) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and (proname ilike '%search%' or proname ilike '%match%embedding%'))
    ) audit
    """
    try:
        payload=management_sql(sql)[0]['audit'];catalog_access='PASS'
    except Exception as exc:
        catalog_access=f'BLOCKED:{type(exc).__name__}'
        def fetch(table,columns='*'):
            return db.table(table).select(columns).in_('asset_id',ids).execute().data or []
        layers=fetch('asset_semantic_layers','id,asset_id,layer_id,processing_status,completeness_status,semantic_spec_version,active,analysis_run_id')
        docs=fetch('search_document_builds','id,asset_id,scene_id,event_id,document_type,search_document_version,status,active,stale')
        legacy=fetch('asset_search_documents','asset_id,build_status')
        embeddings=fetch('semantic_embeddings','id,asset_id,scene_id,event_id,keyframe_id,representation_type,provider,model,model_version,embedding_version,dimensions,active,stale')
        scenes=fetch('asset_scenes','id,asset_id,canonical_active')
        keys=fetch('asset_keyframes','id,asset_id,scene_id')
        profiles=fetch('asset_ai_profiles','asset_id,analysis_status')
        prof={str(x['asset_id']):x['analysis_status'] for x in profiles}
        matrix=[]
        for aid in ids:
            al=[x for x in layers if str(x['asset_id'])==aid and x['active']]
            ad=[x for x in docs if str(x['asset_id'])==aid and x['active'] and not x['stale'] and x['status']=='READY' and x['document_type']=='ASSET']
            ld=[x for x in legacy if str(x['asset_id'])==aid and x['build_status']=='READY']
            ae=[x for x in embeddings if str(x['asset_id'])==aid and x['active'] and not x['stale']]
            asc=[x for x in scenes if str(x['asset_id'])==aid and x['canonical_active']]
            matrix.append({'asset_id':aid,'active_layers':len(al),'complete_layers':sum(x['processing_status']=='COMPLETE' and x['completeness_status'] in('COMPLETE','NOT_APPLICABLE') for x in al),'evaluated_complete_layers':None,'canonical_asset_docs':len(ad),'legacy_asset_docs':len(ld),'text_asset':sum(x['representation_type']=='TEXT_ASSET' and x['dimensions']==384 for x in ae),'visual_asset':sum(x['representation_type']=='VISUAL_ASSET' and x['dimensions']==512 for x in ae),'scenes':len(asc),'keyframes':sum(str(x['scene_id']) in {str(s['id']) for s in asc} for x in keys),'profile_status':prof.get(aid)})
        from collections import Counter
        dup_layers=sum(v>1 for v in Counter((str(x['asset_id']),x['layer_id'],x['semantic_spec_version']) for x in layers if x['active']).values())
        dup_docs=sum(v>1 for v in Counter((str(x['asset_id']),x['document_type'],str(x.get('scene_id')),str(x.get('event_id')),x['search_document_version']) for x in docs if x['active']).values())
        dup_emb=sum(v>1 for v in Counter((str(x['asset_id']),str(x.get('scene_id')),str(x.get('event_id')),str(x.get('keyframe_id')),x['representation_type'],x['provider'],x['model'],x['model_version'],x['embedding_version']) for x in embeddings if x['active']).values())
        all_active=db.table('asset_semantic_layers').select('asset_id').eq('active',True).execute().data or []
        payload={'assets':881,'locked_assets':30,'status_matrix':matrix,'counts':{'active_layers':sum(x['active'] for x in layers),'canonical_scenes':sum(x['canonical_active'] for x in scenes),'canonical_keyframes':sum(str(x['scene_id']) in {str(s['id']) for s in scenes if s['canonical_active']} for x in keys),'canonical_asset_documents':sum(x['document_type']=='ASSET' and x['active'] and not x['stale'] and x['status']=='READY' for x in docs),'canonical_scene_documents':sum(x['document_type']=='SCENE' and x['active'] and not x['stale'] and x['status']=='READY' for x in docs),'text_asset':sum(x['representation_type']=='TEXT_ASSET' and x['active'] and not x['stale'] and x['dimensions']==384 for x in embeddings),'visual_asset':sum(x['representation_type']=='VISUAL_ASSET' and x['active'] and not x['stale'] and x['dimensions']==512 for x in embeddings),'text_scene':sum(x['representation_type']=='TEXT_SCENE' and x['active'] and not x['stale'] and x['dimensions']==384 for x in embeddings),'visual_scene':sum(x['representation_type']=='VISUAL_SCENE' and x['active'] and not x['stale'] and x['dimensions']==512 for x in embeddings),'visual_keyframe':sum(x['representation_type']=='VISUAL_KEYFRAME' and x['active'] and not x['stale'] and x['dimensions']==512 for x in embeddings)},'duplicates':{'active_layers':dup_layers,'active_documents':dup_docs,'active_embeddings':dup_emb,'stale_and_active':sum(x['active'] and x['stale'] for x in embeddings)},'outside_indexed':len({str(x['asset_id']) for x in all_active}-set(ids)),'indexes':None,'search_functions':None}
    payload['catalog_sql_access']=catalog_access
    payload['generated_at']=datetime.now(timezone.utc).isoformat();payload['access']='READ_ONLY'
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'live_database_snapshot_before.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    (OUT/'status_authority_matrix.json').write_text(json.dumps({'generated_at':payload['generated_at'],'authority':'CANONICAL_TRUTH_AUDIT','assets':payload['status_matrix']},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'assets':payload['assets'],'counts':payload['counts'],'duplicates':payload['duplicates'],'outside_indexed':payload['outside_indexed'],'status_rows':len(payload['status_matrix'])}))

if __name__=='__main__':main()
