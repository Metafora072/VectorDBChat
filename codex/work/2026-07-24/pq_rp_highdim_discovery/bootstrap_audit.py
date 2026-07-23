#!/usr/bin/env python3
"""Paired-query audit for the primary threshold-dominance comparison."""

from __future__ import annotations

import csv
import gzip
import json
import struct
from pathlib import Path

import numpy as np

WORK = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_discovery")
GT_PATH = Path(
    "/home/ubuntu/pz/VectorDB/data/VectorDB/"
    "pq_rp_highdim_a0_0724/converted/gist_gt100.truthset"
)
SEED = 20260724
BOOTSTRAPS = 10_000

with GT_PATH.open("rb") as handle:
    nqueries, gt_k = struct.unpack("<II", handle.read(8))
gt_ids = np.memmap(
    GT_PATH, dtype="<u4", mode="r", offset=8, shape=(nqueries, gt_k)
)


def recalls(label: str, search_l: int) -> np.ndarray:
    path = WORK / "results/per_query" / f"discovery_{label}_r1.csv.gz"
    with gzip.open(path, "rt", newline="") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if int(row["L"]) == search_l
        ]
    if len(rows) != nqueries:
        raise ValueError(f"{label} L{search_l}: expected {nqueries} rows")
    result = np.empty(nqueries)
    for row in rows:
        qid = int(row["qid"])
        returned = {int(row[f"id{k}"]) for k in range(10)}
        truth = set(map(int, gt_ids[qid, :10]))
        result[qid] = len(returned & truth) / 10.0
    return result


delta = recalls("pq64", 400) - recalls("pq32", 800)
rng = np.random.default_rng(SEED)
means = np.empty(BOOTSTRAPS)
for start in range(0, BOOTSTRAPS, 1_000):
    count = min(1_000, BOOTSTRAPS - start)
    indices = rng.integers(0, nqueries, size=(count, nqueries))
    means[start:start + count] = delta[indices].mean(axis=1)

result = {
    "comparison": "PQ64 L400 minus PQ32 L800 per-query Recall@10",
    "seed": SEED,
    "bootstrap_samples": BOOTSTRAPS,
    "mean_delta_pp": 100.0 * float(delta.mean()),
    "bootstrap_95pct_ci_pp": [
        100.0 * float(x) for x in np.quantile(means, [0.025, 0.975])
    ],
    "query_wins": int(np.sum(delta > 0)),
    "query_ties": int(np.sum(delta == 0)),
    "query_losses": int(np.sum(delta < 0)),
    "scope": "post-hoc uncertainty audit; not part of the preregistered PASS gate",
}
(WORK / "results/bootstrap_audit.json").write_text(
    json.dumps(result, indent=2, sort_keys=True) + "\n"
)
print(json.dumps(result, indent=2, sort_keys=True))

