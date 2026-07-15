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
def write_float(path, values):
 with path.open('wb') as f:
  f.write(struct.pack('<II',values.shape[0],values.shape[1]));np.asarray(values,dtype='<f4').tofile(f)
def materialize_active(full, active, out):
 with out.open('wb') as f:
  f.write(struct.pack('<II',active.size,full.shape[1]))
  for lo in range(0,active.size,16384):np.asarray(full[active[lo:lo+16384]],dtype='<f4').tofile(f)
def exact_gt(full, active, queries, out, k=100):
 ids=np.empty((queries.shape[0],k),dtype='<u4');dists=np.empty((queries.shape[0],k),dtype='<f4')
 for qi,q in enumerate(queries):
  best_d=np.empty(0,dtype=np.float32);best_i=np.empty(0,dtype=np.uint32)
  for lo in range(0,active.size,8192):
   cur=active[lo:lo+8192];vec=np.asarray(full[cur],dtype=np.float32);cur_d=np.einsum('ij,ij->i',vec-q,vec-q,optimize=True)
   all_d=np.concatenate((best_d,cur_d));all_i=np.concatenate((best_i,cur));take=min(k,all_d.size);keep=np.argpartition(all_d,take-1)[:take];order=np.lexsort((all_i[keep],all_d[keep]));best_d=all_d[keep][order];best_i=all_i[keep][order]
  ids[qi],dists[qi]=best_i,best_d
 with out.open('wb') as f:
  f.write(struct.pack('<II',queries.shape[0],k));ids.tofile(f);dists.tofile(f)
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
 query_vectors=np.asarray(full[q],dtype='<f4')
 write_float(out/'query_18.bin',query_vectors)
 materialize_active(full,expected,out/'active_cp01.bin')
 exact_gt(full,active,query_vectors,out/'gt_cp00_18')
 exact_gt(full,expected,query_vectors,out/'gt_cp01_18')
 (out/'manifest.json').write_text(json.dumps({'schema':'w1-micro-v1','replacements':n,'active_count':int(expected.size),'positions':pos,'classification':'infrastructure correctness test only'},indent=2)+'\n')
if __name__=='__main__':main()
