#!/usr/bin/env python3
"""Fail-closed aggregate-only F0 query log validation for native drivers."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path


FATAL = re.compile(
    r"bad file descriptor|\bfailed\b|i/o error|io_uring.*failed|fatal|abort|"
    r"assert(?:ion)? failure|segmentation fault|core dumped",
    re.I,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    text = args.log.read_text(errors="replace")
    if FATAL.search(text):
        raise ValueError("query log contains an I/O or fatal failure marker")
    lines = text.splitlines()
    header = next((index for index, line in enumerate(lines) if "Recall@10" in line), None)
    if header is None:
        raise ValueError("missing Recall@10 header")
    recall = None
    for line in lines[header + 1 :]:
        fields = line.split()
        if fields and fields[0].isdigit():
            try:
                candidate = float(fields[-1])
            except ValueError:
                continue
            if math.isfinite(candidate) and 0.0 <= candidate <= 100.0:
                recall = candidate / 100.0
                break
    if recall is None:
        raise ValueError("missing finite Recall@10 result in [0, 100]")
    report = {
        "schema": "dynamic-vamana-aggregate-query-validation-v1",
        "validation_level": "aggregate-only validation",
        "recall_at_10_normalized": recall,
        "fatal_markers": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
