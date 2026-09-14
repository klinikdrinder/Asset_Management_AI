import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
const ROOT=resolve(import.meta.dirname,"../..");
const cases:any[]=[];
const templates=[
  (i:number)=>({query:`Find a doctor for frontal hairline design ${i}`,requirements:[{code:"CLINICIAN",class:"STRONG_REQUIREMENT",allowed:["doctor","physician","clinician"]},{code:"FRONTAL_HAIRLINE",class:"STRONG_REQUIREMENT",allowed:["frontal hairline","front hairline","frontal hair line","front hair line"]},{code:"DRAWING_HAIRLINE",class:"STRONG_REQUIREMENT",allowed:["hairline drawing","drawing hairline","hairline design","hairline planning","hairline marking"]}]}),
  (i:number)=>({query:`Only frontal hairline images ${i}`,requirements:[{code:"FRONTAL_HAIRLINE",class:"HARD_CONSTRAINT",allowed:["frontal hairline","front hairline","frontal hair line","front hair line"]}]}),
  (i:number)=>({query:`Exclude injection footage ${i}`,requirements:[{code:"INJECTING",class:"HARD_EXCLUSION",allowed:["injecting","injection","inject","syringe injection"]}]}),
  (i:number)=>({query:`Prefer frontal hairline planning ${i}`,requirements:[{code:"FRONTAL_HAIRLINE",class:"PREFERENCE",allowed:["frontal hairline","front hairline","frontal hair line","front hair line","hairline"]}]}),
  (i:number)=>({query:`If possible avoid injection scenes ${i}`,requirements:[{code:"INJECTING",class:"NEGATIVE_PREFERENCE",allowed:["injecting","injection","inject","syringe injection"]}]}),
  (i:number)=>({query:`Show M-CURE visible on screen ${i}`,requirements:[{field:"OCR_LITERAL",class:"STRONG_REQUIREMENT",literal:"M-CURE"}]}),
  (i:number)=>({query:`Show videos with delta resonance ${i}`,requirements:[{field:"UNRESOLVED",class:"UNRESOLVED",literal:"delta resonance"}]}),
  (i:number)=>({query:`Show frontal scalp procedure ${i}`,requirements:[{code:"FRONTAL_SCALP",class:"STRONG_REQUIREMENT",allowed:["frontal scalp","front scalp","scalp"]}]}),
  (i:number)=>({query:`Show hair transplant, not graft implantation ${i}`,requirements:[{code:"HAIR_TRANSPLANT",class:"STRONG_REQUIREMENT",allowed:["hair transplant","hair transplantation","transplant"]},{code:"IMPLANTING_GRAFTS",class:"HARD_EXCLUSION",allowed:["graft implantation","implanting grafts","implantation of grafts","graft placement"]}]}),
  (i:number)=>({query:`Only videos but exclude injecting ${i}`,requirements:[{field:"MEDIA_TYPE",class:"HARD_CONSTRAINT",allowed:["video"]},{code:"INJECTING",class:"HARD_EXCLUSION",allowed:["injecting","injection","inject","syringe injection"]}]})
];
for(let i=0;i<180;i++)cases.push({id:`QX16-${String(i+1).padStart(3,"0")}`,split:i<120?"DEV":i<150?"VALIDATION":"BLIND",language:"ENGLISH",...templates[i%templates.length](i+1)});
const out={benchmark_version:"kdi_query_expansion_benchmark_v1",language:"ENGLISH",splits:{dev:120,validation:30,blind:30},cases};
const fp=createHash("sha256").update(JSON.stringify(out)).digest("hex");
await mkdir(resolve(ROOT,"config/semantic-search/benchmarks"),{recursive:true}); await writeFile(resolve(ROOT,"config/semantic-search/benchmarks/kdi_query_expansion_benchmark_v1.json"),JSON.stringify({...out,fingerprint:fp},null,2)); console.log(JSON.stringify({fingerprint:fp,cases:180}));
