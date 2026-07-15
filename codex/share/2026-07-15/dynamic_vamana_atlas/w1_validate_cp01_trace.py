#!/usr/bin/env python3
"""Independently validate a W1 trace and its expected active-tag checkpoint."""
from __future__ import annotations
import argparse, hashlib, json, struct
from pathlib import Path
import numpy as np

def sha(p: Path) -> str:
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''): h.update(b)
 return h.hexdigest()
def tags(p: Path) -> np.ndarray:
 with p.open('rb') as f: n,d=struct.unpack('<II',f.read(8))
 if d!=1 or p.stat().st_size!=8+n*4: raise ValueError(f'invalid tag file {p}')
 return np.asarray(np.memmap(p,dtype='<u4',mode='r',offset=8,shape=(n,)))
def main() -> None:
 p=argparse.ArgumentParser(); p.add_argument('--initial-active-tags',type=Path,required=True); p.add_argument('--work-dir',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
 initial, out = tags(a.initial_active_tags), a.work_dir
 raw=(out/'replace_cp01_80k.bin').read_bytes(); n=struct.unpack('<i',raw[:4])[0]
 if n!=80_000 or len(raw)!=4+n*8: raise ValueError('invalid 80K binary trace layout')
 dels=np.frombuffer(raw,dtype='<u4',offset=4,count=n); ins=np.frombuffer(raw,dtype='<u4',offset=4+n*4,count=n); actual=tags(out/'active_cp01.tags.bin')
 expected=np.sort(np.concatenate((initial[~np.isin(initial,dels)],ins))).astype('<u4',copy=False)
 checks={'delete_unique':np.unique(dels).size==n,'insert_unique':np.unique(ins).size==n,'disjoint':np.intersect1d(dels,ins).size==0,
         'deletes_from_initial':bool(np.all(np.isin(dels,initial))),'inserts_absent_initial':not bool(np.any(np.isin(ins,initial))),
         'expected_cardinality':int(expected.size),'actual_exact_match':bool(np.array_equal(actual,expected)),'binary_trace_sha256':sha(out/'replace_cp01_80k.bin'),
         'expected_active_sha256':sha(out/'active_cp01.tags.bin')}
 if not all(v is True for v in checks.values() if isinstance(v,bool)): raise ValueError(checks)
 manifest=json.loads((out/'replace_cp01_manifest.json').read_text())
 if manifest['binary_trace_sha256']!=checks['binary_trace_sha256'] or manifest['expected_cp01_active_set_sha256']!=checks['expected_active_sha256']: raise ValueError('manifest hash mismatch')
 a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps({'schema':'dynamic-vamana-w1-trace-validation-v1','valid':True,'checks':checks},indent=2)+'\n')
if __name__=='__main__': main()
