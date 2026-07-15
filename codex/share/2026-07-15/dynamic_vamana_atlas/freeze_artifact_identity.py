#!/usr/bin/env python3
"""Freeze and attach the immutable query artifact identity for P2-A-R1."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"missing artifact: {path}")
    return {"path": str(path.resolve()), "sha256": sha256(path)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--system", required=True)
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--index", type=Path, required=True)
    p.add_argument("--query", type=Path, required=True)
    p.add_argument("--groundtruth", type=Path, required=True)
    p.add_argument("--compat-patch", type=Path, required=True)
    p.add_argument("--source-repo", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--attach-point", type=Path)
    args = p.parse_args()
    if args.output.exists():
        payload = json.loads(args.output.read_text())
    else:
        commit = subprocess.check_output(["git", "-C", str(args.source_repo), "rev-parse", "HEAD"], text=True).strip()
        payload = {
            "schema": "dynamic-vamana-query-artifact-identity-v1",
            "frozen_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "system": args.system,
            "binary": identity(args.binary), "index_file": identity(args.index),
            "query": identity(args.query), "groundtruth": identity(args.groundtruth),
            "compatibility_patch": identity(args.compat_patch), "source_commit": commit,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n")
    if payload.get("system") != args.system:
        raise SystemExit("artifact manifest system mismatch")
    if args.attach_point:
        point = json.loads(args.attach_point.read_text())
        if point.get("system") != args.system:
            raise SystemExit("point system mismatch")
        point["artifact_identity"] = payload
        args.attach_point.write_text(json.dumps(point, indent=2) + "\n")


if __name__ == "__main__":
    main()
