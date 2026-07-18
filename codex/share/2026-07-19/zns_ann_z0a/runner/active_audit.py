#!/usr/bin/env python3
import argparse
import hashlib
import json
import struct
from pathlib import Path


def read_tags(path: Path):
    with path.open("rb") as f:
        n, d = struct.unpack("<II", f.read(8))
        if d != 1:
            raise ValueError(f"bad tag dimension {d}")
        values = list(struct.unpack(f"<{n}I", f.read(4 * n)))
        if f.read(1):
            raise ValueError("trailing bytes")
    return values


def digest(values):
    return hashlib.sha256(struct.pack(f"<{len(values)}I", *sorted(values))).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--actual", required=True, type=Path)
    p.add_argument("--expected", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    actual, expected = read_tags(a.actual), read_tags(a.expected)
    report = {
        "schema": "zns-ann-z0a-active-audit-v1",
        "actual_count": len(actual), "expected_count": len(expected),
        "actual_sorted_sha256": digest(actual),
        "expected_sorted_sha256": digest(expected),
        "duplicate_count": len(actual) - len(set(actual)),
        "exact_match": sorted(actual) == sorted(expected),
    }
    report["status"] = "pass" if report["exact_match"] and report["duplicate_count"] == 0 else "fail"
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
