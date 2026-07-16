#!/usr/bin/env python3
"""Create or transition the fail-closed CP05 cumulative execution manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path


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
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
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
    parser.add_argument("--phase")
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    now_ns = time.time_ns()
    if args.action == "activate":
        if args.manifest.exists() or args.preflight is None:
            raise SystemExit("activation requires fresh manifest and preflight")
        preflight = json.loads(args.preflight.read_text())
        if preflight.get("status") != "pass":
            raise SystemExit("preflight did not pass")
        payload: dict[str, object] = {
            "schema": "dynamic-vamana-w1-cp05-cumulative-execution-v1",
            "status": "running",
            "phase": args.phase or "execution_deltas",
            "started_unix_ns": now_ns,
            "controller_pid": int(os.environ.get("W1_CONTROLLER_PID", "0")),
            "preflight_realpath": str(args.preflight.resolve()),
            "preflight_sha256": sha256(args.preflight),
            "authorized_sequence": ["CP00", "CP01", "CP05"],
            "attempts": {
                "DGAI": "trajectory-cp05-01",
                "OdinANN": "trajectory-cp05-01",
                "DiskANN": "stale-cp05-01",
            },
            "retry_policy": "none",
        }
    else:
        if not args.manifest.is_file():
            raise SystemExit("execution manifest absent")
        payload = json.loads(args.manifest.read_text())
        if payload.get("status") not in ("running",):
            raise SystemExit("terminal execution manifest cannot transition")
        if args.action == "phase":
            if not args.phase:
                raise SystemExit("phase transition requires --phase")
            payload["phase"] = args.phase
            payload["phase_updated_unix_ns"] = now_ns
        elif args.action == "stop":
            payload.update(
                status="stopped_failed",
                stopped_phase=args.phase or payload.get("phase"),
                exit_code=args.exit_code,
                stopped_unix_ns=now_ns,
            )
        else:
            if args.summary is None or not args.summary.is_file():
                raise SystemExit("complete transition requires summary")
            payload.update(
                status="complete",
                phase="complete",
                completed_unix_ns=now_ns,
                summary_realpath=str(args.summary.resolve()),
                summary_sha256=sha256(args.summary),
            )
    write_atomic(args.manifest, payload)


if __name__ == "__main__":
    main()
