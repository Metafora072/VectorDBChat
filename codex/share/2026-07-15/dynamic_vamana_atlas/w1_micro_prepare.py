#!/usr/bin/env python3
"""Prepare the authorized 16-replacement, 1M infrastructure-only canary."""
from __future__ import annotations
import argparse,csv,json,os,struct
from pathlib import Path
import numpy as np
def tags(path):
 with path.open('rb') as f:n,d=struct.unpack('<II',f.read(8))
 if d!=1:raise ValueError('invalid tags')
 return np.asarray(np.memmap(path,dtype='<u4',mode='r',offset=8,shape=(n,)))
def main():
 p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--authorized',action='store_true');a=p.parse_args()
 if not a.authorized:raise SystemExit('micro preparation requires explicit authorization')
 ds=a.dataset.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);n=16
 with (ds/'smoke_replace_new_trace.csv').open() as f:rows=list(csv.DictReader(f))[:n]
 dels=np.asarray([int(r['delete_tag']) for r in rows],dtype='<u4');ins=np.asarray([int(r['insert_tag']) for r in rows],dtype='<u4');src=np.asarray([int(r['insert_source_row']) for r in rows],dtype='<u4')
 if not np.array_equal(ins,src):raise ValueError('insert_source_row/tag mismatch')
 active=tags(ds/'active_cp00.tags.bin');expected=np.sort(np.concatenate((active[~np.isin(active,dels)],ins))).astype('<u4')
 with (out/'trace.bin').open('wb') as f:f.write(struct.pack('<i',n));dels.tofile(f);ins.tofile(f)
 with (out/'active.tags.bin').open('wb') as f:f.write(struct.pack('<II',expected.size,1));expected.tofile(f)
 pos=sorted(set([0,n-1]+[round(i*(n-1)/8) for i in range(1,8)]));
 if len(pos)!=9:raise ValueError('micro positions not unique')
 probes=[]
 for x in pos:probes += [{'ordinal':len(probes),'op_seq':x,'kind':'insert','query_tag':int(ins[x]),'expected_tag':int(ins[x])},{'ordinal':len(probes)+1,'op_seq':x,'kind':'delete','query_tag':int(dels[x]),'forbidden_tag':int(dels[x])}]
 (out/'probes.json').write_text(json.dumps({'schema':'w1-micro-probes-v1','positions':pos,'probes':probes},indent=2)+'\n')
 with (ds/'full_1m.bin').open('rb') as f:total,dim=struct.unpack('<II',f.read(8))
 full=np.memmap(ds/'full_1m.bin',dtype='<f4',mode='r',offset=8,shape=(total,dim));q=np.asarray([x['query_tag'] for x in probes],dtype=np.uint32)
 with (out/'probes.bin').open('wb') as f:f.write(struct.pack('<II',q.size,dim));np.asarray(full[q],dtype='<f4').tofile(f)
 (out/'manifest.json').write_text(json.dumps({'schema':'w1-micro-v1','replacements':n,'active_count':int(expected.size),'positions':pos,'classification':'infrastructure correctness test only'},indent=2)+'\n')
if __name__=='__main__':main()
