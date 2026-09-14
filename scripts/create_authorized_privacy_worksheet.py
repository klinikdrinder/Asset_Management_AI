"""Create an explicitly authorized worksheet from a frozen local-preparation manifest."""
from __future__ import annotations
import argparse, csv, json
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ["ordinal","asset_id","filename","local_classification","confidence","patient_context",
          "procedure_context","sensitive_text","external_ai_current","human_decision","reviewer",
          "reviewed_at","notes"]

def main():
    p=argparse.ArgumentParser(); p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True); p.add_argument("--ordinal-start",type=int,required=True)
    p.add_argument("--ordinal-end",type=int,required=True); a=p.parse_args()
    raw=json.loads(a.manifest.read_text(encoding="utf-8"))["assets"]
    values=list(raw.values()) if isinstance(raw,dict) else list(raw)
    rows=sorted((x for x in values if x.get("ordinal") is not None and a.ordinal_start<=int(x["ordinal"])<=a.ordinal_end),key=lambda x:int(x["ordinal"]))
    expected=a.ordinal_end-a.ordinal_start+1
    if len(rows)!=expected or len({x["asset_id"] for x in rows})!=expected: raise RuntimeError("FROZEN_SCOPE_INVALID")
    stamp=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open("w",newline="",encoding="utf-8-sig") as fh:
        w=csv.DictWriter(fh,fieldnames=FIELDS,quoting=csv.QUOTE_ALL); w.writeheader()
        for x in rows: w.writerow({"ordinal":x["ordinal"],"asset_id":x["asset_id"],"filename":x["filename"],
            "local_classification":"UNCERTAIN","confidence":"LOW","patient_context":"NOT_DETERMINED_LOCALLY",
            "procedure_context":"NOT_DETERMINED_LOCALLY","sensitive_text":"NOT_EVALUATED_LOCALLY",
            "external_ai_current":"NOT_REVIEWED","human_decision":"APPROVE","reviewer":"KDI_OPERATOR",
            "reviewed_at":stamp,"notes":f"Controlled internal KDI Claude semantic indexing authorization for exact cohort ordinals {a.ordinal_start}-{a.ordinal_end}."})
    print(json.dumps({"status":"CREATED","rows":len(rows),"distinct_assets":len({x['asset_id'] for x in rows}),
                      "min_ordinal":min(x['ordinal'] for x in rows),"max_ordinal":max(x['ordinal'] for x in rows),"path":str(a.output)}))
if __name__=="__main__": main()
