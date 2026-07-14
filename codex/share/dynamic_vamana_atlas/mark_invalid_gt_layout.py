#!/usr/bin/env python3
"""Preserve a forensic marker for a truthset produced by row-wise slicing."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-run-root", type=Path, required=True)
    parser.add_argument("--truthset", type=Path, required=True)
    args = parser.parse_args()
    if not args.truthset.is_file():
        raise SystemExit(f"missing old truthset: {args.truthset}")
    args.old_run_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "dynamic-vamana-invalid-gt-layout-v1",
        "marked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "artifact": str(args.truthset.resolve()),
        "sha256": sha256(args.truthset),
        "reason": "make_binary_prefix.py copied only the initial ID block; DiskANN truthsets store all IDs before all distance values.",
        "status": "INVALID_GT_LAYOUT",
        "preservation": "artifact retained unchanged; do not use for formal Recall claims",
    }
    (args.old_run_root / "INVALID_GT_LAYOUT.json").write_text(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
