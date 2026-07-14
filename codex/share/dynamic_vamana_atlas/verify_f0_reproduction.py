#!/usr/bin/env python3
"""Fail closed unless the R1 full-query F0 canary reproduces its reference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED = {"DiskANN": 0.9688, "DGAI": 0.9216, "OdinANN": 0.9738}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--point", type=Path, required=True)
    parser.add_argument("--tolerance", type=float, default=0.00005)
    args = parser.parse_args()
    row = json.loads(args.point.read_text())
    system = row.get("system")
    if system not in EXPECTED:
        raise SystemExit(f"unknown canary system: {system}")
    if row.get("valid") is not True:
        raise SystemExit(f"invalid canary point: {row.get('invalid_reason')}")
    if row.get("query_count") != 10000:
        raise SystemExit(f"canary must use full 10K query, got {row.get('query_count')}")
    identity = row.get("input_identity", {})
    if not identity.get("query") or not identity.get("groundtruth"):
        raise SystemExit("canary lacks query/groundtruth identity")
    observed = float(row["recall_at_10"])
    expected = EXPECTED[system]
    if abs(observed - expected) > args.tolerance:
        raise SystemExit(f"F0 reproduction mismatch for {system}: observed={observed:.8f} expected={expected:.8f}")
    print(f"F0 reproduction PASS {system}: {observed:.8f}")


if __name__ == "__main__":
    main()
