import json,sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from visual_indexing.openclip_encoder import OpenClipEncoder
enc=OpenClipEncoder(); payload=json.load(sys.stdin); texts=payload if isinstance(payload,list) else [payload]
json.dump([enc.embed_text(str(x).strip()) for x in texts],sys.stdout)
