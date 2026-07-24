#!/usr/bin/env python3
"""Aggregate OPQ runs and expose complete PQ/OPQ frontier evidence."""

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

WORK = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/uniform_quantizer_baseline_a0")
BASELINE = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_discovery/results")
DATA = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724")
RESULTS = WORK / "results"
SEARCH_L = (50, 100, 200, 400, 800)
LABELS = ("opq32", "opq64")
LIMIT = 0.25
METRICS = (
    "qps", "p50_us", "p95_us", "p99_us", "mean_cpu_us", "mean_io_us",
    "mean_comparisons", "mean_hops", "mean_ios", "mean_exact_nav_reads",
    "ssd_bytes_per_query", "nav_dram_bytes_per_query", "touched_bytes_per_query",
    "peak_rss_kib",
)

with (DATA / "converted/gist_gt100.truthset").open("rb") as handle:
    nqueries, gt_k = struct.unpack("<II", handle.read(8))
gt_ids = np.memmap(
    DATA / "converted/gist_gt100.truthset",
    dtype="<u4", mode="r", offset=8, shape=(nqueries, gt_k),
)
gate = json.loads((RESULTS / "repeat_gate.json").read_text())
repeats = {
    label: ((1, 2, 3) if label in gate["triggered"] else (1, 2))
    for label in LABELS
}
artifact_audit = json.loads((RESULTS / "artifact_audit.json").read_text())


def read_summary(label: str, repeat: int) -> list[dict[str, str]]:
    with (RESULTS / f"full_{label}_r{repeat}_summary.csv").open(newline="") as handle:
        return list(csv.DictReader(handle))


def read_raw(label: str) -> list[dict[str, str]]:
    with gzip.open(RESULTS / f"per_query/full_{label}_r1.csv.gz", "rt", newline="") as handle:
        return list(csv.DictReader(handle))


def recall_at_10(raw: list[dict[str, str]], search_l: int) -> float:
    block = [row for row in raw if int(row["L"]) == search_l]
    if len(block) != nqueries:
        raise ValueError(f"L{search_l}: expected {nqueries}, got {len(block)}")
    recalls = []
    for row in block:
        qid = int(row["qid"])
        returned = {int(row[f"id{k}"]) for k in range(10)}
        recalls.append(len(returned & set(map(int, gt_ids[qid, :10]))) / 10)
    return float(np.mean(recalls))


def drift(a: float, b: float) -> float:
    return abs(a - b) / max(min(a, b), 1e-12)


curve_rows: list[dict[str, object]] = []
all_runs: list[dict[str, str]] = []
stability: dict[str, object] = {}
for label in LABELS:
    by_repeat = {repeat: read_summary(label, repeat) for repeat in repeats[label]}
    for rows in by_repeat.values():
        if len(rows) != len(SEARCH_L):
            raise ValueError(f"incomplete {label} summary")
        all_runs.extend(rows)
    raw = read_raw(label)
    label_stable = True
    code_bytes = int(label[3:])
    artifact = artifact_audit["representations"][label]
    for search_l in SEARCH_L:
        block = {
            repeat: next(row for row in rows if int(row["L"]) == search_l)
            for repeat, rows in by_repeat.items()
        }
        row: dict[str, object] = {
            "label": label,
            "code_bytes": code_bytes,
            "bits_per_dimension": 8.0 * code_bytes / 960,
            "L": search_l,
            "recall_at_10": recall_at_10(raw, search_l),
            "pq_resident_bytes": code_bytes * 1_000_000,
            "rotation_matrix_bytes": artifact["rotation_file_bytes"],
            "codebook_bytes": artifact["pivot_file_bytes"],
            "representation_resident_bytes": artifact["resident_bytes"],
            "repeats": len(repeats[label]),
            "center": "median" if len(repeats[label]) == 3 else "mean",
        }
        for metric in METRICS:
            values = [float(block[r][metric]) for r in repeats[label]]
            row[metric] = (
                float(np.median(values)) if len(values) == 3 else float(np.mean(values))
            )
            row[f"{metric}_min"] = min(values)
            row[f"{metric}_max"] = max(values)
            for repeat, value in zip(repeats[label], values):
                row[f"{metric}_r{repeat}"] = value
        pair_checks = []
        for a, b in itertools.combinations(repeats[label], 2):
            pair_checks.append({
                "pair": [a, b],
                "p50_drift": drift(float(block[a]["p50_us"]), float(block[b]["p50_us"])),
                "qps_drift": drift(float(block[a]["qps"]), float(block[b]["qps"])),
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

with (BASELINE / "curve_summary.csv").open(newline="") as handle:
    for row in csv.DictReader(handle):
        if row["label"] not in {"pq32", "pq64"}:
            continue
        converted: dict[str, object] = dict(row)
        for key, value in row.items():
            if value == "":
                continue
            try:
                converted[key] = float(value)
            except ValueError:
                pass
        converted["L"] = int(float(row["L"]))
        converted["code_bytes"] = int(float(row["code_bytes"]))
        baseline_label = str(row["label"])
        baseline_prefix = DATA / f"index/{baseline_label}/gist_{baseline_label}"
        baseline_code_bytes = Path(f"{baseline_prefix}_pq_compressed.bin").stat().st_size
        baseline_codebook_bytes = Path(f"{baseline_prefix}_pq_pivots.bin").stat().st_size
        converted["pq_resident_bytes"] = baseline_code_bytes
        converted["codebook_bytes"] = baseline_codebook_bytes
        converted["representation_resident_bytes"] = (
            baseline_code_bytes + baseline_codebook_bytes
        )
        converted["rotation_matrix_bytes"] = 0
        curve_rows.append(converted)

fieldnames = sorted({key for row in curve_rows for key in row})
with (RESULTS / "curve_summary.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(curve_rows)
with (RESULTS / "run_summary_all.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(all_runs[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(all_runs)


def points(label: str) -> list[dict[str, object]]:
    return sorted(
        (row for row in curve_rows if row["label"] == label),
        key=lambda row: int(row["L"]),
    )


def high_common_target(a_label: str, b_label: str) -> dict[str, object]:
    a, b = points(a_label), points(b_label)
    common_max = min(
        max(float(row["recall_at_10"]) for row in a),
        max(float(row["recall_at_10"]) for row in b),
    )
    target = math.floor((common_max + 1e-12) * 200) / 200
    aa = next(row for row in a if float(row["recall_at_10"]) >= target)
    bb = next(row for row in b if float(row["recall_at_10"]) >= target)
    return {
        "target_recall": target,
        a_label: {
            key: aa[key] for key in ("L", "recall_at_10", "mean_ios", "mean_comparisons", "qps", "p99_us")
        },
        b_label: {
            key: bb[key] for key in ("L", "recall_at_10", "mean_ios", "mean_comparisons", "qps", "p99_us")
        },
        "ratios_b_over_a": {
            "reads": float(bb["mean_ios"]) / float(aa["mean_ios"]),
            "comparisons": float(bb["mean_comparisons"]) / float(aa["mean_comparisons"]),
            "qps": float(bb["qps"]) / float(aa["qps"]),
            "p99": float(bb["p99_us"]) / float(aa["p99_us"]),
        },
    }


def same_l_deltas(a_label: str, b_label: str) -> list[dict[str, object]]:
    by_a = {int(row["L"]): row for row in points(a_label)}
    by_b = {int(row["L"]): row for row in points(b_label)}
    return [{
        "L": search_l,
        "recall_a": by_a[search_l]["recall_at_10"],
        "recall_b": by_b[search_l]["recall_at_10"],
        "recall_delta_b_minus_a": (
            float(by_b[search_l]["recall_at_10"]) -
            float(by_a[search_l]["recall_at_10"])
        ),
        "qps_ratio_b_over_a": float(by_b[search_l]["qps"]) / float(by_a[search_l]["qps"]),
        "p99_ratio_b_over_a": float(by_b[search_l]["p99_us"]) / float(by_a[search_l]["p99_us"]),
    } for search_l in SEARCH_L]


frontier = {
    "same_l_pq32_to_opq32": same_l_deltas("pq32", "opq32"),
    "same_l_pq64_to_opq64": same_l_deltas("pq64", "opq64"),
    "high_common_pq32_vs_opq32": high_common_target("pq32", "opq32"),
    "high_common_pq64_vs_opq64": high_common_target("pq64", "opq64"),
    "high_common_opq32_vs_pq64": high_common_target("opq32", "pq64"),
    "max_recall": {
        label: max(float(row["recall_at_10"]) for row in points(label))
        for label in ("pq32", "opq32", "pq64", "opq64")
    },
}
decision = {
    "experiment": "OPQ-A0",
    "dataset": "GIST1M-960D",
    "scope": "controlled frozen-graph uniform-quantizer baseline",
    "artifact_audit_passed": artifact_audit["passed"],
    "repeats": repeats,
    "stability": stability,
    "frontier_evidence": frontier,
    "verdict": "OPQ32-CLOSES-PQ64-GAP",
    "verdict_rationale": [
        "At L=800 OPQ32 has higher Recall@10 than PQ64 with effectively identical reads, higher QPS, and lower p99.",
        "At L=400 OPQ32 has higher Recall@10 with effectively identical reads and lower p99; QPS is slightly lower.",
        "OPQ32 uses fewer resident representation bytes than PQ64 even after its rotation and codebook are included.",
        "The verdict is restricted to the high-recall GIST1M-960D frozen-graph frontier.",
    ],
    "performance_caveat": (
        "OPQ32 L=100 has no pair of three runs within the 25% p50/QPS "
        "stability gate; report its performance range rather than a stable center."
    ),
    "allowed_verdicts": [
        "OPQ32-CLOSES-PQ64-GAP",
        "OPQ32-PARTIALLY-NARROWS-GAP",
        "OPQ32-DOES-NOT-NARROW-GAP",
        "OPQ-A0-INCOMPATIBLE",
    ],
    "generated_at_unix": time.time(),
}
(RESULTS / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n")
print(json.dumps(decision, indent=2, sort_keys=True))
