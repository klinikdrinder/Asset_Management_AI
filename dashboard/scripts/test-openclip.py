from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import math, tempfile
from PIL import Image
from visual_indexing.openclip_encoder import OpenClipEncoder, DIMENSIONS, MODEL_NAME, MODEL_VERSION

model=OpenClipEncoder()
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/"test.png"; Image.new("RGB",(224,224),(120,160,200)).save(path)
    image=model.embed_image(path); text=model.embed_text("a pale blue test image")
cosine=sum(a*b for a,b in zip(image,text))
assert len(image)==len(text)==DIMENSIONS and all(math.isfinite(x) for x in image+text)
assert abs(sum(x*x for x in image)-1)<1e-4 and math.isfinite(cosine)
print(f"model={MODEL_NAME} pretrained={MODEL_VERSION} dimensions={DIMENSIONS} device=cpu cosine={cosine:.6f} PASS")
