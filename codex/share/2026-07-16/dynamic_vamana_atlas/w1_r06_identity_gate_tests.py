#!/usr/bin/env python3
"""Replay identity-v2 and prove semantic corruptions fail closed."""
from __future__ import annotations
import argparse,json,shutil,struct,subprocess
from pathlib import Path
def main():
 p=argparse.ArgumentParser(); p.add_argument("--root",type=Path,required=True); p.add_argument("--gate",type=Path,required=True); p.add_argument("--artifact",type=Path,required=True); p.add_argument("--scratch",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
 if a.scratch.exists() or a.output.exists(): raise SystemExit("identity test freshness failed")
 source=a.root/"results/pilot3_sift10m_w1_r05/OdinANN/cp01-05"; clone=a.root/"formal/pilot3_sift10m_w1_r05/OdinANN/cp01-05"; a.scratch.mkdir(parents=True)
 names=[]
 for L in (29,46):
  for r in (1,2,3): names += [f"pre_cp00_L{L}_r{r}{s}" for s in (".metrics.json",".validation.json",".resources.json",".result_ids.bin",".log")]
 def fixture(name):
  d=a.scratch/name; d.mkdir();
  for n in names: shutil.copy2(source/n,d/n)
  return d
 common=["python3",str(a.gate),"--system","OdinANN","--mode","formal","--binary",str(a.root/"build/w1-canonical-v6/install/OdinANN/search_disk_index"),"--driver",str(a.root/"build/w1-canonical-v6/install/OdinANN/w1_canary"),"--artifact-manifest",str(a.artifact),"--base-manifest",str(clone/"base_content_before.tsv"),"--clone-manifest",str(clone/"clone_content_before.tsv"),"--query",str(a.root/"datasets/sift10m/query.bin"),"--gt",str(a.root/"groundtruth/sift10m/pilot3_sift10m_p1r07/gt_cp00"),"--active-tags",str(clone/"index/index_disk.index.tags"),"--ls","29,46","--threads","1","--io-engine","uring","--device","259:10"]
 rows=[]
 def run(name,mutate,expected):
  d=fixture(name); mutate(d); out=d/"gate.json"; q=subprocess.run(common+["--result-dir",str(d),"--output",str(out)],text=True,capture_output=True); rows.append({"name":name,"expected_exit":expected,"actual_exit":q.returncode,"passed":q.returncode==expected,"stderr":q.stderr[-1000:]})
 run("valid_replay",lambda d:None,0)
 def setid(d,index,value):
  p=d/"pre_cp00_L29_r1.result_ids.bin"; b=bytearray(p.read_bytes()); struct.pack_into("<I",b,8+index*4,value); p.write_bytes(b)
 run("duplicate_id",lambda d:setid(d,1,struct.unpack_from("<I",(d/"pre_cp00_L29_r1.result_ids.bin").read_bytes(),8)[0]),1)
 run("sentinel_id",lambda d:setid(d,0,0xffffffff),1)
 run("inactive_id",lambda d:setid(d,0,10000001),1)
 def wrong_l(d):
  p=d/"pre_cp00_L29_r1.log"; p.write_text(p.read_text().replace("        29          16","        28          16"))
 run("wrong_actual_l",wrong_l,1)
 report={"schema":"dynamic-vamana-w1-r06-identity-gate-tests-v1","status":"pass" if all(x["passed"] for x in rows) else "fail","tests":rows}
 a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(report,indent=2)+"\n"); shutil.rmtree(a.scratch)
 if report["status"]!="pass": raise SystemExit("identity gate tests failed")
if __name__=="__main__":main()
