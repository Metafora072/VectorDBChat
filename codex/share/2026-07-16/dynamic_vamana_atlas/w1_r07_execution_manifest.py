#!/usr/bin/env python3
"""Create the R07 DiskANN-only continuation execution manifest."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, required=True)
    parser.add_argument("--loader-tests", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("R07 execution manifest overwrite refused")
    preflight = json.loads(args.preflight.read_text())
    runtime = json.loads(args.runtime_manifest.read_text())
    tests = json.loads(args.loader_tests.read_text())
    if not all(item.get("status") == "pass" for item in (preflight, runtime, tests)):
        raise SystemExit("R07 preflight/runtime/loader tests did not pass")
    device = subprocess.run(["findmnt", "-rn", "-T", str(args.root), "-o", "MAJ:MIN"], check=True,
                            text=True, capture_output=True).stdout.splitlines()[0]
    report = {
        "schema": "dynamic-vamana-w1-r07-diskann-continuation-execution-v1", "status": "running",
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "pid": os.getpid(),
        "experiment_root": str(args.root.resolve()), "experiment_device": device,
        "initial_free_bytes": shutil.disk_usage(args.root).free,
        "global_lock_held": os.environ.get("W1_GLOBAL_LOCK_HELD") == "1",
        "r05_dgai_source_run": "pilot3_sift10m_w1_r05", "r05_dgai_source_attempt": "DGAI/cp01-05",
        "r05_dgai_reexecuted": False,
        "r06_odinann_source_run": "pilot3_sift10m_w1_r06", "r06_odinann_source_attempt": "OdinANN/cp01-06",
        "r06_odinann_reexecuted": False,
        "r02_gt_reused": True, "r02_gt_sha256": preflight["r02_gt_sha256"], "cp01_reused": True,
        "execution_preflight": {"realpath": str(args.preflight.resolve()), "sha256": sha(args.preflight)},
        "runtime_manifest": {"realpath": str(args.runtime_manifest.resolve()), "sha256": sha(args.runtime_manifest)},
        "loader_tests": {"realpath": str(args.loader_tests.resolve()), "sha256": sha(args.loader_tests)},
        "policy": {"systems_serial": ["DiskANN stale-static negative control"], "L": [29, 53],
                   "repetitions": 3, "query_threads": 1, "dynamic_systems_reexecuted": False},
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
