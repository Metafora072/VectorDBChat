#!/usr/bin/env python3
"""Enforce the preregistered PQ-RP canary gate."""

from __future__ import annotations

import csv
import json
import struct
from pathlib import Path

import numpy as np

ROOT = Path("/home/ubuntu/pz/VectorDB/chat")
WORK = ROOT / "codex/work/2026-07-23/pq_rp_128d_a0"
P07 = ROOT / "codex/work/2026-07-22/p07_page_bonus_a0"
GT = P07 / "results/gt_1000_top100"

with GT.open("rb") as handle:
    nqueries, gt_k = struct.unpack("<II", handle.read(8))
gt_ids = np.memmap(GT, dtype=np.uint32, mode="r", offset=8, shape=(nqueries, gt_k))


def metrics(label: str, repeat: int) -> list[dict[str, str]]:
    path = WORK / f"results/per_query/canary_{label}_r{repeat}.csv"
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "qid", "L", "qps", "run_wall_s", "total_us", "cpu_us", "io_us",
        "n_ios", "n_cmps", "n_hops", "n_exact_nav_reads", "id0",
    }
    if len(rows) != 5000 or not required.issubset(rows[0]):
        raise ValueError(f"incomplete metrics: {path}, rows={len(rows)}")
    return rows


def recall(rows: list[dict[str, str]], search_l: int) -> float:
    block = [row for row in rows if int(row["L"]) == search_l]
    values = []
    for row in block:
        qid = int(row["qid"])
        returned = {int(row[f"id{k}"]) for k in range(10)}
        values.append(len(returned & set(gt_ids[qid, :10])) / 10.0)
    return float(np.mean(values))


recalls = {}
p50 = {}
for label in ("pq16", "exact"):
    for repeat in (1, 2):
        rows = metrics(label, repeat)
        for search_l in (50, 100, 150, 200, 300):
            key = f"{label}_r{repeat}_L{search_l}"
            recalls[key] = recall(rows, search_l)
            latency = [float(row["total_us"]) for row in rows if int(row["L"]) == search_l]
            p50[key] = float(np.median(latency))

expected = {100: 0.9651, 150: 0.9844, 200: 0.9914}
failures = []
for repeat in (1, 2):
    for search_l, target in expected.items():
        actual = recalls[f"pq16_r{repeat}_L{search_l}"]
        if abs(actual - target) > 0.0005:
            failures.append(f"PQ16 r{repeat} L{search_l}: {actual:.6f} vs {target:.6f}")
    if recalls[f"exact_r{repeat}_L100"] < 0.997:
        failures.append(f"Exact r{repeat} L100 below 0.997")

for label in ("pq16", "exact"):
    for search_l in (50, 100, 150, 200, 300):
        left = p50[f"{label}_r1_L{search_l}"]
        right = p50[f"{label}_r2_L{search_l}"]
        relative = abs(left - right) / max(min(left, right), 1.0)
        if relative > 0.25:
            failures.append(f"p50 drift {label} L{search_l}: {relative:.3f}")

result = {
    "status": "PASS" if not failures else "FAIL",
    "failures": failures,
    "recall": recalls,
    "p50_us": p50,
}
path = WORK / "results/canary_gate.json"
path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, indent=2, sort_keys=True))
if failures:
    raise SystemExit(1)

