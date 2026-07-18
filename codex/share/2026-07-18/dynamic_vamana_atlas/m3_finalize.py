#!/usr/bin/env python3
import argparse, hashlib, json, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
def load(p): return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''): h.update(b)
 return h.hexdigest()
p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--result-root',type=Path,required=True); p.add_argument('--formal-root',type=Path,required=True); p.add_argument('--build-manifest',type=Path,required=True); p.add_argument('--m2-summary',type=Path,required=True); p.add_argument('--comparability',type=Path,required=True); p.add_argument('--free-before',type=int,required=True); a=p.parse_args()
points=[]
for n in (50000,400000):
 for s in ('DGAI','OdinANN'):
  q=a.result_root/s/f'm3-n{n}-01/m3_summary.json'; d=load(q); assert d['status']=='pass'; d['summary']=str(q.resolve()); d['summary_sha256']=sha(q); points.append(d)
free_after=int(subprocess.check_output(['df','-PB1',str(a.root)],text=True).splitlines()[1].split()[3])
formal_bytes=sum(x.stat().st_size for x in a.formal_root.rglob('*') if x.is_file()); result_bytes=sum(x.stat().st_size for x in a.result_root.rglob('*') if x.is_file())
summary={'schema':'dynamic-vamana-write-supersession-m3-summary-v1','status':'complete','completed_at_utc8':datetime.now(timezone(timedelta(hours=8))).isoformat(),
 'scope':'DGAI/OdinANN 50K and 400K only; no coalescing and no matched-R build','m2_summary':{'path':str(a.m2_summary.resolve()),'sha256':sha(a.m2_summary)},
 'build_manifest':{'path':str(a.build_manifest.resolve()),'sha256':sha(a.build_manifest)},'comparability_audit':{'path':str(a.comparability.resolve()),'sha256':sha(a.comparability)},'points':points,
 'aggregate':{'generated':sum(x['totals']['generated'] for x in points),'directly_supersedable_before_submit_versions':sum(x['directly_supersedable_before_submit_versions'] for x in points),
  'directly_supersedable_before_submit_bytes':sum(x['directly_supersedable_before_submit_bytes'] for x in points),'already_avoided_versions':sum(x['already_avoided_versions'] for x in points)},
 'space':{'free_before_bytes':a.free_before,'free_after_bytes':free_after,'free_space_delta_bytes':a.free_before-free_after,'formal_apparent_bytes':formal_bytes,'result_apparent_bytes':result_bytes},
 'experiments_started_beyond_gate':False}
o=a.result_root/'m3_summary.json'; o.write_text(json.dumps(summary,indent=2)+'\n'); (a.result_root/'M3_COMPLETE').touch(); print(o)
