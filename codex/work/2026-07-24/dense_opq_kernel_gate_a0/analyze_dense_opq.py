#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import json
import math
import struct
import time
from pathlib import Path

import numpy as np

WORK = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/dense_opq_kernel_gate_a0")
DATA = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724")
RESULTS = WORK / "results"
SEARCH_L = (50, 100, 200, 400, 800)
IMPLS = ("v0", "v1", "v2")
REPEATS = (1, 2)

with (DATA / "converted/gist_gt100.truthset").open("rb") as handle:
    nqueries, gt_k = struct.unpack("<II", handle.read(8))
gt_ids = np.memmap(
    DATA / "converted/gist_gt100.truthset",
    dtype="<u4", mode="r", offset=8, shape=(nqueries, gt_k),
)


def read_summary(impl: str, repeat: int) -> list[dict[str, str]]:
    with (RESULTS / f"full_{impl}_r{repeat}_summary.csv").open(newline="") as handle:
        return list(csv.DictReader(handle))


def read_raw(impl: str, repeat: int) -> list[dict[str, str]]:
    with gzip.open(RESULTS / f"per_query/full_{impl}_r{repeat}.csv.gz", "rt", newline="") as handle:
        return list(csv.DictReader(handle))


def recall_at_10(rows: list[dict[str, str]], search_l: int) -> float:
    block = [row for row in rows if int(row["L"]) == search_l]
    if len(block) != nqueries:
        raise ValueError(f"{search_l}: expected {nqueries}, got {len(block)}")
    recalls = []
    for row in block:
        qid = int(row["qid"])
        returned = {int(row[f"id{k}"]) for k in range(10)}
        recalls.append(len(returned & set(map(int, gt_ids[qid, :10]))) / 10)
    return float(np.mean(recalls))


def pct(values: list[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=float), q))


kernel_rows = []
for line in (RESULTS / "rotation_kernel_bench.jsonl").read_text().splitlines():
    if line.strip():
        kernel_rows.append(json.loads(line))

perf = {"available": False}
perf_file = RESULTS / "rotation_kernel_bench.perf.txt"
if perf_file.exists():
    text = perf_file.read_text(errors="replace")
    cycles = instructions = None
    for line in text.splitlines():
        parts = line.split(",")
        if len(parts) >= 3 and parts[2] == "cycles":
            try:
                cycles = int(parts[0])
            except ValueError:
                pass
        if len(parts) >= 3 and parts[2] == "instructions":
            try:
                instructions = int(parts[0])
            except ValueError:
                pass
    if cycles is not None and instructions is not None:
        perf = {"available": True, "cycles": cycles, "instructions": instructions, "ipc": instructions / cycles}
    else:
        perf = {"available": False, "raw": text[-800:]}

curve_rows: list[dict[str, object]] = []
for impl in IMPLS:
    summaries = {repeat: read_summary(impl, repeat) for repeat in REPEATS}
    raws = {repeat: read_raw(impl, repeat) for repeat in REPEATS}
    for search_l in SEARCH_L:
        raw_blocks = {
            repeat: [row for row in raws[repeat] if int(row["L"]) == search_l]
            for repeat in REPEATS
        }
        summary_blocks = {
            repeat: next(row for row in summaries[repeat] if int(row["L"]) == search_l)
            for repeat in REPEATS
        }
        rotation_values = {
            repeat: [float(row["rotation_us"]) for row in raw_blocks[repeat]]
            for repeat in REPEATS
        }
        total_values = {
            repeat: [float(row["total_us"]) for row in raw_blocks[repeat]]
            for repeat in REPEATS
        }
        per_repeat = []
        for repeat in REPEATS:
            total_p50 = pct(total_values[repeat], 0.50)
            rotation_p50 = pct(rotation_values[repeat], 0.50)
            zero_p50 = pct(
                [max(t - r, 0.0) for t, r in zip(total_values[repeat], rotation_values[repeat])],
                0.50,
            )
            per_repeat.append({
                "repeat": repeat,
                "recall_at_10": recall_at_10(raws[repeat], search_l),
                "qps": float(summary_blocks[repeat]["qps"]),
                "reads": float(summary_blocks[repeat]["mean_ios"]),
                "comparisons": float(summary_blocks[repeat]["mean_comparisons"]),
                "p50_us": total_p50,
                "p95_us": pct(total_values[repeat], 0.95),
                "p99_us": pct(total_values[repeat], 0.99),
                "rotation_mean_us": float(np.mean(rotation_values[repeat])),
                "rotation_p50_us": rotation_p50,
                "rotation_p95_us": pct(rotation_values[repeat], 0.95),
                "rotation_share_of_p50": rotation_p50 / total_p50,
                "zero_rotation_p50_us": zero_p50,
                "zero_rotation_speedup_upper_bound": total_p50 / max(zero_p50, 1e-9),
            })
        row: dict[str, object] = {"impl": impl, "L": search_l, "repeats": 2}
        for metric in (
            "recall_at_10", "qps", "reads", "comparisons", "p50_us", "p95_us", "p99_us",
            "rotation_mean_us", "rotation_p50_us", "rotation_p95_us", "rotation_share_of_p50",
            "zero_rotation_p50_us", "zero_rotation_speedup_upper_bound",
        ):
            values = [float(item[metric]) for item in per_repeat]
            row[metric] = float(np.mean(values))
            row[f"{metric}_r1"] = values[0]
            row[f"{metric}_r2"] = values[1]
        curve_rows.append(row)

fieldnames = sorted({key for row in curve_rows for key in row})
with (RESULTS / "curve_summary.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(curve_rows)

by_impl_l = {(row["impl"], int(row["L"])): row for row in curve_rows}
target_ls = [200, 400, 800]
optimized_rotation_small = all(
    float(by_impl_l[("v2", search_l)]["rotation_share_of_p50"]) < 0.08 and
    float(by_impl_l[("v2", search_l)]["zero_rotation_speedup_upper_bound"]) < 1.10
    for search_l in target_ls
)
v2_recall_ok = all(
    math.isclose(
        float(by_impl_l[("v0", search_l)]["recall_at_10"]),
        float(by_impl_l[("v2", search_l)]["recall_at_10"]),
        rel_tol=0.0,
        abs_tol=0.002,
    )
    for search_l in SEARCH_L
)

decision = {
    "experiment": "DENSE-OPQ-KERNEL-GATE-A0",
    "dataset": "GIST1M-960D OPQ32 frozen graph",
    "threading": {
        "search_threads": 1,
        "MKL_NUM_THREADS": 1,
        "OMP_NUM_THREADS": 1,
        "OPENBLAS_NUM_THREADS": 1,
        "blas_backend": "system libblas, DiskANN_USE_SYSTEM_BLAS=ON",
    },
    "kernel_rows": kernel_rows,
    "perf": perf,
    "v2_recall_matches_v0": v2_recall_ok,
    "high_recall_v2_rotation_small": optimized_rotation_small,
    "verdict": (
        "KILL-UNOPTIMIZED-OPQ-AS-RESEARCH-MOTIVATION"
        if optimized_rotation_small and v2_recall_ok
        else "HOLD-DENSE-OPQ-BOTTLENECK"
    ),
    "structured_fast_opq_priority": (
        "LOW/KILL" if optimized_rotation_small and v2_recall_ok else "HOLD"
    ),
    "generated_at_unix": time.time(),
}
(RESULTS / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n")
print(json.dumps(decision, indent=2, sort_keys=True))
