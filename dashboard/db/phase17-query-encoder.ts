import {spawn} from "node:child_process";
import {resolve} from "node:path";

// `import.meta.dirname` is not preserved when this server module is bundled by Next/Turbopack and
// caused production builds to fail during page-data collection. The dashboard launchers establish
// the dashboard as cwd, so resolve the two controlled local paths from that stable boundary.
const dashboardRoot=process.cwd();
const PYTHON=resolve(dashboardRoot,"../.venv/Scripts/python.exe");
const scripts=resolve(dashboardRoot,"scripts");

async function encode(script:string,texts:string[],dimension:number,timeout=180_000){
  const clean=texts.map(text=>text.replace(/\s+/g," ").trim().slice(0,300));
  if(!clean.length||clean.some(x=>!x))throw new Error("QUERY_EMBEDDING_EMPTY_TEXT");
  let stdout:string;
  try{stdout=await new Promise<string>((resolveOutput,reject)=>{const child=spawn(PYTHON,[resolve(scripts,script)],{windowsHide:true,stdio:["pipe","pipe","pipe"]});let out="",err="";const timer=setTimeout(()=>{child.kill();reject(Object.assign(new Error("TIMEOUT"),{killed:true}))},timeout);child.stdout.setEncoding("utf8").on("data",x=>{out+=x;if(out.length>8_000_000){child.kill();reject(new Error("OUTPUT_LIMIT"))}});child.stderr.setEncoding("utf8").on("data",x=>err+=x);child.on("error",reject);child.on("close",code=>{clearTimeout(timer);code===0?resolveOutput(out):reject(new Error(err||`exit ${code}`))});child.stdin.end(JSON.stringify(clean))});}
  catch(error:any){throw new Error(`QUERY_ENCODER_FAILED:${script}:${error?.killed?"TIMEOUT":error?.message??error}`)}
  const vectors=JSON.parse(stdout);
  if(!Array.isArray(vectors)||vectors.length!==clean.length||vectors.some((vector:any)=>!Array.isArray(vector)||vector.length!==dimension||vector.some((x:any)=>!Number.isFinite(x))))throw new Error(`QUERY_ENCODER_DIMENSION_MISMATCH:${dimension}`);
  return vectors as number[][];
}

export async function encodePhase17Queries(texts:string[]){
  const started=performance.now();
  // Loading both CPU model families concurrently causes severe memory/BLAS
  // contention on the provisioned search host. Sequential cold starts are
  // deterministic; production workers can keep each encoder warm separately.
  const e5=await encode("phase17_encode_e5.py",texts,384,120_000);
  const openclip=await encode("phase17_encode_openclip.py",texts,512,180_000);
  const provenance={
    e5:{provider:"sentence_transformers",model:"intfloat/multilingual-e5-small",dimension:384,preprocessing:"query: prefix + L2 normalization"},
    openclip:{provider:"open_clip",model:"ViT-B-32",checkpoint:"laion2b_s34b_b79k",dimension:512,preprocessing:"OpenCLIP tokenizer + L2 normalization"},
    elapsed_ms:performance.now()-started,
  };
  return texts.map((_,i)=>({text:e5[i],visual:openclip[i],provenance}));
}

export async function encodePhase17Query(text:string){return (await encodePhase17Queries([text]))[0]}
