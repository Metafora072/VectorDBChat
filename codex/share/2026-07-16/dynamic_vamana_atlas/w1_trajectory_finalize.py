#!/usr/bin/env python3
"""Finalize machine evidence and the trajectory preparation report."""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, shutil
from pathlib import Path

def sha(path: Path) -> str:
 h=hashlib.sha256()
 with path.open("rb") as f:
  for b in iter(lambda:f.read(8<<20),b""): h.update(b)
 return h.hexdigest()
def space(root: Path)->dict:
 apparent=allocated=files=0
 for p in root.rglob("*"):
  if p.is_file():
   s=p.stat(); files+=1; apparent+=s.st_size; allocated+=s.st_blocks*512
 return {"files":files,"apparent_bytes":apparent,"allocated_bytes":allocated}
def main()->None:
 p=argparse.ArgumentParser(); p.add_argument("--root",type=Path,required=True); p.add_argument("--validation",type=Path,required=True); p.add_argument("--execution",type=Path,required=True); p.add_argument("--preservation",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
 if a.output.exists(): raise SystemExit("trajectory report overwrite refused")
 validation=json.loads(a.validation.read_text()); execution=json.loads(a.execution.read_text()); preservation=json.loads(a.preservation.read_text())
 if validation.get("status")!="pass" or execution.get("status")!="running" or preservation.get("status")!="pass": raise SystemExit("trajectory final prerequisites invalid")
 root=a.root.resolve(); trajectory=root/"datasets/sift10m/w1_trajectory"; gt=root/"groundtruth/sift10m/w1_trajectory"
 final_free=shutil.disk_usage(root).free; total={"trajectory":space(trajectory),"groundtruth":space(gt)}
 lines=["# Dynamic Vamana W1 Trajectory Preparation Results","","## 结论","",
        "CP05、CP10、CP20 的单一 master-trace 前缀、active sets、active vectors、visibility probes 与 location-ID exact GT preparation 全部通过。该轮仅准备冻结输入，没有创建动态索引 clone，没有运行 DGAI/OdinANN update、checkpoint query、DiskANN stale control 或 rebuild。","",
        "## Master trace 与 CP01 前缀","",
        f"- master records：`1,600,000`；binary SHA256：`{validation['master_trace_sha256']}`。",
        f"- master TSV SHA256：`{validation['master_trace_tsv_sha256']}`；manifest SHA256：`{validation['master_trace_manifest_sha256']}`。",
        f"- CP01 80K logical record payload：逐条 exact；证据 SHA256：`{validation['cp01_prefix_validation_sha256']}`。",
        "- CP05/CP10/CP20 分别是 master 的前 400K/800K/1.6M records；delete 与 insert sets 严格嵌套。","",
        "## Checkpoint artifacts 与 GT","",
        "| Checkpoint | Replacements | Active tags | Trace bin / TSV SHA256 | Active tags SHA256 | Active vectors SHA256 | Probe spec / vectors SHA256 | Final GT SHA256 | GT validation SHA256 | Tag 0 |",
        "|---|---:|---:|---|---|---|---|---|---|---|"]
 for name,row in validation["checkpoints"].items():
  lines.append(f"| {name.upper()} | {row['replacement_count']} | {row['active_cardinality']} | `{row['trace_sha256']}` / `{row['trace_tsv_sha256']}` | `{row['active_tags_sha256']}` | `{row['active_vectors_sha256']}` | `{row['probe_spec_sha256']}` / `{row['probe_vectors_sha256']}` | `{row['gt_sha256']}` | `{row['gt_validation_sha256']}` | {'active' if row['tag_zero_active'] else 'deleted'} |")
 lines += ["","每个 GT 均为 `10000×100`，location IDs range/uniqueness、final active tags、deleted absence、row uniqueness、finite/monotonic distances、remap distance block byte identity 和 less-than-K warning absence 全部通过。每个 checkpoint 均完成固定 36-query brute-force audit：保存 raw 正式/独立列表与逐项比较，并按 `(recomputed squared-L2 distance, tag)` canonicalize 后逐位置 exact；raw 顺序差异只允许来自等距组，distance 逐位置容差为 `5e-3`。","",
           "### 36-query 独立审计身份","",
           "| Checkpoint | Query IDs | Audit count | GT manifest SHA256 | Location GT SHA256 | Compute log SHA256 |","|---|---|---:|---|---|---|"]
 for name,row in validation["checkpoints"].items():
  lines.append(f"| {name.upper()} | `{','.join(str(value) for value in row['audit_qids'])}` | {row['audit_count']} | `{row['gt_manifest_sha256']}` | `{row['locations_gt_sha256']}` | `{row['compute_log_sha256']}` |")
 lines += ["",
           "## 资源","","| Stage | Wall(s) | Peak RSS(B) | cgroup peak(B) | NVMe R/W(B) | Output apparent/allocated delta(B) |","|---|---:|---:|---:|---|---|"]
 for name,row in validation["resources"].items():
  io=row["nvme_delta"]; sp=row["space_delta"]
  lines.append(f"| {name} | {row['elapsed_seconds']:.3f} | {row['peak_process_tree_rss_bytes']} | {row['cgroup_memory_peak_bytes']} | {io['rbytes']}/{io['wbytes']} | {sp['apparent_bytes']}/{sp['allocated_bytes']} |")
 lines += ["",f"Trajectory dataset tree apparent/allocated：`{total['trajectory']['apparent_bytes']}/{total['trajectory']['allocated_bytes']} B`；GT tree apparent/allocated：`{total['groundtruth']['apparent_bytes']}/{total['groundtruth']['allocated_bytes']} B`。项目 NVMe final free：`{final_free} B`。","",
           "十个 preparation stage 均使用独立 scope；每份资源证据强制绑定 command、scope、space root、项目 NVMe `259:10` 的 baseline/final I/O、完整 space samples 与无 OOM memory.events。资源 JSON 的 SHA256 已收录于 trajectory validation。","",
           "## Cross-checkpoint invariants 与边界","",
           "Master/checkpoint prefix、历史 CP01、三组 8M cardinality、delete/insert nesting、active-set difference、全量 vector row/tag mapping、完整 probe semantics、GT active-only、GT source/tool identity、read-only inode-disjoint artifacts 与全部 output hashes 均已冻结。", "",
           f"- trajectory validation SHA256：`{sha(a.validation)}`。",
           f"- final CP01/formal-input preservation：`pass`；SHA256：`{sha(a.preservation)}`。",
           "- 后续 cumulative trajectory update 必须另行审议；本轮停止，不进入动态执行。",""]
 a.output.write_text("\n".join(lines))
 execution.update({"status":"complete","completed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"final_free_bytes":final_free,
                   "trajectory_space":total["trajectory"],"groundtruth_space":total["groundtruth"],"trajectory_validation_sha256":sha(a.validation),
                   "preservation_final_sha256":sha(a.preservation),
                   "report":str(a.output.resolve()),"report_sha256":sha(a.output)})
 temporary=a.execution.with_name(a.execution.name+f".tmp.{os.getpid()}"); temporary.write_text(json.dumps(execution,indent=2)+"\n"); os.replace(temporary,a.execution)
if __name__=="__main__": main()
