from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from .openclip_encoder import OpenClipEncoder, MODEL_PROVIDER, MODEL_NAME, MODEL_VERSION, DIMENSIONS

app = FastAPI(docs_url=None, redoc_url=None)
encoder: OpenClipEncoder | None = None
def get_encoder():
    global encoder
    if encoder is None: encoder = OpenClipEncoder()
    return encoder
class TextRequest(BaseModel): text: str = Field(min_length=1,max_length=300)
@app.get("/health")
def health(): return {"status":"ok","provider":MODEL_PROVIDER,"model":MODEL_NAME,"version":MODEL_VERSION,"dimensions":DIMENSIONS,"device":"cpu"}
@app.post("/embed-text")
def embed_text(request: TextRequest):
    try: values=get_encoder().embed_text(request.text)
    except Exception as exc: raise HTTPException(500,"local embedding failed") from exc
    return {"provider":MODEL_PROVIDER,"model":MODEL_NAME,"version":MODEL_VERSION,"dimensions":DIMENSIONS,"embedding":values}
