#!/usr/bin/env python3
"""Create the R03 system-stage continuation execution manifest."""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, shutil, subprocess
from pathlib import Path

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""): h.update(block)
    return h.hexdigest()

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True)
    p.add_argument("--preflight", type=Path, required=True); p.add_argument("--clone-tests", type=Path, required=True)
    p.add_argument("--mutable-tests", type=Path)
    p.add_argument("--run", choices=("pilot3_sift10m_w1_r03", "pilot3_sift10m_w1_r04", "pilot3_sift10m_w1_r05"), default="pilot3_sift10m_w1_r03")
    p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    label = "r05" if a.run.endswith("_r05") else "r04" if a.run.endswith("_r04") else "r03"
    if a.output.exists(): raise SystemExit(f"{label.upper()} execution manifest overwrite refused")
    preflight = json.loads(a.preflight.read_text()); tests = json.loads(a.clone_tests.read_text())
    if preflight.get("status") != "pass" or tests.get("status") != "pass": raise SystemExit(f"{label.upper()} preflight/tests did not pass")
    mutable = None
    if label == "r05":
        if a.mutable_tests is None or not a.mutable_tests.is_file(): raise SystemExit("R05 mutable-clone tests absent")
        mutable = json.loads(a.mutable_tests.read_text())
        if mutable.get("status") != "pass": raise SystemExit("R05 mutable-clone tests did not pass")
    device = subprocess.run(["findmnt", "-rn", "-T", str(a.root), "-o", "MAJ:MIN"], check=True, text=True, capture_output=True).stdout.splitlines()[0]
    report = {"schema": f"dynamic-vamana-w1-{label}-continuation-execution-v1", "status": "running",
              "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "pid": os.getpid(),
              "experiment_root": str(a.root.resolve()), "experiment_device": device, "initial_free_bytes": shutil.disk_usage(a.root).free,
              "global_lock_held": os.environ.get("W1_GLOBAL_LOCK_HELD") == "1",
              "continuation_parent_r01": "pilot3_sift10m_w1", "continuation_parent_r02": "pilot3_sift10m_w1_r02",
              "continuation_parent_r03": "pilot3_sift10m_w1_r03" if label in ("r04", "r05") else None,
              "continuation_parent_r04": "pilot3_sift10m_w1_r04" if label == "r05" else None,
              "r02_gt_reused": True, "r02_gt_sha256": preflight["r02_gt_sha256"], "cp01_reused": True,
              "clone_allowlist_mode": "full_exact_target_capability_mutable_private_tree" if label == "r05" else "full_exact_target_capability" if label == "r04" else "exact_target_capability",
              "execution_preflight": {"realpath": str(a.preflight.resolve()), "sha256": sha(a.preflight)},
              "clone_target_tests": {"realpath": str(a.clone_tests.resolve()), "sha256": sha(a.clone_tests)},
              "mutable_clone_tests": {"realpath": str(a.mutable_tests.resolve()), "sha256": sha(a.mutable_tests)} if mutable is not None else None,
              "policy": {"delete_count": 80000, "insert_count": 80000, "final_active_cardinality": 8000000,
                         "systems_serial": ["DGAI", "OdinANN", "DiskANN stale-static negative control"]}}
    a.output.write_text(json.dumps(report, indent=2) + "\n")

if __name__ == "__main__": main()
