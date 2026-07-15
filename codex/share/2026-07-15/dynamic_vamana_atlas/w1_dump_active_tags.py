#!/usr/bin/env python3
"""Audit persisted `<prefix>_disk.index.tags` without decoding index internals."""
from __future__ import annotations
import argparse, hashlib, json, struct
from pathlib import Path
import numpy as np
def read(p:Path)->np.ndarray:
 with p.open('rb') as f:n,d=struct.unpack('<II',f.read(8))
 if d!=1 or p.stat().st_size!=8+n*4:raise ValueError(f'invalid persisted tags: {p}')
 return np.asarray(np.memmap(p,dtype='<u4',mode='r',offset=8,shape=(n,)))
def digest(a:np.ndarray)->str:return hashlib.sha256(np.sort(a).astype('<u4',copy=False).tobytes()).hexdigest()
def main()->None:
 p=argparse.ArgumentParser();p.add_argument('--tags',type=Path,required=True);p.add_argument('--expected',type=Path,required=True);p.add_argument('--expected-count',type=int,default=8_000_000);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 actual,expected=read(a.tags),read(a.expected); sorted_actual=np.sort(actual); duplicate=int(actual.size-np.unique(actual).size)
 report={'schema':'dynamic-vamana-w1-active-tag-audit-v1','active_tag_count':int(actual.size),'sorted_active_tag_sha256':digest(actual),'minimum_tag':int(sorted_actual[0]),'maximum_tag':int(sorted_actual[-1]),'duplicate_count':duplicate,'expected_exact_match':bool(np.array_equal(sorted_actual,np.sort(expected)))}
 report['valid']=report['active_tag_count']==a.expected_count and duplicate==0 and report['expected_exact_match']
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
 if not report['valid']:raise SystemExit('active-tag audit failed')
if __name__=='__main__':main()
