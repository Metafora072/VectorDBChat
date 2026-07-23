#!/usr/bin/env python3
"""Aggregate the frozen high-dimensional PQ RP-memory experiment."""

from __future__ import annotations

import csv
import gzip
import json
import math
import struct
from pathlib import Path

import numpy as np

WORK = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_a0")
DATA = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724")
RESULTS = WORK / "results"
GT_PATH = DATA / "converted/gist_gt100.truthset"
LABELS = ("pq16", "pq32", "pq64", "exact")
SEARCH_L = (50, 100, 200, 400, 800)
REPEATS = (1, 2)
DIM = 960

with GT_PATH.open("rb") as handle:
    nqueries, gt_k = struct.unpack("<II", handle.read(8))
gt_ids = np.memmap(GT_PATH, dtype="<u4", mode="r", offset=8, shape=(nqueries, gt_k))
m1 = json.loads((RESULTS / "m1_artifact_audit.json").read_text())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def raw_metrics(label: str, repeat: int) -> list[dict[str, str]]:
    path = RESULTS / f"per_query/full_{label}_r{repeat}.csv.gz"
    with gzip.open(path, "rt", newline="") as handle:
        return list(csv.DictReader(handle))


raw_r1 = {label: raw_metrics(label, 1) for label in LABELS}


def recall_at_10(label: str, search_l: int) -> float:
    block = [row for row in raw_r1[label] if int(row["L"]) == search_l]
    if len(block) != nqueries:
        raise ValueError(f"{label} L{search_l}: expected {nqueries}, got {len(block)}")
    values = []
    for row in block:
        qid = int(row["qid"])
        returned = {int(row[f"id{k}"]) for k in range(10)}
        values.append(len(returned & set(map(int, gt_ids[qid, :10]))) / 10.0)
    return float(np.mean(values))


run_rows = []
for label in LABELS:
    for repeat in REPEATS:
        rows = read_csv(RESULTS / f"full_{label}_r{repeat}_summary.csv")
        if len(rows) != len(SEARCH_L):
            raise ValueError(f"incomplete summary: {label} r{repeat}")
        run_rows.extend(rows)

with (RESULTS / "run_summary_all.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(run_rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(run_rows)

metric_names = (
    "qps", "p50_us", "p95_us", "p99_us", "mean_cpu_us", "mean_io_us",
    "mean_comparisons", "mean_hops", "mean_ios", "mean_exact_nav_reads",
    "ssd_bytes_per_query", "nav_dram_bytes_per_query", "touched_bytes_per_query",
    "peak_rss_kib",
)
curve_rows = []
stability = {}
for label in LABELS:
    for search_l in SEARCH_L:
        block = [
            row for row in run_rows
            if row["label"] == label and int(row["L"]) == search_l
        ]
        if len(block) != 2:
            raise ValueError(f"{label} L{search_l}: missing repeat")
        code_bytes = 16 if label == "exact" else int(label.removeprefix("pq"))
        full_bytes = 1_000_000 * DIM * 4 if label == "exact" else 0
        row = {
            "label": label,
            "code_bytes": code_bytes,
            "bits_per_dimension": 8.0 * code_bytes / DIM,
            "raw_float_compression": DIM * 4 / code_bytes,
            "L": search_l,
            "recall_at_10": recall_at_10(label, search_l),
            "pq_resident_bytes": 1_000_000 * code_bytes,
            "full_vector_resident_bytes": full_bytes,
            "declared_nav_resident_bytes": 1_000_000 * code_bytes + full_bytes,
        }
        for metric in metric_names:
            values = [float(item[metric]) for item in block]
            row[metric] = float(np.median(values))
            row[f"{metric}_r1"] = values[0]
            row[f"{metric}_r2"] = values[1]
            row[f"{metric}_min"] = min(values)
            row[f"{metric}_max"] = max(values)
        p50_values = [float(item["p50_us"]) for item in block]
        drift = abs(p50_values[0] - p50_values[1]) / max(min(p50_values), 1.0)
        stability[f"{label}_L{search_l}"] = {
            "p50_relative_drift": drift,
            "within_25pct": drift <= 0.25,
        }
        curve_rows.append(row)

with (RESULTS / "curve_summary.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(curve_rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(curve_rows)


def points(label: str) -> list[dict]:
    return sorted((row for row in curve_rows if row["label"] == label), key=lambda row: int(row["L"]))


def conservative_point(label: str, target: float) -> dict | None:
    for row in points(label):
        if float(row["recall_at_10"]) + 1e-12 >= target:
            return row
    return None


pq32 = points("pq32")
pq64 = points("pq64")
lower = max(0.95, min(float(row["recall_at_10"]) for row in pq32), min(float(row["recall_at_10"]) for row in pq64))
upper = min(0.995, max(float(row["recall_at_10"]) for row in pq32), max(float(row["recall_at_10"]) for row in pq64))
r_star = math.floor((upper + 1e-12) * 200.0) / 200.0 if upper >= lower else None
if r_star is not None and r_star < lower:
    r_star = None

matched_rows = []
repeat_pass = {}
if r_star is not None:
    p32 = conservative_point("pq32", r_star)
    p64 = conservative_point("pq64", r_star)
    if p32 is None or p64 is None:
        r_star = None
    else:
        for repeat in REPEATS:
            qps_speedup = float(p64[f"qps_r{repeat}"]) / float(p32[f"qps_r{repeat}"])
            reads_reduction = 1.0 - float(p64[f"mean_ios_r{repeat}"]) / float(p32[f"mean_ios_r{repeat}"])
            p99_reduction = 1.0 - float(p64[f"p99_us_r{repeat}"]) / float(p32[f"p99_us_r{repeat}"])
            gate = reads_reduction >= 0.30 and (qps_speedup >= 1.5 or p99_reduction >= 0.30)
            repeat_pass[str(repeat)] = gate
            matched_rows.append({
                "repeat": repeat,
                "r_star": r_star,
                "pq32_L": p32["L"],
                "pq32_recall": p32["recall_at_10"],
                "pq64_L": p64["L"],
                "pq64_recall": p64["recall_at_10"],
                "qps_speedup_pq64_over_pq32": qps_speedup,
                "reads_reduction": reads_reduction,
                "p99_reduction": p99_reduction,
                "go_gate": gate,
            })

if matched_rows:
    with (RESULTS / "matched_recall_pq32_pq64.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(matched_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(matched_rows)

exact_by_l = {int(row["L"]): float(row["recall_at_10"]) for row in points("exact")}
same_l_gaps = [
    {
        "L": int(row["L"]),
        "exact_recall": exact_by_l[int(row["L"])],
        "pq32_recall": float(row["recall_at_10"]),
        "gap_pp": 100.0 * (exact_by_l[int(row["L"])] - float(row["recall_at_10"])),
    }
    for row in pq32
    if 0.95 <= exact_by_l[int(row["L"])] <= 0.995
]
saturated = bool(same_l_gaps) and all(item["gap_pp"] <= 0.25 for item in same_l_gaps)
all_stable = all(item["within_25pct"] for item in stability.values())

if r_star is None:
    verdict = "HOLD-DATASET-SPECIFIC"
    reason = "No preregistered common-recall grid point was reachable without extrapolation."
elif all(repeat_pass.values()):
    verdict = "HOLD-DATASET-SPECIFIC"
    reason = (
        "PQ64 passed the numerical GO gates, but GIST fallback evidence is capped "
        "at HOLD-DATASET-SPECIFIC by preregistration."
    )
else:
    improvements = [
        (
            row["qps_speedup_pq64_over_pq32"] - 1.0,
            row["reads_reduction"],
            row["p99_reduction"],
        )
        for row in matched_rows
    ]
    uniformly_below_10 = all(max(values) < 0.10 for values in improvements)
    if saturated or uniformly_below_10:
        verdict = "KILL-MIXED-PRECISION-MOTIVATION"
        reason = (
            "PQ32 is same-L saturated against Exact in the preregistered recall range."
            if saturated
            else "PQ64 improvements are below 10% in QPS, p99, and reads."
        )
    else:
        verdict = "HOLD-DATASET-SPECIFIC"
        reason = "PQ64 benefit lies between the preregistered KILL and GO thresholds."

decision = {
    "dataset": "GIST1M-960D",
    "dataset_scope_warning": (
        "This changes dataset, distribution, and dimension relative to SIFT128; "
        "differences are workload-specific evidence and are not attributable to dimension alone."
    ),
    "r_star": r_star,
    "matched_recall": matched_rows,
    "go_gate_by_repeat": repeat_pass,
    "same_l_pq32_exact_gaps": same_l_gaps,
    "saturated_pq32_highdim": saturated,
    "performance_stability": stability,
    "all_p50_drifts_within_25pct": all_stable,
    "verdict": verdict,
    "reason": reason,
    "mixed_precision_selectivity_not_established": True,
    "m1_artifact_status": m1["status"],
}
(RESULTS / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n")
print(json.dumps(decision, indent=2, sort_keys=True))
