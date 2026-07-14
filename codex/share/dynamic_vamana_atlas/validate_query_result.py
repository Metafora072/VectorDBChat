#!/usr/bin/env python3
"""Validate a DiskANN uint32 result bin against a shared active-tag set."""

from __future__ import annotations

import argparse
import json
import math
import re
import struct
from pathlib import Path

import numpy as np


def read_header(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        raw = handle.read(8)
    if len(raw) != 8:
        raise ValueError(f"short header: {path}")
    return struct.unpack("<II", raw)


def parse_recall(log: Path) -> float:
    content = log.read_text(errors="replace")
    if re.search(r"fatal|abort|assert(?:ion)? failure|segmentation fault|core dumped", content, re.I):
        raise ValueError("query log contains fatal/abort/assert/segmentation-fault marker")
    lines = content.splitlines()
    header = next((index for index, line in enumerate(lines) if "Recall@10" in line), None)
    if header is None:
        raise ValueError("missing Recall@10 header")
    for line in lines[header + 1 :]:
        fields = line.split()
        if len(fields) >= 2 and re.fullmatch(r"[0-9]+", fields[0]):
            try:
                value = float(fields[-1])
            except ValueError:
                continue
            # Drivers report percentages. Normalise to [0, 1] for one criterion.
            if math.isfinite(value) and 0.0 <= value <= 100.0:
                return value / 100.0
    raise ValueError("cannot parse a finite Recall@10 result row")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--active-tags", type=Path, required=True)
    parser.add_argument("--query", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result_n, result_k = read_header(args.result)
    query_n, _ = read_header(args.query)
    tag_n, tag_dim = read_header(args.active_tags)
    if result_n != query_n or result_k != args.k:
        raise ValueError(f"result shape {(result_n, result_k)} != expected {(query_n, args.k)}")
    if tag_dim != 1 or args.active_tags.stat().st_size != 8 + tag_n * 4:
        raise ValueError("invalid active tag file")
    expected_size = 8 + result_n * result_k * 4
    if args.result.stat().st_size != expected_size:
        raise ValueError("result file size does not match header")
    tags = np.memmap(args.active_tags, dtype="<u4", mode="r", offset=8, shape=(tag_n,))
    values = np.memmap(args.result, dtype="<u4", mode="r", offset=8, shape=(result_n, result_k))
    active = np.zeros(int(tags.max()) + 1, dtype=bool)
    active[np.asarray(tags, dtype=np.int64)] = True
    invalid = values >= active.size
    valid = np.zeros(values.shape, dtype=bool)
    valid[~invalid] = active[values[~invalid]]
    if not bool(valid.all()):
        raise ValueError(f"result contains {int((~valid).sum())} inactive/out-of-range IDs")
    recall = parse_recall(args.log)
    report = {
        "schema": "dynamic-vamana-query-result-validation-v1",
        "query_count": result_n,
        "k": result_k,
        "recall_at_10_normalized": recall,
        "all_result_ids_active": True,
        "invalid_or_inactive_ids": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
