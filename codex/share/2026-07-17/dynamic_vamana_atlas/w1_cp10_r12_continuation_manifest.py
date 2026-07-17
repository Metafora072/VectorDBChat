#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, time
from pathlib import Path
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p:Path,d:dict)->None:
 t=p.with_name(f'.{p.name}.tmp.{os.getpid()}');t.write_text(json.dumps(d,indent=2)+'\n');os.replace(t,p)
q=argparse.ArgumentParser();q.add_argument('command',choices=('activate','phase','complete','stop'));q.add_argument('--manifest',type=Path,required=True);q.add_argument('--r12-execution',type=Path);q.add_argument('--phase');q.add_argument('--exit-code',type=int);a=q.parse_args()
if a.command=='activate':
 if a.manifest.exists() or a.r12_execution is None:raise SystemExit('continuation target/anchor invalid')
 x=json.loads(a.r12_execution.read_text())
 if (x.get('status'),x.get('phase'),x.get('exit_code'))!=('stopped_failed','cp10_DGAI',1):raise SystemExit('R12 terminal anchor mismatch')
 d={'schema':'dynamic-vamana-w1-cp10-r12-query-continuation-v1','status':'running','phase':'resume_DGAI_query',
    'composition':'R12 DGAI PASS stage + query-only continuation + fresh OdinANN/DiskANN','r12_execution':{'realpath':str(a.r12_execution.resolve()),'sha256':sha(a.r12_execution)},'started_unix_ns':time.time_ns(),'cp20':'HOLD'}
else:
 d=json.loads(a.manifest.read_text())
 if d.get('status')!='running':raise SystemExit('continuation manifest terminal')
 if a.command=='phase':d['phase']=a.phase
 elif a.command=='complete':d.update(status='complete',phase='complete',completed_unix_ns=time.time_ns())
 else:d.update(status='stopped_failed',phase=a.phase,exit_code=a.exit_code,stopped_unix_ns=time.time_ns())
put(a.manifest,d)
