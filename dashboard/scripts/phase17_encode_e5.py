import json,sys,os,glob,math
from sentence_transformers import SentenceTransformer
snaps=glob.glob(os.path.expanduser("~/.cache/huggingface/hub/models--intfloat--multilingual-e5-small/snapshots/*"))
if not snaps: raise RuntimeError("LOCAL_MODEL_UNAVAILABLE: intfloat/multilingual-e5-small")
snap=sorted(snaps)[-1]
model=SentenceTransformer(snap,local_files_only=True)
payload=json.load(sys.stdin)
texts=payload if isinstance(payload,list) else [payload]
vectors=model.encode(["query: "+str(x).strip() for x in texts],normalize_embeddings=True).tolist()
if any(len(v)!=384 or not all(math.isfinite(x) for x in v) for v in vectors): raise RuntimeError("INVALID_E5_VECTOR")
json.dump(vectors,sys.stdout)
