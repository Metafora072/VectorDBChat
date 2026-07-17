#!/usr/bin/env python3
"""Validate the two minimal canonical input-canary regression outcomes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def identity(path: Path) -> dict[str, object]:
    path = path.resolve(strict=True)
    return {"realpath": str(path), "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positive", type=Path, required=True)
    parser.add_argument("--negative-log", type=Path, required=True)
    parser.add_argument("--negative-output", type=Path, required=True)
    parser.add_argument("--update-marker-root", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    positive = json.loads(args.positive.read_text())
    if (positive.get("schema") != "dynamic-vamana-w1-inaccessible-input-canary-v1"
            or positive.get("status") != "pass" or positive.get("uid") != 1000
            or positive.get("gid") != 1000 or positive.get("allowed_readable") is not True
            or positive.get("update_worker_started") is not False
            or not positive.get("denied")
            or not all(isinstance(row.get("path"), str)
                       and row.get("open_refused") is True
                       and row.get("errno") in (1, 13) for row in positive["denied"])):
        raise SystemExit("positive input-canary regression is invalid")
    if args.negative_output.exists() or "denied input unexpectedly readable" not in args.negative_log.read_text():
        raise SystemExit("readable-denied negative regression did not fail closed")
    forbidden = list(args.update_marker_root.rglob("STAGE_WORKER_OK"))
    forbidden += list(args.update_marker_root.rglob("markers.jsonl"))
    forbidden += list(args.update_marker_root.rglob("ingest_begin"))
    if forbidden:
        raise SystemExit("input-canary fixture started an update worker")
    report = {
        "schema": "dynamic-vamana-w1-canonical-input-canary-tests-v1", "status": "pass",
        "positive": identity(args.positive), "negative_log": identity(args.negative_log),
        "denied_readable_rejected": True, "update_worker_not_started": True,
        "helper": identity(args.helper),
    }
    if args.output.exists() or args.output.is_symlink():
        raise SystemExit("input-canary test report reuse refused")
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2); stream.write("\n")
        stream.flush(); os.fsync(stream.fileno())


if __name__ == "__main__":
    main()
