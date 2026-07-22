#!/usr/bin/env python3
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/graph_aging_a0")
RESULTS = ROOT / "results"


def load(name):
    path = RESULTS / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def stats(values):
    values = list(values)
    if not values:
        return {"n": 0, "mean": None, "std": None, "variance": None, "ci95": None, "min": None, "max": None}
    m = statistics.mean(values)
    if len(values) == 1:
        return {"n": 1, "mean": m, "std": 0.0, "variance": 0.0, "ci95": 0.0, "min": m, "max": m}
    sd = statistics.stdev(values)
    t95 = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776}.get(len(values), 1.96)
    return {
        "n": len(values), "mean": m, "std": sd, "variance": sd * sd,
        "ci95": t95 * sd / math.sqrt(len(values)), "min": min(values), "max": max(values),
    }


def aggregate(rows, keys):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in keys)].append(row)
    result = {}
    metrics = [
        "recall_at_10", "distance_calcs_mean", "distance_calcs_p50", "distance_calcs_p95",
        "distance_calcs_p99", "visited_nodes_mean", "visited_nodes_p50", "visited_nodes_p95",
        "visited_nodes_p99", "edge_jaccard_vs_g0", "edge_count", "build_seconds", "update_seconds",
    ]
    for key, items in groups.items():
        result["|".join(map(str, key))] = {metric: stats(item[metric] for item in items) for metric in metrics}
    return result


def main():
    g0_rows = load("a01_full.jsonl")
    g0 = next(row for row in g0_rows if row["label"] == "g0_identity")
    static_rows = load("static_seeds.jsonl")
    a01_rows = load("a01_seeds.jsonl")
    a02_rows = load("a02_path2.jsonl") + load("a02_path3.jsonl")
    static_summary = aggregate(static_rows, ["experiment"])
    a01_summary = aggregate(a01_rows, ["checkpoint"])
    a02_summary = aggregate(a02_rows, ["label"])
    build_recall = stats(row["recall_at_10"] for row in static_rows)
    variance_comparison = {}
    for checkpoint in (1, 10, 100):
        rows = [row for row in a01_rows if row["checkpoint"] == checkpoint]
        if not rows:
            continue
        recall = stats(row["recall_at_10"] for row in rows)
        variance_comparison[str(checkpoint)] = {
            "recall": recall,
            "delta_vs_g0_pp": (recall["mean"] - g0["recall_at_10"]) * 100,
            "history_to_build_variance_ratio": (
                recall["variance"] / build_recall["variance"] if build_recall["variance"] else None
            ),
            "build_recall": build_recall,
        }
    output = {
        "g0": g0,
        "raw": {"static": static_rows, "a01": a01_rows, "a02": a02_rows},
        "aggregate": {"static": static_summary, "a01": a01_summary, "a02": a02_summary},
        "variance_comparison": variance_comparison,
    }
    (RESULTS / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output["variance_comparison"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
