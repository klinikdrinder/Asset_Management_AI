"""Local-only SmolVLM fixture test; generates non-sensitive synthetic media."""
from pathlib import Path
import json, time
from PIL import Image, ImageDraw
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
FIX=ROOT/'.kdi-test-fixtures'; FIX.mkdir(exist_ok=True)
img_path=FIX/'phase06_fixture.png'; video_path=FIX/'phase06_fixture.mp4'
im=Image.new('RGB',(320,240),'white'); d=ImageDraw.Draw(im); d.rectangle((40,40,280,200),outline='blue',width=5); d.text((80,105),'KDI TEST',fill='black'); im.save(img_path)
out=cv2.VideoWriter(str(video_path),cv2.VideoWriter_fourcc(*'mp4v'),5,(320,240))
for i in range(10):
    frame=np.full((240,320,3),255,np.uint8); cv2.rectangle(frame,(40+i*3,40),(280,200),(255,0,0),3); cv2.putText(frame,'KDI TEST',(80,125),cv2.FONT_HERSHEY_SIMPLEX,1,(0,0,0),2); out.write(frame)
out.release()
result={'model':'HuggingFaceTB/SmolVLM2-256M-Video-Instruct','fixture_media_created':True,'external_media_transmission':False,'production_writes':0}
try:
    from transformers import AutoProcessor, AutoModelForImageTextToText
    import torch
    model_dir=str(ROOT/'.kdi-models'/'SmolVLM2-256M-Video-Instruct')
    t=time.perf_counter(); processor=AutoProcessor.from_pretrained(model_dir,local_files_only=True); model=AutoModelForImageTextToText.from_pretrained(model_dir,local_files_only=True,torch_dtype=torch.float32); model.eval()
    result.update({'model_load':'PASS','load_seconds':round(time.perf_counter()-t,2),'device':'cpu'})
    inputs=processor(text='<image> Describe this non-sensitive test image in one short sentence.',images=[im],return_tensors='pt')
    with torch.no_grad(): generated=model.generate(**inputs,max_new_tokens=32)
    result.update({'image_inference':'PASS','image_output_chars':len(processor.batch_decode(generated,skip_special_tokens=True)[0])})
    cap=cv2.VideoCapture(str(video_path)); frames=[]; timestamps=[]
    for idx in (0,4,8):
        cap.set(cv2.CAP_PROP_POS_FRAMES,idx); ok,fr=cap.read()
        if ok:
            frames.append(Image.fromarray(cv2.cvtColor(fr,cv2.COLOR_BGR2RGB))); timestamps.append(int(cap.get(cv2.CAP_PROP_POS_MSEC)))
    cap.release()
    video_prompt=' '.join(['<image>']*len(frames))+' Describe these ordered video keyframes and mention their temporal order.'
    vin=processor(text=video_prompt,images=frames,return_tensors='pt')
    with torch.no_grad(): vg=model.generate(**vin,max_new_tokens=48)
    result.update({'video_decode':'PASS','keyframes':len(frames),'timestamps_ms':timestamps,'video_inference':'PASS','video_output_chars':len(processor.batch_decode(vg,skip_special_tokens=True)[0])})
except Exception as exc:
    result.update({'model_load':'FAIL','image_inference':'FAIL','error_type':type(exc).__name__,'error':str(exc)[:240]})
print(json.dumps(result))
(ROOT/'reports/semantic-search/rollout/phase-06/phase_06_local_model_fixture_test.json').write_text(json.dumps(result,indent=2)+'\n')
