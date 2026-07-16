#!/usr/bin/env python3
"""Exact-identity and execution-invariant W1 pre-update gate v2."""
from __future__ import annotations
import argparse, hashlib, json, math, re, statistics, struct
from pathlib import Path
import numpy as np

def sha(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for b in iter(lambda:f.read(8<<20),b""): h.update(b)
 return h.hexdigest()
def load(p): return json.loads(Path(p).read_text())
def io_delta(d,dev):
 s=d.get("samples",[])
 def row(x): return next((z for z in x.get("cgroup_io_stat",[]) if z.get("device")==dev),{})
 if not s:return 0
 a,b=row(s[0]),row(s[-1]); return int(b.get("rbytes",0))-int(a.get("rbytes",0))
def main():
 p=argparse.ArgumentParser(); p.add_argument("--system",required=True,choices=("DGAI","OdinANN")); p.add_argument("--mode",required=True)
 for x in ("result-dir","binary","driver","artifact-manifest","base-manifest","clone-manifest","query","gt","active-tags","ls","io-engine","device","output"): p.add_argument("--"+x,required=True)
 p.add_argument("--threads",type=int,required=True); a=p.parse_args(); rd=Path(a.result_dir); art=load(a.artifact_manifest); sys=art["systems"][a.system]
 assert a.mode=="formal" and a.threads==1 and a.io_engine==sys["io_engine"] and a.device=="259:10"
 assert sha(a.binary)==sys["binary_sha256"]["search_disk_index"] and sha(a.driver)==sys["binary_sha256"]["w1_canary"]
 assert sha(a.query)==art["formal_inputs"]["query"]["sha256"] and sha(a.gt)==art["formal_inputs"]["gt_cp00"]["sha256"]
 assert sha(a.base_manifest)==sha(a.clone_manifest)==sys["formal_base"]["manifest_sha256"]
 ntag,d=struct.unpack("<II",Path(a.active_tags).read_bytes()[:8]); assert (ntag,d)==(8_000_000,1)
 active=np.memmap(a.active_tags,dtype="<u4",mode="r",offset=8,shape=(ntag,)); active_sha=sha(a.active_tags)
 expected_active="fb9d35876d863963f6809e827e38c86d418c7e56c5beef7e49d9fe2614eacb99"; assert active_sha==expected_active
 active_set=set(map(int,np.asarray(active)))
 rows=[]; bad=re.compile(r"fatal|assert|EBADF|negative CQE|I/O error",re.I)
 for L in map(int,a.ls.split(",")):
  for rep in (1,2,3):
   stem=rd/f"pre_cp00_L{L}_r{rep}"; path=lambda suffix: Path(str(stem)+suffix)
   metrics=load(path(".metrics.json")); valid=load(path(".validation.json")); res=load(path(".resources.json")); log=path(".log").read_text(errors="replace")
   raw=path(".result_ids.bin").read_bytes(); nq,k=struct.unpack("<II",raw[:8]); assert (nq,k)==(10000,10) and len(raw)==8+nq*k*4
   ids=np.frombuffer(raw,dtype="<u4",offset=8).reshape(nq,k); assert not np.any(ids==np.uint32(0xffffffff))
   assert all(len(set(map(int,row)))==10 for row in ids) and all(int(x) in active_set for x in ids.ravel())
   required=("qps","mean_latency_us","p50_latency_us","p95_latency_us","p99_latency_us","mean_ios","recall_at_10_percent")
   assert all(math.isfinite(float(metrics[x])) for x in required) and valid.get("all_result_ids_active") is True and 0<=float(valid["recall_at_10_normalized"])<=1
   assert res.get("returncode")==0 and io_delta(res,a.device)>0 and not any(int(x.get("cgroup_memory_events",{}).get(y,0)) for x in res.get("samples",[]) for y in ("oom","oom_kill"))
   assert not bad.search(log)
   actual=[int(x) for x in re.findall(r"(?:^|\s)(\d+)\s+\d+(?:\.\d+)?\s+\d+(?:\.\d+)?\s+\d+(?:\.\d+)?",log,re.M)]; assert L in actual
   rows.append({"L":L,"repeat":rep,"recall_at_10":float(metrics["recall_at_10_percent"])/100,"qps":float(metrics["qps"]),"p99_latency_us":float(metrics["p99_latency_us"]),"nvme_read_bytes":io_delta(res,a.device),"ids_sha256":sha(path(".result_ids.bin")),"ids":ids})
 outrows=[]
 for L in map(int,a.ls.split(",")):
  xs=[x for x in rows if x["L"]==L]; pairs=[]
  for i in range(3):
   for j in range(i+1,3):
    exact=float(np.mean(np.all(xs[i]["ids"]==xs[j]["ids"],axis=1))); overlap=float(np.mean([len(set(map(int,xs[i]["ids"][q]))&set(map(int,xs[j]["ids"][q])))/10 for q in range(10000)])); pairs.append({"runs":[i+1,j+1],"top10_exact_row_rate":exact,"slot_overlap":overlap})
  outrows.append({"L":L,"recall":{"median":statistics.median(x["recall_at_10"] for x in xs),"min":min(x["recall_at_10"] for x in xs),"max":max(x["recall_at_10"] for x in xs)},"qps_median":statistics.median(x["qps"] for x in xs),"p99_us_median":statistics.median(x["p99_latency_us"] for x in xs),"pairwise":pairs,"runs":[{k:v for k,v in x.items() if k!="ids"} for x in xs]})
 if len(outrows)>1 and outrows[-1]["recall"]["median"]<outrows[0]["recall"]["median"]: raise SystemExit("high-L recall dominance inversion; audit required")
 report={"schema":"dynamic-vamana-w1-preupdate-identity-v2","status":"pass","system":a.system,"identities":{"query_binary_sha256":sha(a.binary),"driver_sha256":sha(a.driver),"base_index_manifest_sha256":sha(a.base_manifest),"clone_initial_content_manifest_sha256":sha(a.clone_manifest),"query_sha256":sha(a.query),"cp00_gt_sha256":sha(a.gt),"cp00_active_tags_sha256":active_sha,"threads":a.threads,"io_engine":a.io_engine,"device":a.device},"points":outrows,"recall_is_diagnostic_only":True}
 Path(a.output).write_text(json.dumps(report,indent=2)+"\n")
if __name__=="__main__": main()
