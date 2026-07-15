#!/usr/bin/env python3
"""Fail-closed verifier for result-ID output from deterministic W1 probes."""
from __future__ import annotations
import argparse,json,struct
from pathlib import Path
import numpy as np
def main()->None:
 p=argparse.ArgumentParser();p.add_argument('--probes',type=Path,required=True);p.add_argument('--result-tags',type=Path,required=True);p.add_argument('--active-tags',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 spec=json.loads(a.probes.read_text())['probes'];raw=a.result_tags.read_bytes()
 if len(raw)<8:raise ValueError('short result-ID output')
 nq,k=struct.unpack('<II',raw[:8])
 if nq!=len(spec) or k<1 or len(raw)!=8+nq*k*4:raise ValueError('result-ID output layout mismatch')
 result=np.frombuffer(raw,dtype='<u4',offset=8).reshape(nq,k)
 with a.active_tags.open('rb') as f:n,d=struct.unpack('<II',f.read(8))
 if d!=1:raise ValueError('invalid active tag set')
 active=np.asarray(np.memmap(a.active_tags,dtype='<u4',mode='r',offset=8,shape=(n,)))
 active_set=set(active.tolist()); rows=[]
 for i,probe in enumerate(spec):
  ids=[int(x) for x in result[i]]; all_active=all(x in active_set for x in ids)
  ok=(int(probe['expected_tag']) in ids) if probe['kind']=='insert' else (int(probe['forbidden_tag']) not in ids)
  rows.append({'ordinal':i,'op_seq':probe['op_seq'],'kind':probe['kind'],'result_ids':ids,'all_returned_tags_active':all_active,'passed':ok and all_active})
 report={'schema':'dynamic-vamana-w1-visibility-probe-v1','valid':all(r['passed'] for r in rows),'rows':rows}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
 if not report['valid']:raise SystemExit('visibility probe failed')
if __name__=='__main__':main()
