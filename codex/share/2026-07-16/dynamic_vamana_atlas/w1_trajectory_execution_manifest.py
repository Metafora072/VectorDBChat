#!/usr/bin/env python3
"""Create the data-only trajectory preparation execution manifest."""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, shutil, subprocess
from pathlib import Path

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--root",type=Path,required=True); p.add_argument("--preflight",type=Path)
    p.add_argument("--launcher",type=Path,required=True); p.add_argument("--mode",choices=("initialize","activate"),required=True)
    p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    if a.mode == "initialize" and a.output.exists(): raise SystemExit("trajectory execution manifest overwrite refused")
    if a.mode == "activate" and (not a.output.is_file() or a.preflight is None): raise SystemExit("trajectory activation inputs absent")
    dev=subprocess.run(["findmnt","-rn","-T",str(a.root),"-o","MAJ:MIN"],check=True,text=True,capture_output=True).stdout.splitlines()[0]
    controller_pid=int(os.environ.get("W1_CONTROLLER_PID", "0"))
    if controller_pid <= 1: raise SystemExit("trajectory controller PID absent")
    if a.mode == "initialize":
        report={"schema":"dynamic-vamana-w1-trajectory-preparation-execution-v1","status":"preflighting",
            "attempt_started_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"controller_pid":controller_pid,
            "manifest_writer_pid_initialize":os.getpid(), "launcher_realpath":str(a.launcher.resolve()), "launcher_sha256":sha(a.launcher),
            "experiment_root":str(a.root.resolve()),"experiment_device":dev,"initial_free_bytes":shutil.disk_usage(a.root).free,
            "global_lock_held":os.environ.get("W1_GLOBAL_LOCK_HELD")=="1",
            "policy":{"data_only":True,"master_replacements":1600000,"checkpoints":{"cp05":400000,"cp10":800000,"cp20":1600000},
                      "active_cardinality":8000000,"dynamic_clone":False,"index_update":False,"checkpoint_query":False,
                      "diskann_stale_or_rebuild":False,"gt_mode":"location-ID exact then active-tag remap","stages_serial":True}}
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(report,indent=2)+"\n")
        return
    report=json.loads(a.output.read_text()); pre=json.loads(a.preflight.read_text())
    if report.get("status")!="preflighting" or pre.get("status")!="pass" or report.get("controller_pid")!=controller_pid:
        raise SystemExit("trajectory preflight/attempt identity invalid")
    if sha(a.launcher)!=report.get("launcher_sha256"): raise SystemExit("trajectory launcher changed during preflight")
    report.update({"status":"running","started_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   "manifest_writer_pid_activate":os.getpid(),"preflight_sha256":sha(a.preflight)})
    temporary=a.output.with_name(a.output.name+f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(report,indent=2)+"\n"); os.replace(temporary,a.output)
if __name__=="__main__": main()
