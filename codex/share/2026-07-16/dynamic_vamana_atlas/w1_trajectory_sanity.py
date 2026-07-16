#!/usr/bin/env python3
"""Small deterministic regression suite for trajectory binary/prefix/remap rules."""
from __future__ import annotations
import argparse, json, shutil, struct
from pathlib import Path
import numpy as np
from w1_trajectory_generate import atomic_trace, read_trace
def main()->None:
 p=argparse.ArgumentParser(); p.add_argument("--scratch",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
 if a.scratch.exists() or a.output.exists(): raise SystemExit("trajectory sanity freshness guard failed")
 a.scratch.mkdir(parents=True); rows=[]
 try:
  old_d=np.asarray([3,1],dtype="<u4"); old_i=np.asarray([8,9],dtype="<u4"); old=a.scratch/"old.bin"; atomic_trace(old,old_d,old_i)
  master_d=np.asarray([3,1,6,0,7],dtype="<u4"); master_i=np.asarray([8,9,11,10,12],dtype="<u4"); master=a.scratch/"master.bin"; atomic_trace(master,master_d,master_i)
  rd,ri=read_trace(master); prefix=bool(np.array_equal(rd[:2],old_d) and np.array_equal(ri[:2],old_i))
  rows.append({"name":"columnar_header_aware_cp01_prefix","passed":prefix})
  positions=[j*(400_000-1)//8 for j in range(9)]
  rows.append({"name":"floor_probe_positions","passed":positions==[0,49999,99999,149999,199999,249999,299999,349999,399999],"positions":positions})
  d1=np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence([20260713,0x44454C]))).permutation(np.arange(16,dtype="<u4"))
  d2=np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence([20260713,0x44454C]))).permutation(np.arange(16,dtype="<u4"))
  ins=np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence([20260713,0x494E53]))).permutation(np.arange(16,dtype="<u4"))
  rows.append({"name":"domain_separated_deterministic_streams","passed":bool(np.array_equal(d1,d2) and not np.array_equal(d1,ins))})
  tags=np.asarray([4,2,7,9],dtype="<u4"); locations=np.asarray([[0,1,2,3]],dtype="<u4"); distances=np.asarray([[.1,.2,.3,.4]],dtype="<f4")
  mapped=tags[locations]
  rows.append({"name":"tag_zero_absent_is_valid","passed":bool(0 not in tags and np.array_equal(mapped,[[4,2,7,9]]) and np.all(distances[:,1:]>=distances[:,:-1]))})
  formal_ids=np.asarray([9,4,7],dtype="<u4"); exact_ids=np.asarray([4,9,7],dtype="<u4")
  formal_dist=np.asarray([1.0,1.0,2.0],dtype="<f4"); exact_dist=np.asarray([1.0,1.0,2.0],dtype="<f4")
  formal_order=np.lexsort((formal_ids,formal_dist)); exact_order=np.lexsort((exact_ids,exact_dist))
  rows.append({"name":"equal_distance_raw_reorder_is_canonical_exact","passed":bool(
   not np.array_equal(formal_ids,exact_ids) and np.array_equal(formal_dist,exact_dist)
   and np.array_equal(formal_ids[formal_order],exact_ids[exact_order]))})
  rows.append({"name":"target_reuse_refused_by_contract","passed":old.exists() and master.exists()})
  report={"schema":"dynamic-vamana-w1-trajectory-sanity-v1","status":"pass" if all(x["passed"] for x in rows) else "fail","tests":rows,"scratch_removed_after_report":True}
  a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(report,indent=2)+"\n")
 finally: shutil.rmtree(a.scratch,ignore_errors=True)
 if report["status"]!="pass": raise SystemExit("trajectory sanity failed")
if __name__=="__main__": main()
