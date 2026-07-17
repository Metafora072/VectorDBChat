#!/usr/bin/env python3
"""Atomic terminal state for the R12 CP10 continuation."""
from __future__ import annotations
import argparse, hashlib, json, os, time
from pathlib import Path

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path: Path, value: dict) -> None:
    tmp=path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(value,indent=2)+"\n"); os.replace(tmp,path)

p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command",required=True)
a=sub.add_parser("activate"); a.add_argument("--manifest",type=Path,required=True); a.add_argument("--preflight",type=Path,required=True)
for name in ("phase","complete","stop"):
    q=sub.add_parser(name); q.add_argument("--manifest",type=Path,required=True); q.add_argument("--phase",required=name!="complete")
    if name=="stop": q.add_argument("--exit-code",type=int,required=True)
args=p.parse_args()
if args.command=="activate":
    if args.manifest.exists(): raise SystemExit("R12 manifest reuse refused")
    d={"schema":"dynamic-vamana-w1-cp10-r12-execution-v1","run":"pilot3_sift10m_w1_cp10_trajectory_r12",
       "status":"running","phase":"preflight_complete","preflight":{"realpath":str(args.preflight.resolve()),"sha256":sha(args.preflight)},
       "started_unix_ns":time.time_ns(),"cp20":"HOLD"}
else:
    d=json.loads(args.manifest.read_text())
    if d.get("status")!="running": raise SystemExit("R12 manifest is terminal")
    if args.command=="phase": d["phase"]=args.phase
    elif args.command=="complete": d.update(status="complete",phase="complete",completed_unix_ns=time.time_ns())
    else: d.update(status="stopped_failed",phase=args.phase,exit_code=args.exit_code,stopped_unix_ns=time.time_ns())
write(args.manifest,d)
