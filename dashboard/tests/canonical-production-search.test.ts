import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import path from "node:path";
import {assertEmbeddingCompatibility,CANDIDATE_RETRIEVER_VERSION} from "../db/candidate-retriever";
import {CANONICAL_SEARCH_VERSION} from "../db/canonical-production-retriever";

const root=path.resolve(process.cwd());
const identity=(representation:string,provider:string,model:string,modelVersion:string,dimension:number)=>({representation,provider,model,modelVersion,dimension,normalization:"L2"});

test("canonical version and retriever are explicit",()=>{
  assert.equal(CANONICAL_SEARCH_VERSION,"KDI_CANONICAL_SEMANTIC_SEARCH");
  assert.equal(CANDIDATE_RETRIEVER_VERSION,"kdi_candidate_retriever_v1");
});

test("E5 and OpenCLIP identities cannot be crossed",()=>{
  assert.doesNotThrow(()=>assertEmbeddingCompatibility(identity("TEXT_SCENE","sentence_transformers","intfloat/multilingual-e5-small","hf-main-pinned-runtime-v1",384),Array(384).fill(0)));
  assert.doesNotThrow(()=>assertEmbeddingCompatibility(identity("VISUAL_SCENE","open_clip","ViT-B-32","laion2b_s34b_b79k",512),Array(512).fill(0)));
  assert.throws(()=>assertEmbeddingCompatibility(identity("TEXT_SCENE","open_clip","ViT-B-32","laion2b_s34b_b79k",384),Array(384).fill(0)),/INCOMPATIBLE_EMBEDDING_IDENTITY/);
  assert.throws(()=>assertEmbeddingCompatibility(identity("VISUAL_SCENE","sentence_transformers","intfloat\/multilingual-e5-small","hf-main-pinned-runtime-v1",512),Array(512).fill(0)),/INCOMPATIBLE_EMBEDDING_IDENTITY/);
  assert.throws(()=>assertEmbeddingCompatibility(identity("TEXT_ASSET","sentence_transformers","intfloat\/multilingual-e5-small","hf-main-pinned-runtime-v1",384),Array(512).fill(0)),/QUERY_VECTOR_DIMENSION_MISMATCH/);
});

test("all production callers use the canonical orchestration",()=>{
  const ui=readFileSync(path.join(root,"app/lib/media/search.ts"),"utf8");
  // The canonical route is the production API; /api/search/v3 is now only an alias re-export.
  const api=readFileSync(path.join(root,"app/api/search/route.ts"),"utf8");
  const alias=readFileSync(path.join(root,"app/api/search/v3/route.ts"),"utf8");
  assert.match(alias,/export \{\s*POST\s*\} from "\.\.\/route"/);
  assert.match(ui,/executeCanonicalSearch/);
  assert.match(api,/executeCanonicalSearch/);
  assert.doesNotMatch(ui,/liveRest\("rpc\/hybrid_search_assets_v3"/);
  assert.doesNotMatch(api,/retrieveCandidates\(|rerankAuthorizedCandidates\(/);
});

test("canonical retrieval uses an unversioned production RPC authority",()=>{
  const retriever=readFileSync(path.join(root,"db/candidate-retriever.ts"),"utf8");
  assert.match(retriever,/db\.rpc\("match_kdi_semantic_search_embeddings"/);
  assert.doesNotMatch(retriever,/match_kdi_search_v\d+_embeddings/);
});

test("canonical E5 encoder applies the required query prefix",()=>{
  const encoder=readFileSync(path.join(root,"scripts/phase17_encode_e5.py"),"utf8");
  assert.match(encoder,/"query: "\+str\(x\)\.strip\(\)/);
  assert.match(encoder,/normalize_embeddings=True/);
});
