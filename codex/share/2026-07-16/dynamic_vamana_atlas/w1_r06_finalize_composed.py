#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime,json,re,statistics
from pathlib import Path
def load(p):return json.loads(Path(p).read_text())
def points(d):
 out=[]
 for p in sorted(Path(d).glob("*_L*_r*.metrics.json")):
  m=re.fullmatch(r"(pre_cp00|post_cp01)_L(\d+)_r(\d+)\.metrics\.json",p.name)
  if m:
   v=load(p.with_name(p.name.replace(".metrics.json",".validation.json"))); q=load(p); out.append((m.group(1),int(m.group(2)),int(m.group(3)),float(v["recall_at_10_normalized"]),float(q["qps"]),float(q["p99_latency_us"])))
 return out
p=argparse.ArgumentParser(); p.add_argument("--root",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args(); r=a.root
r05=r/"results/pilot3_sift10m_w1_r05/DGAI/cp01-05"; r06=r/"results/pilot3_sift10m_w1_r06"; od=r06/"OdinANN/cp01-06"; disk=r06/"DiskANN/stale-cp00-06"
for x in (r05/"FORMAL_W1_CANARY_OK",od/"FORMAL_W1_CANARY_OK",disk/"DISKANN_STALE_CONTROL_OK",r06/"preflight/r05_dgai_freeze.json"): assert x.exists()
can={"DGAI":load(r05/"canary.json"),"OdinANN":load(od/"canary.json")}; qs={"DGAI":points(r05),"OdinANN":points(od)}; stale=load(disk/"stale_control.json")
lines=["# Composed W1 1% Canary Result","","## 结论","","本报告组合 R05 DGAI、R06 OdinANN、R06 DiskANN stale control 与 R02 checkpoint-1 GT。它们是经冻结身份连接的独立有效证据，**不是同一个无中断 attempt**；结果只支持 W1 1% replace-new canary，不进入更高 churn。","","## Dynamic update","","| System/source | Ingestion(s) | Ops/s | Visibility(s) | Visibility ops/s |","|---|---:|---:|---:|---:|",f"| DGAI / R05 cp01-05 | {can['DGAI']['ingestion_seconds']:.3f} | {can['DGAI']['ingestion_throughput_ops_s']:.3f} | {can['DGAI']['restart_visibility_seconds']:.3f} restart | {can['DGAI']['restart_visible_throughput_ops_s']:.3f} |",f"| OdinANN / R06 cp01-06 | {can['OdinANN']['ingestion_seconds']:.3f} | {can['OdinANN']['ingestion_throughput_ops_s']:.3f} | {can['OdinANN']['online_visibility_seconds']:.3f} online | {can['OdinANN']['online_visible_throughput_ops_s']:.3f} |","","## Fixed-policy query","","| System | Phase | L | Recall median[min,max] | QPS median | P99 median(us) |","|---|---|---:|---|---:|---:|"]
for s in ("DGAI","OdinANN"):
 for phase in ("pre_cp00","post_cp01"):
  for L in sorted({x[1] for x in qs[s] if x[0]==phase}):
   x=[z for z in qs[s] if z[0]==phase and z[1]==L]; rv=[z[3] for z in x]; lines.append(f"| {s} | {phase} | {L} | {statistics.median(rv):.4f}[{min(rv):.4f},{max(rv):.4f}] | {statistics.median(z[4] for z in x):.2f} | {statistics.median(z[5] for z in x):.1f} |")
lines += ["","DiskANN 为 immutable CP00 对 R02 CP01 GT 的 stale-static negative control；完整逐次值位于 R06 `stale_control.json`。Recall/QPS/P99 与 overlap 是诊断记录，identity-v2 不以 Recall 区间裁决基础设施。",""]
a.output.write_text("\n".join(lines)); m=load(r06/"execution_manifest.json"); m.update({"status":"complete","completed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"report":str(a.output.resolve()),"composed_sources":{"DGAI":"R05/cp01-05","OdinANN":"R06/cp01-06","DiskANN":"R06/stale-cp00-06","GT":"R02/gt_cp01"}}); (r06/"execution_manifest.json").write_text(json.dumps(m,indent=2)+"\n")
