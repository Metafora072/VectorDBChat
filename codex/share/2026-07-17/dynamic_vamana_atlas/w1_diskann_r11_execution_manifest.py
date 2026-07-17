#!/usr/bin/env python3
"""Create or transition the fail-closed DiskANN-only R11 execution manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path


SCHEMA = "dynamic-vamana-w1-cp05-diskann-closure-r11-execution-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with temporary.open("w") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("activate", "phase", "stop", "complete"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--r10-execution", type=Path)
    parser.add_argument("--r10-preservation", type=Path)
    parser.add_argument("--phase")
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--closure-manifest", type=Path)
    args = parser.parse_args(); now = time.time_ns()
    if args.action == "activate":
        required = (args.preflight, args.r10_execution, args.r10_preservation)
        if args.manifest.exists() or any(path is None or not path.is_file() for path in required):
            raise SystemExit("R11 activation requires fresh manifest and all bound evidence")
        preflight = json.loads(args.preflight.read_text())
        r10 = json.loads(args.r10_execution.read_text())
        preservation = json.loads(args.r10_preservation.read_text())
        if (preflight.get("schema") != "dynamic-vamana-w1-cp05-diskann-closure-r11-preflight-v1"
                or preflight.get("status") != "pass"):
            raise SystemExit("R11 preflight did not pass")
        if ((r10.get("schema"), r10.get("status"), r10.get("stopped_phase"), r10.get("exit_code"))
                != ("dynamic-vamana-w1-cp05-cumulative-r10-execution-v1", "stopped_failed",
                    "diskann_cp05_stale_control", 1)):
            raise SystemExit("R10 terminal identity mismatch")
        if (preservation.get("schema") != "dynamic-vamana-w1-cp05-cumulative-r10-preservation-v1"
                or preservation.get("status") != "pass" or preservation.get("mismatches")):
            raise SystemExit("R10 stop preservation is not PASS")
        payload: dict[str, object] = {
            "schema": SCHEMA, "status": "running", "phase": args.phase or "diskann_cp05_stale_control",
            "started_unix_ns": now, "controller_pid": int(os.environ.get("W1_CONTROLLER_PID", "0")),
            "run": "pilot3_sift10m_w1_cp05_diskann_closure_r11", "attempt": "stale-cp05-11",
            "result_root": str(args.manifest.parent.resolve()),
            "preflight_realpath": str(args.preflight.resolve()), "preflight_sha256": sha256(args.preflight),
            "r10_execution_realpath": str(args.r10_execution.resolve()),
            "r10_execution_sha256": sha256(args.r10_execution),
            "r10_preservation_realpath": str(args.r10_preservation.resolve()),
            "r10_preservation_sha256": sha256(args.r10_preservation),
            "base_root": "/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index",
            "L": [29, 53], "Tq": 1, "repetitions": 3,
            "r10_dynamic_results_reused_readonly": True, "r10_attempt_modified": False,
            "cp10_cp20": "HOLD", "retry_policy": "none",
        }
    else:
        if not args.manifest.is_file():
            raise SystemExit("R11 execution manifest absent")
        payload = json.loads(args.manifest.read_text())
        if payload.get("schema") != SCHEMA or payload.get("status") != "running":
            raise SystemExit("terminal or foreign R11 execution manifest cannot transition")
        if args.action == "phase":
            if not args.phase:
                raise SystemExit("phase transition requires --phase")
            payload["phase"] = args.phase; payload["phase_updated_unix_ns"] = now
        elif args.action == "stop":
            payload.update(status="stopped_failed", stopped_phase=args.phase or payload.get("phase"),
                           exit_code=args.exit_code, stopped_unix_ns=now)
        else:
            if args.closure_manifest is None or not args.closure_manifest.is_file():
                raise SystemExit("complete transition requires closure manifest")
            payload.update(status="complete", phase="complete", completed_unix_ns=now,
                           closure_manifest_realpath=str(args.closure_manifest.resolve()),
                           closure_manifest_sha256=sha256(args.closure_manifest))
    write_atomic(args.manifest, payload)


if __name__ == "__main__":
    main()
