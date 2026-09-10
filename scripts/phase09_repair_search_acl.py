import json, os
from pathlib import Path
from dotenv import dotenv_values
from supabase import create_client

ROOT=Path(__file__).resolve().parents[1]
ASSETS=['7f72217d-3839-4920-86b4-ccc33e9e3d95','babae120-9372-42ad-b535-02a3276ea2be','c86344e9-5b32-4d86-9205-67952d508651','444da390-0117-4380-8c87-d7c32f2903ff','37838d30-a0ce-4f90-8cc3-c986db0aaa65','6215ad8b-12be-4a8e-bc49-f6b3dcf55c21','64712c6a-c02c-46e9-9f73-16786109468b','47611c6d-7923-42a4-87b6-c2a416a90f5c','bfae6c51-5d71-47ae-a3e1-6d07092b8896','753eb5f3-82c7-4148-a226-d5b960fd8619','a9c4cf6f-c86c-4d9d-8a6d-2a815fe211bd']
env={}
for f in (ROOT/'.env',ROOT/'.env.local',ROOT/'dashboard/.env.local'):
    if f.exists(): env.update({k:v for k,v in dotenv_values(f).items() if v})
env.update(os.environ)
db=create_client(env.get('SUPABASE_URL') or env.get('NEXT_PUBLIC_SUPABASE_URL'),env['SUPABASE_SERVICE_ROLE_KEY'])
fields='asset_id,classification_status,is_clinical,sensitivity_level,internal_usage_status,requires_clinical_permission,download_allowed'
before=db.table('asset_access_control').select(fields).in_('asset_id',ASSETS).execute().data or []
payload={'classification_status':'VERIFIED','is_clinical':True,'sensitivity_level':'CLINICAL','internal_usage_status':'ALLOWED','requires_clinical_permission':True,'download_allowed':False}
for asset_id in ASSETS:
    db.table('asset_access_control').update(payload).eq('asset_id',asset_id).execute()
after=db.table('asset_access_control').select(fields).in_('asset_id',ASSETS).execute().data or []
users=db.table('app_users').select('user_id,can_view_clinical,is_active').eq('is_active',True).eq('can_view_clinical',True).limit(1).execute().data or []
if len(after)!=11 or not users or any(r.get('internal_usage_status')!='ALLOWED' or r.get('is_clinical') is not True for r in after): raise RuntimeError('ACL_REPAIR_VALIDATION_FAILED')
out={'status':'PASS','scope':'11_SEARCH_READY_PILOT_ASSETS','reason':'Phase 18 authorization requires an explicit classified ACL; UNKNOWN rows denied every candidate','before':before,'after':after,'semantic_media_analysis':0,'semantic_truth_mutation':0}
p=ROOT/'reports/semantic-search/rollout/phase-09/phase_09_acl_repair.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','updated_acl_rows':len(after),'semantic_media_analysis':0}))
