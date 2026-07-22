#!/usr/bin/env python3
"""Analyze P10 paths, costs, recall, and preregistered gates."""

from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from pathlib import Path

import numpy as np

ROOT = Path("/home/ubuntu/pz/VectorDB/chat")
WORK = ROOT / "codex/work/2026-07-23/p10_pq_corridor_a0"
RESULTS = WORK / "results"
TRACES = WORK / "traces"
QUERY_PATH = ROOT / "codex/work/2026-07-22/p07_page_bonus_a0/queries_1000.bin"
FULL_PATH = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin")
GT_PATH = ROOT / "codex/work/2026-07-22/p07_page_bonus_a0/results/gt_1000_top100"

parser = argparse.ArgumentParser()
parser.add_argument("--tag", default="", help="filename prefix, for example pq16_")
args = parser.parse_args()
TAG = args.tag

BASE_VARIANTS = [
    "pq_l100_w2", "exact_l100_w2", "early1_l100_w2", "early2_l100_w2",
    "early4_l100_w2", "early8_l100_w2", "late4_l100_w2",
    "pq_l100_w4", "pq_l150_w4", "pq_l200_w4",
]
VARIANTS = [TAG + name for name in BASE_VARIANTS]


def variant(name: str) -> str:
    return TAG + name


def load_bin(path: Path, dtype: np.dtype) -> np.ndarray:
    with path.open("rb") as handle:
        rows, dim = struct.unpack("<II", handle.read(8))
    return np.memmap(path, dtype=dtype, mode="r", offset=8, shape=(rows, dim))


def load_metrics(name: str) -> list[dict[str, str]]:
    with (RESULTS / f"{name}.csv").open(newline="") as handle:
        return list(csv.DictReader(handle))


def load_trace(name: str) -> dict[int, dict[str, object]]:
    out: dict[int, dict[str, object]] = {}
    with (TRACES / f"{name}.tsv").open() as handle:
        for line in handle:
            qid_s, expanded_s, visited_s = line.rstrip("\n").split("\t")
            expanded = []
            scores = []
            payload = expanded_s.removeprefix("e=")
            if payload:
                for token in payload.split(","):
                    node, score = token.split(":")
                    expanded.append(int(node))
                    scores.append(float(score))
            visited_payload = visited_s.removeprefix("v=")
            visited = set(map(int, visited_payload.split(","))) if visited_payload else set()
            out[int(qid_s)] = {"expanded": expanded, "scores": scores, "visited": visited}
    return out


def jaccard(left: set, right: set) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def path_metrics(base: dict[str, object], other: dict[str, object]) -> dict[str, float]:
    a = base["expanded"]
    b = other["expanded"]
    limit = min(len(a), len(b))
    first = next((i for i in range(limit) if a[i] != b[i]), limit)
    if first == limit and len(a) != len(b):
        first = limit
    suffix = set(a[first:])
    reentry = next((i - first for i in range(first, len(b)) if b[i] in suffix), math.nan)
    bigram_a = set(zip(a, a[1:]))
    bigram_b = set(zip(b, b[1:]))
    return {
        "first_divergence": float(first),
        "expanded_jaccard": jaccard(set(a), set(b)),
        "order_bigram_jaccard": jaccard(bigram_a, bigram_b),
        "visited_jaccard": jaccard(base["visited"], other["visited"]),
        "reentry_steps": float(reentry),
    }


def quartiles(values: np.ndarray) -> np.ndarray:
    edges = np.quantile(values, [0.25, 0.5, 0.75])
    return np.digitize(values, edges, right=True)


with GT_PATH.open("rb") as handle:
    gt_n, gt_k = struct.unpack("<II", handle.read(8))
gt_ids = np.memmap(GT_PATH, dtype=np.uint32, mode="r", offset=8, shape=(gt_n, gt_k))
gt_dists = np.memmap(
    GT_PATH, dtype=np.float32, mode="r", offset=8 + gt_n * gt_k * 4, shape=(gt_n, gt_k)
)
queries = np.asarray(load_bin(QUERY_PATH, np.float32))
with FULL_PATH.open("rb") as handle:
    full_n, full_d = struct.unpack("<II", handle.read(8))
full = np.memmap(FULL_PATH, dtype=np.float32, mode="r", offset=8, shape=(full_n, full_d))

metrics = {name: load_metrics(name) for name in VARIANTS}
traces = {name: load_trace(name) for name in VARIANTS}

recall_per_query: dict[str, np.ndarray] = {}
summary: dict[str, dict[str, float]] = {}
for name in VARIANTS:
    ids = np.array([[int(row[f"id{k}"]) for k in range(10)] for row in metrics[name]], dtype=np.uint32)
    recall = np.array([len(set(ids[q]) & set(gt_ids[q, :10])) / 10.0 for q in range(len(ids))])
    recall_per_query[name] = recall
    ios = np.array([float(row["n_ios"]) for row in metrics[name]])
    exact_reads = np.array([float(row["n_exact_nav_reads"]) for row in metrics[name]])
    summary[name] = {
        "recall_at_10": float(recall.mean()),
        "mean_latency_us": float(np.mean([float(row["total_us"]) for row in metrics[name]])),
        "mean_page_reads": float(ios.mean()),
        "mean_comparisons": float(np.mean([float(row["n_cmps"]) for row in metrics[name]])),
        "mean_hops": float(np.mean([float(row["n_hops"]) for row in metrics[name]])),
        "mean_exact_nav_reads": float(exact_reads.mean()),
        "mean_bytes_touched": float(np.mean(ios * 4096.0 + exact_reads * full_d * 4.0)),
    }

base_trace = traces[variant("pq_l100_w2")]
path_summary: dict[str, dict[str, float]] = {}
per_query_path: dict[str, dict[str, np.ndarray]] = {}
for name in VARIANTS[1:]:
    rows = [path_metrics(base_trace[q], traces[name][q]) for q in range(1000)]
    per_query_path[name] = {key: np.array([row[key] for row in rows]) for key in rows[0]}
    path_summary[name] = {}
    for key, vals in per_query_path[name].items():
        finite = vals[np.isfinite(vals)]
        path_summary[name][f"median_{key}"] = float(np.median(finite)) if len(finite) else math.nan
        path_summary[name][f"mean_{key}"] = float(np.mean(finite)) if len(finite) else math.nan
    path_summary[name]["reentry_rate"] = float(np.isfinite(per_query_path[name]["reentry_steps"]).mean())

# Baseline PQ score residual on exactly the nodes whose scores drove expansion.
pq_residual = np.zeros(1000, dtype=np.float64)
for q in range(1000):
    ids = np.array(base_trace[q]["expanded"], dtype=np.int64)
    pq_scores = np.array(base_trace[q]["scores"], dtype=np.float64)
    exact_scores = np.sum((np.asarray(full[ids], dtype=np.float64) - queries[q]) ** 2, axis=1)
    pq_residual[q] = np.median(np.abs(pq_scores - exact_scores) / np.maximum(exact_scores, 1e-9))

topk_margin = (gt_dists[:, 10] - gt_dists[:, 9]) / np.maximum(gt_dists[:, 9], 1e-9)
groups = {"pq_residual": quartiles(pq_residual), "topk_margin": quartiles(topk_margin)}
grouped: dict[str, dict[str, dict[str, float]]] = {}
base_recall = recall_per_query[variant("pq_l100_w2")]
for group_name, labels in groups.items():
    grouped[group_name] = {}
    for quartile in range(4):
        mask = labels == quartile
        grouped[group_name][f"q{quartile + 1}"] = {
            name: (
                float((recall_per_query[name][mask] - base_recall[mask]).mean())
                if np.any(mask)
                else math.nan
            )
            for name in VARIANTS[1:]
        }

pq_recall = summary[variant("pq_l100_w2")]["recall_at_10"]
exact_gain = summary[variant("exact_l100_w2")]["recall_at_10"] - pq_recall
group_gains = [
    grouped[axis][quartile][variant("exact_l100_w2")]
    for axis in grouped for quartile in grouped[axis]
]
max_group_gain = max(value for value in group_gains if math.isfinite(value))
no_consequence = exact_gain < 0.005 and max_group_gain < 0.02

exact_reads = summary[variant("exact_l100_w2")]["mean_exact_nav_reads"]
early_candidates = [variant(f"early{h}_l100_w2") for h in (1, 2, 4, 8)]
early_pass = []
for name in early_candidates:
    gain = summary[name]["recall_at_10"] - pq_recall
    read_ratio = summary[name]["mean_exact_nav_reads"] / exact_reads if exact_reads else math.inf
    if exact_gain > 0 and gain >= 0.5 * exact_gain and read_ratio <= 0.25:
        early_pass.append(name)

controls = [variant(name) for name in ("late4_l100_w2", "pq_l100_w4", "pq_l150_w4", "pq_l200_w4")]
best_early = max(early_candidates, key=lambda name: summary[name]["recall_at_10"])
early_cost = summary[best_early]["mean_bytes_touched"]
nonunique = any(
    summary[control]["mean_bytes_touched"] <= early_cost
    and summary[best_early]["recall_at_10"] - summary[control]["recall_at_10"] <= 0.0025
    for control in controls
)

if no_consequence:
    verdict = "KILL-P10-NO-CONSEQUENCE"
elif not early_pass:
    verdict = "KILL-P10-NO-EARLY-LOCALITY"
elif nonunique:
    verdict = "HOLD-P10-NONUNIQUE"
else:
    verdict = "PASS-P10-A0"


def paired_bootstrap(left: str, right: str, seed: int) -> dict[str, float]:
    delta = recall_per_query[left] - recall_per_query[right]
    rng = np.random.default_rng(seed)
    bootstrap_means = np.empty(10000, dtype=np.float64)
    for i in range(len(bootstrap_means)):
        bootstrap_means[i] = rng.choice(delta, size=len(delta), replace=True).mean()
    return {
        "mean_delta_pp": float(100.0 * delta.mean()),
        "ci95_low_pp": float(100.0 * np.quantile(bootstrap_means, 0.025)),
        "ci95_high_pp": float(100.0 * np.quantile(bootstrap_means, 0.975)),
        "fraction_queries_positive": float(np.mean(delta > 0)),
        "fraction_queries_negative": float(np.mean(delta < 0)),
    }


paired = {
    "exact_minus_pq": paired_bootstrap(variant("exact_l100_w2"), variant("pq_l100_w2"), 20260723),
    "early8_minus_pq": paired_bootstrap(variant("early8_l100_w2"), variant("pq_l100_w2"), 20260724),
    "early8_minus_l150w4": paired_bootstrap(
        variant("early8_l100_w2"), variant("pq_l150_w4"), 20260725
    ),
    "l200w4_minus_early8": paired_bootstrap(
        variant("pq_l200_w4"), variant("early8_l100_w2"), 20260726
    ),
}

output = {
    "verdict": verdict,
    "gate_values": {
        "aggregate_exact_gain_pp": 100.0 * exact_gain,
        "max_quartile_exact_gain_pp": 100.0 * max_group_gain,
        "early_variants_passing_efficiency_gate": early_pass,
        "best_early_by_recall": best_early,
        "nonunique_control_at_no_greater_byte_cost": nonunique,
    },
    "variant_summary": summary,
    "path_summary_vs_pq": path_summary,
    "paired_bootstrap": paired,
    "grouped_recall_delta": grouped,
    "diagnostic": {
        "pq_residual_median": float(np.median(pq_residual)),
        "pq_residual_p90": float(np.quantile(pq_residual, 0.9)),
        "topk_margin_median": float(np.median(topk_margin)),
    },
}
suffix = TAG.rstrip("_")
analysis_name = f"analysis_summary_{suffix}.json" if suffix else "analysis_summary.json"
table_name = f"variant_summary_{suffix}.csv" if suffix else "variant_summary.csv"
(RESULTS / analysis_name).write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")

with (RESULTS / table_name).open("w", newline="") as handle:
    fields = ["variant", *next(iter(summary.values())).keys()]
    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for name in VARIANTS:
        writer.writerow({"variant": name, **summary[name]})

print(json.dumps(output["gate_values"], indent=2, sort_keys=True))
print(verdict)
