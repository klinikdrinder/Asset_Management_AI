"""Build human-review JSON/Markdown/CSV from the frozen triage manifest."""
from __future__ import annotations
import csv, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'reports/semantic-search/rollout/100'; SRC=OUT/'privacy-approval-required.json'
def main():
    source=json.loads(SRC.read_text(encoding='utf-8')); assets=source['assets']
    detailed=[]
    for x in assets:
        detailed.append({**x, 'patient_context': 'NOT_DETERMINED_LOCALLY', 'procedure_context': 'NOT_DETERMINED_LOCALLY', 'sensitive_text': 'NOT_EVALUATED_LOCALLY', 'visual_sampling_status': 'NOT_COMPLETED_LOCAL_MODEL_RUNTIME', 'privacy_rationale': 'Checksum-verified local technical inspection completed; deep visual privacy classification was not completed because the cached local SmolVLM runtime is CPU-only and did not complete the first multi-frame asset within the bounded run.', 'recommended_review_action':'HUMAN_REVIEW_FOR_EXTERNAL_AI'})
    packet={'status':'READY_FOR_HUMAN_APPROVAL','manifest_id':'kdi_semantic_rollout_100_v1','range':'#31-#130','rows':100,'local_model':'SmolVLM2-256M-Video-Instruct (cached; CPU-only runtime blocker)','external_ai_calls':0,'local_visual_sampling_completed':0,'local_classification_failures':100,'groups':{'GROUP_A_LIKELY_NON_CLINICAL':[],'GROUP_B_POTENTIALLY_CLINICAL':[],'GROUP_C_CLINICAL':[],'GROUP_D_UNCERTAIN':[x['ordinal'] for x in detailed]},'assets':detailed}
    (OUT/'privacy-review-detailed.json').write_text(json.dumps(packet,indent=2)+'\n',encoding='utf-8')
    md=['# KDI 100-Asset Privacy Review','',f"Status: **READY_FOR_HUMAN_APPROVAL**",'', 'Local visual model sampling was attempted but could not complete within the bounded CPU runtime. No external AI was called.', '', '| Ordinal | Filename | Classification | Confidence | Patient context | Procedure context | Sensitive text | Current external AI | Recommended action |','|---:|---|---|---|---|---|---|---|---|']
    md += [f"| {x['ordinal']} | {x['filename']} | UNCERTAIN | LOW | NOT_DETERMINED_LOCALLY | NOT_DETERMINED_LOCALLY | NOT_EVALUATED_LOCALLY | {x.get('external_ai_status')} | HUMAN_REVIEW_FOR_EXTERNAL_AI |" for x in detailed]
    (OUT/'privacy-review-detailed.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    fields=['ordinal','asset_id','filename','local_classification','confidence','patient_context','procedure_context','sensitive_text','external_ai_current','human_decision','reviewer','reviewed_at','notes']
    with (OUT/'privacy-approval-worksheet.csv').open('w',newline='',encoding='utf-8') as fh:
        writer=csv.DictWriter(fh,fieldnames=fields); writer.writeheader()
        for x in detailed: writer.writerow({'ordinal':x['ordinal'],'asset_id':x['asset_id'],'filename':x['filename'],'local_classification':'UNCERTAIN','confidence':'LOW','patient_context':'NOT_DETERMINED_LOCALLY','procedure_context':'NOT_DETERMINED_LOCALLY','sensitive_text':'NOT_EVALUATED_LOCALLY','external_ai_current':x.get('external_ai_status'),'human_decision':'','reviewer':'','reviewed_at':'','notes':'Await bounded local visual runtime or human review'})
    print(json.dumps({'status':'PASS','rows':100,'external_ai_calls':0,'visual_sampling_completed':0}))
if __name__=='__main__': main()
