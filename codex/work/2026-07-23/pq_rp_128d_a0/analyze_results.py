#!/usr/bin/env python3
"""Aggregate full PQ-RP repeats into recall/performance frontiers."""

from __future__ import annotations

import csv
import json
import math
import struct
from pathlib import Path

import numpy as np

ROOT = Path("/home/ubuntu/pz/VectorDB/chat")
WORK = ROOT / "codex/work/2026-07-23/pq_rp_128d_a0"
RESULTS = WORK / "results"
ART = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_128d_a0_0723")
GT_PATH = ART / "sift1m_official_gt100.truthset"
LABELS = ("pq8", "pq16", "pq32", "exact")
SEARCH_L = (50, 100, 150, 200, 300)
REPEATS = (1, 2, 3)

with GT_PATH.open("rb") as handle:
    nqueries, gt_k = struct.unpack("<II", handle.read(8))
gt_ids = np.memmap(GT_PATH, dtype=np.uint32, mode="r", offset=8, shape=(nqueries, gt_k))
artifact_manifest = json.loads((RESULTS / "artifact_manifest.json").read_text())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def recall_from_metrics(label: str, search_l: int) -> float:
    rows = read_csv(RESULTS / f"per_query/full_{label}_r1.csv")
    block = [row for row in rows if int(row["L"]) == search_l]
    if len(block) != nqueries:
        raise ValueError(f"{label} L{search_l}: expected {nqueries} rows, got {len(block)}")
    recall = []
    for row in block:
        qid = int(row["qid"])
        returned = {int(row[f"id{k}"]) for k in range(10)}
        recall.append(len(returned & set(gt_ids[qid, :10])) / 10.0)
    return float(np.mean(recall))


run_rows = []
for label in LABELS:
    for repeat in REPEATS:
        path = RESULTS / f"full_{label}_r{repeat}_summary.csv"
        rows = read_csv(path)
        if len(rows) != len(SEARCH_L):
            raise ValueError(f"incomplete summary: {path}")
        run_rows.extend(rows)

run_fields = list(run_rows[0])
with (RESULTS / "run_summary_all.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=run_fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(run_rows)

median_metrics = (
    "qps", "p50_us", "p95_us", "p99_us", "mean_cpu_us", "mean_io_us",
    "mean_comparisons", "mean_hops", "mean_ios", "mean_exact_nav_reads",
    "ssd_bytes_per_query", "nav_dram_bytes_per_query", "touched_bytes_per_query",
    "peak_rss_kib",
)
curve_rows = []
for label in LABELS:
    for search_l in SEARCH_L:
        block = [
            row for row in run_rows
            if row["label"] == label and int(row["L"]) == search_l
        ]
        if len(block) != len(REPEATS):
            raise ValueError(f"{label} L{search_l}: missing repeat")
        row = {
            "label": label,
            "code_bytes": 0 if label == "exact" else int(label.removeprefix("pq")),
            "L": search_l,
            "recall_at_10": recall_from_metrics(label, search_l),
        }
        for metric in median_metrics:
            row[metric] = float(np.median([float(item[metric]) for item in block]))
            row[f"{metric}_min"] = float(np.min([float(item[metric]) for item in block]))
            row[f"{metric}_max"] = float(np.max([float(item[metric]) for item in block]))
        if label == "exact":
            row["pq_resident_bytes"] = artifact_manifest["16"]["pq_resident_bytes"]
            row["full_vector_resident_bytes"] = 1_000_000 * 128 * 4
        else:
            code = label.removeprefix("pq")
            row["pq_resident_bytes"] = artifact_manifest[code]["pq_resident_bytes"]
            row["full_vector_resident_bytes"] = 0
        row["declared_nav_resident_bytes"] = (
            row["pq_resident_bytes"] + row["full_vector_resident_bytes"]
        )
        row["query_scratch_bytes"] = ""
        curve_rows.append(row)

curve_fields = list(curve_rows[0])
with (RESULTS / "curve_summary.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=curve_fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(curve_rows)

exact_by_l = {
    int(row["L"]): float(row["recall_at_10"])
    for row in curve_rows if row["label"] == "exact"
}
gaps = {}
for label in ("pq8", "pq16", "pq32"):
    values = []
    for row in curve_rows:
        if row["label"] != label:
            continue
        search_l = int(row["L"])
        gap = exact_by_l[search_l] - float(row["recall_at_10"])
        values.append({"L": search_l, "gap_pp": 100.0 * gap})
    gaps[label] = {
        "by_L": values,
        "maximum_gap_pp": max(item["gap_pp"] for item in values),
        "remaining_gap_at_L300_pp": next(
            item["gap_pp"] for item in values if item["L"] == 300
        ),
    }

marginal_rows = []
for label in LABELS:
    points = sorted(
        (row for row in curve_rows if row["label"] == label),
        key=lambda row: int(row["L"]),
    )
    for left, right in zip(points, points[1:]):
        recall_pp = 100.0 * (
            float(right["recall_at_10"]) - float(left["recall_at_10"])
        )
        item = {
            "label": label,
            "L_from": int(left["L"]),
            "L_to": int(right["L"]),
            "recall_gain_pp": recall_pp,
        }
        for metric in ("mean_comparisons", "mean_ios", "p50_us", "p95_us", "p99_us"):
            delta = float(right[metric]) - float(left[metric])
            item[f"delta_{metric}"] = delta
            item[f"{metric}_per_recall_pp"] = (
                delta / recall_pp if recall_pp > 1e-12 else math.inf
            )
        marginal_rows.append(item)

with (RESULTS / "marginal_cost.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(
        handle, fieldnames=list(marginal_rows[0]), lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(marginal_rows)


def pareto(points: list[dict], cost: str, maximize_cost: bool = False) -> list[int]:
    selected = []
    for candidate in points:
        dominated = False
        for other in points:
            recall_better = float(other["recall_at_10"]) >= float(candidate["recall_at_10"])
            if maximize_cost:
                cost_better = float(other[cost]) >= float(candidate[cost])
                strict = (
                    float(other["recall_at_10"]) > float(candidate["recall_at_10"])
                    or float(other[cost]) > float(candidate[cost])
                )
            else:
                cost_better = float(other[cost]) <= float(candidate[cost])
                strict = (
                    float(other["recall_at_10"]) > float(candidate["recall_at_10"])
                    or float(other[cost]) < float(candidate[cost])
                )
            if recall_better and cost_better and strict:
                dominated = True
                break
        if not dominated:
            selected.append(int(candidate["L"]))
    return selected


frontiers = {}
for label in LABELS:
    points = [row for row in curve_rows if row["label"] == label]
    frontiers[label] = {
        "recall_qps_L": pareto(points, "qps", maximize_cost=True),
        "recall_p50_L": pareto(points, "p50_us"),
        "recall_ios_L": pareto(points, "mean_ios"),
    }

analysis = {
    "gaps_vs_exact_same_L": gaps,
    "pareto_frontiers": frontiers,
    "query_scratch_bytes": {
        "value": None,
        "reason": "not reported: allocator and scratch-pool overhead cannot be isolated reliably",
    },
    "curve_points": len(curve_rows),
    "performance_repeats": len(REPEATS),
}
(RESULTS / "analysis_summary.json").write_text(
    json.dumps(analysis, indent=2, sort_keys=True) + "\n"
)
print(json.dumps(analysis, indent=2, sort_keys=True))

