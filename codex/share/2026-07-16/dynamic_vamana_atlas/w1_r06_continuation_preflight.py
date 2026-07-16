#!/usr/bin/env python3
"""Read-only R06 continuation preflight, anchored to accepted prior attempts."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess
from pathlib import Path
from w1_process_identity import ancestor_chain, load_policy, scan

GT_SHA="4703d2d8a12c1c045c60de56819ccb058e91bc28e0f1883d18573f9917b32c28"
def sha(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for b in iter(lambda:f.read(8<<20),b""):h.update(b)
 return h.hexdigest()
def tree(root):
 h=hashlib.sha256(); n=total=0
 for p in sorted(x for x in Path(root).rglob("*") if x.is_file()):
  rel=p.relative_to(root).as_posix(); s=p.stat().st_size; h.update(f"{rel}\t{s}\t{sha(p)}\n".encode()); n+=1; total+=s
 return {"realpath":str(Path(root).resolve()),"manifest_sha256":h.hexdigest(),"file_count":n,"total_bytes":total}
def main():
 p=argparse.ArgumentParser(); p.add_argument("--root",type=Path,required=True); p.add_argument("--artifact-manifest",type=Path,required=True); p.add_argument("--process-tests",type=Path,required=True); p.add_argument("--freeze",type=Path,required=True); p.add_argument("--freeze-tsv",type=Path,required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--runtime-canary-passed",action="store_true"); a=p.parse_args()
 root=a.root.resolve(); result=root/"results/pilot3_sift10m_w1_r06"; formal=root/"formal/pilot3_sift10m_w1_r06"
 allowed={a.process_tests.resolve().relative_to(result).as_posix(),a.freeze.resolve().relative_to(result).as_posix(),a.freeze_tsv.resolve().relative_to(result).as_posix()}
 actual={x.relative_to(result).as_posix() for x in result.rglob("*") if x.is_file() or x.is_symlink()}
 assert actual==allowed and not formal.exists() and not a.output.exists()
 tests=json.loads(a.process_tests.read_text()); freeze=json.loads(a.freeze.read_text()); assert tests.get("status")==freeze.get("status")=="pass"
 assert freeze["source_run"]=="pilot3_sift10m_w1_r05" and freeze["attempt"]=="cp01-05" and freeze["evidence_manifest"]["sha256"]==sha(a.freeze_tsv)
 runs={}
 expected={"pilot3_sift10m_w1":("stopped_failed","gt_cp01_validation"),"pilot3_sift10m_w1_r02":("stopped_failed","DGAI_canary"),"pilot3_sift10m_w1_r04":("stopped_failed","DGAI_canary"),"pilot3_sift10m_w1_r05":("stopped_failed","OdinANN_canary")}
 for run,want in expected.items():
  path=root/"results"/run/"execution_manifest.json"; d=json.loads(path.read_text()); assert (d.get("status"),d.get("stopped_phase"))==want; runs[run]={"sha256":sha(path),"status":d["status"],"stopped_phase":d["stopped_phase"],"exit_code":d.get("exit_code")}
 r05=root/"results/pilot3_sift10m_w1_r05"; odin=r05/"OdinANN/cp01-05"
 assert not (odin/"markers.jsonl").exists() and not any(odin.glob("post_cp01_*")) and not (r05/"DiskANN").exists()
 assert json.loads((r05/"preflight/preservation_after_stop.json").read_text())["status"]=="pass"
 assert json.loads((r05/"preflight/mutable_clone_tests.json").read_text())["status"]=="pass" and json.loads((r05/"preflight/clone_target_tests.json").read_text())["status"]=="pass"
 prior=json.loads((r05/"preflight/execution_preflight.json").read_text()); assert prior["status"]=="pass"
 cp=root/"datasets/sift10m/w1_cp01"; current={}
 for name,old in prior["cp01_artifacts"].items():
  x=cp/name; st=x.stat(); row={"size_bytes":st.st_size,"sha256":sha(x),"mtime_ns":st.st_mtime_ns}; assert row==old; current[name]=row
 gt=root/"groundtruth/sift10m/w1_r02/gt_cp01"; assert sha(gt)==GT_SHA and gt.stat().st_mtime_ns==prior["r02_gt_mtime_ns"]
 artifact=json.loads(a.artifact_manifest.read_text()); bases={"OdinANN":root/"formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index","DiskANN":root/"formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index"}; base={}
 for system,path in bases.items(): base[system]=tree(path); assert base[system]["manifest_sha256"]==artifact["systems"][system]["formal_base"]["manifest_sha256"]
 verifier=a.artifact_manifest.parent/"w1_verify_artifacts.py"; identities={}
 for system in ("OdinANN",):
  ci=artifact["systems"][system]["canonical_install"]; q=subprocess.run(["python3",str(verifier),"--manifest",str(a.artifact_manifest),"--system",system,"--driver",ci["w1_canary"],"--query-binary",ci["search_disk_index"]],check=True,text=True,capture_output=True); identities[system]=json.loads(q.stdout)
 assert artifact["systems"]["OdinANN"]["io_engine"]=="uring"
 dev=subprocess.run(["findmnt","-rn","-T",str(root),"-o","MAJ:MIN"],check=True,text=True,capture_output=True).stdout.splitlines()[0]; free=shutil.disk_usage(root).free
 assert dev==os.environ.get("ATLAS_NVME_MAJMIN","259:10") and free>=150_000_000_000 and a.runtime_canary_passed and os.environ.get("W1_GLOBAL_LOCK_HELD")=="1"
 identity=scan(load_policy(root,a.artifact_manifest.resolve(),Path(__file__).parent),set(ancestor_chain())); assert identity["status"]=="pass"
 for x in (formal/"OdinANN/cp01-06",formal/"DGAI",result/"OdinANN",result/"DiskANN"): assert not x.exists()
 report={"schema":"dynamic-vamana-w1-r06-continuation-preflight-v1","status":"pass","run":"pilot3_sift10m_w1_r06","attempt":"cp01-06","r05_dgai_source":{"run":"pilot3_sift10m_w1_r05","attempt":"cp01-05","reexecuted":False,"freeze_sha256":sha(a.freeze)},"prior_runs":runs,"r05_odin_no_update_started":True,"r05_diskann_absent":True,"r02_gt_reused":True,"r02_gt_sha256":GT_SHA,"r02_gt_mtime_ns":gt.stat().st_mtime_ns,"cp01_reused":True,"cp01_artifacts":current,"formal_bases":base,"artifact_manifest_sha256":sha(a.artifact_manifest),"artifact_verification":identities,"io_engine":"uring","experiment_device":dev,"free_bytes":free,"process_identity_scan":identity,"new_targets_absent":True}
 a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(report,indent=2)+"\n")
if __name__=="__main__":main()
