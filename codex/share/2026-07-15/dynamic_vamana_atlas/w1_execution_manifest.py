#!/usr/bin/env python3
"""Create the immutable identity and initial capacity record for one formal W1 execution."""
from __future__ import annotations

import argparse, datetime, hashlib, json, os, shutil, subprocess
from pathlib import Path


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--artifact-manifest", type=Path, required=True)
    p.add_argument("--preflight", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise SystemExit("execution manifest overwrite refused")
    device = subprocess.run(["findmnt", "-rn", "-T", str(a.root), "-o", "MAJ:MIN"], check=True, text=True, capture_output=True).stdout.splitlines()[0]
    report = {"schema": "dynamic-vamana-w1-execution-manifest-v1", "status": "running",
              "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "pid": os.getpid(), "experiment_root": str(a.root.resolve()), "experiment_device": device,
              "initial_free_bytes": shutil.disk_usage(a.root).free,
              "global_lock_held": os.environ.get("W1_GLOBAL_LOCK_HELD") == "1",
              "artifact_manifest": {"realpath": str(a.artifact_manifest.resolve()), "sha256": sha(a.artifact_manifest)},
              "execution_preflight": {"realpath": str(a.preflight.resolve()), "sha256": sha(a.preflight)},
              "policy": {"seed": 20260713, "delete_count": 80000, "insert_count": 80000,
                         "final_active_cardinality": 8000000, "systems_serial": ["DGAI", "OdinANN", "DiskANN stale-static negative control"]}}
    a.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
