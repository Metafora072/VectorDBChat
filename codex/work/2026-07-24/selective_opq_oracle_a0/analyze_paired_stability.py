#!/usr/bin/env python3
"""Paired-query stability diagnostics for strict Stage-A signal points."""

from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

import numpy as np

WORK = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/selective_opq_oracle_a0")
SOURCE = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724")
DATA = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/selective_opq_oracle_a0_0724")
GT = np.memmap(
    SOURCE / "converted/gist_gt100.truthset",
    dtype="<u4",
    mode="r",
    offset=8,
    shape=(1000, 100),
)


def load(path: Path, search_l: int) -> dict[int, dict[str, str]]:
    with gzip.open(path, "rt", newline="") as handle:
        rows = {
            int(row["qid"]): row
            for row in csv.DictReader(handle)
            if int(row["L"]) == search_l
        }
    if set(rows) != set(range(1000)):
        raise RuntimeError(f"incomplete qids in {path} at L={search_l}")
    return rows


def hits(row: dict[str, str], qid: int) -> int:
    returned = {int(row[f"id{k}"]) for k in range(10)}
    return len(returned & set(map(int, GT[qid, :10])))


def bootstrap_ci(values: np.ndarray, rng: np.random.Generator) -> list[float]:
    estimates: list[np.ndarray] = []
    for _ in range(20):
        indices = rng.integers(0, len(values), size=(500, len(values)))
        estimates.append(values[indices].mean(axis=1))
    merged = np.concatenate(estimates)
    return [float(x) for x in np.percentile(merged, [2.5, 50, 97.5])]


with (WORK / "results/stage_a_comparison.csv").open(newline="") as handle:
    positives = [row for row in csv.DictReader(handle) if row["strict_signal"] == "True"]

rng = np.random.default_rng(20260724)
report: list[dict[str, object]] = []
for point in positives:
    search_l = int(point["L"])
    budget = int(point["budget"])
    selector = point["selector"]
    baseline = load(DATA / f"results/uniform_opq{budget}.csv.gz", search_l)
    mixed = load(
        DATA / f"results/mixed_L{search_l}_b{budget}_{selector}.csv.gz",
        search_l,
    )
    hit_delta = np.array(
        [hits(mixed[qid], qid) - hits(baseline[qid], qid) for qid in range(1000)],
        dtype=np.float64,
    )
    reads_reduction = np.array(
        [float(baseline[qid]["n_ios"]) - float(mixed[qid]["n_ios"]) for qid in range(1000)]
    )
    comparisons_reduction = np.array(
        [float(baseline[qid]["n_cmps"]) - float(mixed[qid]["n_cmps"]) for qid in range(1000)]
    )
    metrics = {}
    for name, values in (
        ("hits_delta", hit_delta),
        ("reads_reduction", reads_reduction),
        ("comparisons_reduction", comparisons_reduction),
    ):
        metrics[name] = {
            "mean": float(values.mean()),
            "bootstrap_95_ci": bootstrap_ci(values, rng),
            "positive_query_fraction": float(np.mean(values > 0)),
            "negative_query_fraction": float(np.mean(values < 0)),
            "zero_query_fraction": float(np.mean(values == 0)),
        }
    report.append(
        {
            "L": search_l,
            "budget": budget,
            "selector": selector,
            "metrics": metrics,
        }
    )

output = {
    "diagnostic_only": True,
    "bootstrap_seed": 20260724,
    "bootstrap_resamples": 10000,
    "points": report,
}
(WORK / "results/paired_stability.json").write_text(
    json.dumps(output, indent=2, sort_keys=True) + "\n"
)
print(json.dumps(output, indent=2, sort_keys=True))
