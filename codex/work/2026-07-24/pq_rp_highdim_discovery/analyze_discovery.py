#!/usr/bin/env python3
"""Aggregate the preregistered GIST960 discovery characterization."""

from __future__ import annotations

import csv
import gzip
import itertools
import json
import math
import struct
import time
from pathlib import Path

import numpy as np

WORK = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_discovery")
DATA = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724")
RESULTS = WORK / "results"
GT_PATH = DATA / "converted/gist_gt100.truthset"
LABELS = ("pq16", "pq32", "pq64", "exact")
SEARCH_L = (50, 100, 200, 400, 800)
LIMIT = 0.25
METRICS = (
    "qps", "p50_us", "p95_us", "p99_us", "mean_cpu_us", "mean_io_us",
    "mean_comparisons", "mean_hops", "mean_ios", "mean_exact_nav_reads",
    "ssd_bytes_per_query", "nav_dram_bytes_per_query", "touched_bytes_per_query",
    "peak_rss_kib",
)

with GT_PATH.open("rb") as handle:
    nqueries, gt_k = struct.unpack("<II", handle.read(8))
gt_ids = np.memmap(
    GT_PATH, dtype="<u4", mode="r", offset=8, shape=(nqueries, gt_k)
)
gate = json.loads((RESULTS / "repeat_gate.json").read_text())
repeats = {
    label: ((1, 2, 3) if label in gate["triggered"] else (1, 2))
    for label in LABELS
}


def read_summary(label: str, repeat: int) -> list[dict[str, str]]:
    path = RESULTS / f"discovery_{label}_r{repeat}_summary.csv"
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def read_raw(label: str) -> list[dict[str, str]]:
    path = RESULTS / "per_query" / f"discovery_{label}_r1.csv.gz"
    with gzip.open(path, "rt", newline="") as handle:
        return list(csv.DictReader(handle))


def drift(a: float, b: float) -> float:
    return abs(a - b) / max(min(a, b), 1e-12)


def recall_at_10(raw: list[dict[str, str]], search_l: int) -> float:
    block = [row for row in raw if int(row["L"]) == search_l]
    if len(block) != nqueries:
        raise ValueError(f"L{search_l}: expected {nqueries}, got {len(block)}")
    recalls = []
    for row in block:
        qid = int(row["qid"])
        returned = {int(row[f"id{k}"]) for k in range(10)}
        truth = set(map(int, gt_ids[qid, :10]))
        recalls.append(len(returned & truth) / 10.0)
    return float(np.mean(recalls))


all_runs: list[dict[str, str]] = []
curve_rows: list[dict[str, object]] = []
stability: dict[str, object] = {}
for label in LABELS:
    by_repeat = {repeat: read_summary(label, repeat) for repeat in repeats[label]}
    for rows in by_repeat.values():
        if len(rows) != len(SEARCH_L):
            raise ValueError(f"incomplete {label} summary")
        all_runs.extend(rows)
    raw = read_raw(label)
    label_stable = True
    for search_l in SEARCH_L:
        block = {
            repeat: next(row for row in rows if int(row["L"]) == search_l)
            for repeat, rows in by_repeat.items()
        }
        code_bytes = 3840 if label == "exact" else int(label[2:])
        row: dict[str, object] = {
            "label": label,
            "code_bytes": code_bytes,
            "bits_per_dimension": 8.0 * code_bytes / 960,
            "L": search_l,
            "recall_at_10": recall_at_10(raw, search_l),
            "pq_resident_bytes": 0 if label == "exact" else 1_000_000 * code_bytes,
            "full_vector_resident_bytes": 3_840_000_000 if label == "exact" else 0,
            "repeats": len(repeats[label]),
            "center": "median" if len(repeats[label]) == 3 else "mean",
        }
        for metric in METRICS:
            values = [float(block[r][metric]) for r in repeats[label]]
            row[metric] = (
                float(np.median(values))
                if len(values) == 3
                else float(np.mean(values))
            )
            row[f"{metric}_min"] = min(values)
            row[f"{metric}_max"] = max(values)
            for repeat, value in zip(repeats[label], values):
                row[f"{metric}_r{repeat}"] = value
        pair_checks = []
        for a, b in itertools.combinations(repeats[label], 2):
            pair_checks.append({
                "pair": [a, b],
                "p50_drift": drift(
                    float(block[a]["p50_us"]), float(block[b]["p50_us"])
                ),
                "qps_drift": drift(
                    float(block[a]["qps"]), float(block[b]["qps"])
                ),
            })
        point_stable = any(
            item["p50_drift"] <= LIMIT and item["qps_drift"] <= LIMIT
            for item in pair_checks
        )
        label_stable &= point_stable
        stability[f"{label}_L{search_l}"] = {
            "stable_pair_exists": point_stable,
            "pairs": pair_checks,
        }
        curve_rows.append(row)
    stability[label] = {
        "repeats": len(repeats[label]),
        "performance_stable": label_stable,
    }

with (RESULTS / "run_summary_all.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(all_runs[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(all_runs)

fieldnames = sorted({key for row in curve_rows for key in row})
with (RESULTS / "curve_summary.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(curve_rows)


def points(label: str) -> list[dict[str, object]]:
    return sorted(
        (row for row in curve_rows if row["label"] == label),
        key=lambda row: int(row["L"]),
    )


def threshold_compare(lower_label: str, higher_label: str) -> dict[str, object]:
    lower, higher = points(lower_label), points(higher_label)
    common_max = min(
        max(float(row["recall_at_10"]) for row in lower),
        max(float(row["recall_at_10"]) for row in higher),
    )
    target = math.floor((common_max + 1e-12) * 200.0) / 200.0
    low = next(row for row in lower if float(row["recall_at_10"]) >= target)
    high = next(row for row in higher if float(row["recall_at_10"]) >= target)
    return {
        "target_recall": target,
        "lower": lower_label,
        "lower_L": low["L"],
        "lower_recall": low["recall_at_10"],
        "higher": higher_label,
        "higher_L": high["L"],
        "higher_recall": high["recall_at_10"],
        "L_reduction": 1.0 - float(high["L"]) / float(low["L"]),
        "reads_reduction": 1.0 - float(high["mean_ios"]) / float(low["mean_ios"]),
        "comparisons_reduction": (
            1.0 - float(high["mean_comparisons"]) / float(low["mean_comparisons"])
        ),
        "hops_reduction": 1.0 - float(high["mean_hops"]) / float(low["mean_hops"]),
        "qps_speedup": float(high["qps"]) / float(low["qps"]),
        "p50_reduction": 1.0 - float(high["p50_us"]) / float(low["p50_us"]),
        "p99_reduction": 1.0 - float(high["p99_us"]) / float(low["p99_us"]),
        "extra_bytes_per_vector": (
            int(higher_label[2:]) - int(lower_label[2:])
        ),
    }


comparisons = [
    threshold_compare("pq16", "pq32"),
    threshold_compare("pq32", "pq64"),
]
pq64_match = comparisons[1]
pq64_stable = bool(stability["pq64"]["performance_stable"])
pq32_stable = bool(stability["pq32"]["performance_stable"])
structural_pass = float(pq64_match["reads_reduction"]) >= 0.30
no_perf_regression = (
    float(pq64_match["qps_speedup"]) >= 0.90
    and float(pq64_match["p99_reduction"]) >= -0.10
)

if structural_pass and pq64_stable and pq32_stable and no_perf_regression:
    verdict = "PASS-DISCOVERY-UNIFORM-PRECISION-TRADEOFF"
elif structural_pass:
    verdict = "HOLD-DISCOVERY-STRUCTURAL-SIGNAL"
elif not pq64_stable or not pq32_stable:
    verdict = "HOLD-DISCOVERY-WEAK-OR-UNSTABLE"
else:
    verdict = "KILL-DISCOVERY-NO-PQ64-FRONTIER-SHIFT"

decision = {
    "experiment": "PQ-RP-HIGHDIM-DISCOVERY",
    "dataset": "GIST1M-960D",
    "scope": "idea-discovery characterization only; not a paper-level result",
    "repeats": repeats,
    "stability": stability,
    "threshold_comparisons": comparisons,
    "verdict": verdict,
    "forbidden_claims": [
        "mixed precision is feasible",
        "the effect generalizes to high-dimensional data",
        "precision benefits are node- or query-selective",
        "paper-level RP superiority",
    ],
    "generated_at_unix": time.time(),
}
(RESULTS / "decision.json").write_text(
    json.dumps(decision, indent=2, sort_keys=True) + "\n"
)
print(json.dumps(decision, indent=2, sort_keys=True))
