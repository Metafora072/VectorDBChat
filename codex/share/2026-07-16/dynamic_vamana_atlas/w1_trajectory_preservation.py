#!/usr/bin/env python3
"""Recheck frozen CP01/formal inputs after preparation or a failed stage."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(8<<20),b""): h.update(b)
 return h.hexdigest()
def main()->None:
 p=argparse.ArgumentParser(); p.add_argument("--preflight",type=Path,required=True); p.add_argument("--cp01",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
 if a.output.exists(): raise SystemExit("trajectory preservation overwrite refused")
 pre=json.loads(a.preflight.read_text()); mismatches=[]
 for name,expected in pre["cp01_artifacts"].items():
  path=a.cp01/name; st=path.stat(); actual={"size_bytes":st.st_size,"sha256":sha(path),"mtime_ns":st.st_mtime_ns}
  if actual!=expected: mismatches.append({"artifact":str(path),"expected":expected,"actual":actual})
 for name,expected in pre["formal_inputs"].items():
  path=Path(expected["realpath"]); st=path.stat(); actual={"size_bytes":st.st_size,"sha256":sha(path),"mtime_ns":st.st_mtime_ns}
  if actual!={k:expected[k] for k in actual}: mismatches.append({"artifact":str(path),"expected":expected,"actual":actual})
 report={"schema":"dynamic-vamana-w1-trajectory-preservation-v1","status":"pass" if not mismatches else "fail","mismatches":mismatches}
 a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(report,indent=2)+"\n")
 if mismatches: raise SystemExit("frozen trajectory inputs changed")
if __name__=="__main__": main()
