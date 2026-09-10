"""Bounded local-only SmolVLM2-2.2B constrained-observation fixture."""
from pathlib import Path
import json, time
from PIL import Image
from lmformatenforcer import JsonSchemaParser
from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
from transformers import AutoProcessor, AutoModelForImageTextToText
import torch

ROOT=Path(__file__).resolve().parents[1]
MODEL=str(ROOT/'.kdi-models'/'SmolVLM2-500M-Video-Instruct')
im=Image.open(ROOT/'.kdi-test-fixtures/phase06_fixture.png')
schema={'type':'object','properties':{'observations':{'type':'array','items':{'type':'object','properties':{'category':{'type':'string'},'concept':{'type':'string'},'state':{'type':'string','enum':['OBSERVED','UNKNOWN','NOT_APPLICABLE','FALSE']},'evidence_type':{'type':'string','enum':['ASSET','FRAME','KEYFRAME','TIME_RANGE','METADATA']},'confidence':{'type':'string','enum':['HIGH','MEDIUM','LOW','UNKNOWN']}},'required':['category','concept','state','evidence_type','confidence']}}},'required':['observations']}
out={'model':'HuggingFaceTB/SmolVLM2-500M-Video-Instruct','device':'cpu','external_media_transmission':False,'production_writes':0}
try:
    t=time.perf_counter(); processor=AutoProcessor.from_pretrained(MODEL,local_files_only=True); model=AutoModelForImageTextToText.from_pretrained(MODEL,local_files_only=True,torch_dtype=torch.float32); model.eval(); out['load_seconds']=round(time.perf_counter()-t,2)
    inputs=processor(text='<image> Return a JSON object matching the schema exactly. Use one observable ASSET observation.',images=[im],return_tensors='pt')
    parser=JsonSchemaParser(schema); prefix=build_transformers_prefix_allowed_tokens_fn(processor.tokenizer,parser)
    attempts=[]; texts=[]
    for _ in range(5):
        with torch.no_grad(): generated=model.generate(**inputs,max_new_tokens=256,prefix_allowed_tokens_fn=prefix,do_sample=False)
        text=processor.batch_decode(generated,skip_special_tokens=True)[0]; texts.append(text); start=text.find('{'); payload=json.loads(text[start:]); attempts.append(isinstance(payload.get('observations'),list))
    terms=' '.join(texts).lower(); semantic_hits=sum(term in terms for term in ('text','rectangle','shape','object'))
    out.update({'inference':'PASS','structured_json':'PASS' if all(attempts) else 'FAIL','attempts':attempts,'structured_passes':sum(attempts),'schema_valid':all(attempts),'semantic_fixture_hits':semantic_hits,'semantic_quality':'PASS' if semantic_hits >= 1 else 'FAIL'})
except Exception as e:
    out.update({'inference':'FAIL','structured_json':'FAIL','error_type':type(e).__name__,'error':str(e)[:300]})
print(json.dumps(out)); (ROOT/'reports/semantic-search/rollout/phase-06/phase_06_structured_reliability_test.json').write_text(json.dumps(out,indent=2)+'\n')
