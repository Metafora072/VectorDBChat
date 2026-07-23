#!/usr/bin/env python3
"""Enforce all preregistered PQ-RP-HIGHDIM Canary gates."""

from __future__ import annotations

import csv
import gzip
import json
import struct
from pathlib import Path

import numpy as np

WORK = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_a0")
GT = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724/converted/gist_gt100.truthset")
LABELS = ("pq32", "pq64", "exact")
SEARCH_L = (100, 200, 400, 800)

with GT.open("rb") as handle:
    nqueries, gt_k = struct.unpack("<II", handle.read(8))
gt_ids = np.memmap(GT, dtype="<u4", mode="r", offset=8, shape=(nqueries, gt_k))


def metrics(label: str, repeat: int) -> list[dict[str, str]]:
    path = WORK / f"results/per_query/canary_{label}_r{repeat}.csv.gz"
    with gzip.open(path, "rt", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "qid", "L", "qps", "run_wall_s", "total_us", "cpu_us", "io_us",
        "n_ios", "n_cmps", "n_hops", "n_exact_nav_reads",
        *{f"id{k}" for k in range(10)},
    }
    if len(rows) != 200 * len(SEARCH_L) or not rows or not required.issubset(rows[0]):
        raise ValueError(f"incomplete metrics: {path}, rows={len(rows)}")
    return rows


def recall(rows: list[dict[str, str]], search_l: int) -> float:
    values = []
    for row in rows:
        if int(row["L"]) != search_l:
            continue
        qid = int(row["qid"])
        returned = {int(row[f"id{k}"]) for k in range(10)}
        values.append(len(returned & set(map(int, gt_ids[qid, :10]))) / 10.0)
    return float(np.mean(values))


rows_by_run = {(label, repeat): metrics(label, repeat) for label in LABELS for repeat in (1, 2)}
recalls = {}
p50 = {}
failures = []
for label in LABELS:
    for repeat in (1, 2):
        rows = rows_by_run[(label, repeat)]
        for search_l in SEARCH_L:
            key = f"{label}_r{repeat}_L{search_l}"
            recalls[key] = recall(rows, search_l)
            latency = [float(row["total_us"]) for row in rows if int(row["L"]) == search_l]
            p50[key] = float(np.median(latency))
        values = [recalls[f"{label}_r{repeat}_L{search_l}"] for search_l in SEARCH_L]
        for left, right, left_l, right_l in zip(values, values[1:], SEARCH_L, SEARCH_L[1:]):
            if right + 0.0001 < left:
                failures.append(
                    f"recall decreases >0.01pp: {label} r{repeat} L{left_l}->{right_l}: {left:.6f}->{right:.6f}"
                )

for label in LABELS:
    left_rows = rows_by_run[(label, 1)]
    right_rows = rows_by_run[(label, 2)]
    for search_l in SEARCH_L:
        left_ids = [
            tuple(row[f"id{k}"] for k in range(10))
            for row in left_rows if int(row["L"]) == search_l
        ]
        right_ids = [
            tuple(row[f"id{k}"] for k in range(10))
            for row in right_rows if int(row["L"]) == search_l
        ]
        if left_ids != right_ids:
            failures.append(f"non-deterministic returned IDs: {label} L{search_l}")
        left = p50[f"{label}_r1_L{search_l}"]
        right = p50[f"{label}_r2_L{search_l}"]
        drift = abs(left - right) / max(min(left, right), 1.0)
        if drift > 0.25:
            failures.append(f"p50 drift >25%: {label} L{search_l}: {drift:.3f}")

for repeat in (1, 2):
    if recalls[f"exact_r{repeat}_L800"] < 0.995:
        failures.append(f"Exact r{repeat} L800 recall below 99.5%")
    for search_l in SEARCH_L:
        if recalls[f"pq64_r{repeat}_L{search_l}"] + 0.001 < recalls[f"pq32_r{repeat}_L{search_l}"]:
            failures.append(f"PQ64 worse than PQ32 by >0.1pp: r{repeat} L{search_l}")

result = {
    "status": "PASS" if not failures else "FAIL",
    "failures": failures,
    "expected_rows_per_process": 800,
    "recall": recalls,
    "p50_us": p50,
}
path = WORK / "results/canary_gate.json"
path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, indent=2, sort_keys=True))
if failures:
    raise SystemExit(1)
