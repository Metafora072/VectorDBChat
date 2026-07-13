#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

import numpy as np


PATTERN = re.compile(r"fixed_L(\d+)_W(\d+)_B(\d+)\.csv$")
NUMERIC = {
    "qid", "K", "L", "width", "B", "total_us", "traversal_us", "exposed_vector_tail_us",
    "pq_cpu_us", "exact_cpu_us", "graph_io_wait_us", "vector_io_wait_us", "graph_ios", "vector_ios",
    "expanded", "discovered", "heap_replacements", "heap_full_expanded", "stability_expanded",
    "stability_us", "stability_position", "trigger_remaining_fraction", "io_poll_rounds",
    "prefetched_candidates", "useful_prefetched_candidates", "wasted_prefetch_candidates",
    "unfinished_vector_pages_at_traversal_end", "ready_vector_pages_at_traversal_end", "prefetch_overlap_us",
    "final_no_replace_streak", "rerank_batches", "prefetch_benefit_ratio", "recall",
}


def load(path: Path, drop_first: int = 5) -> dict[str, np.ndarray]:
    rows = list(csv.DictReader(path.open()))[drop_first:]
    return {key: np.asarray([float(row[key]) for row in rows]) for key in NUMERIC if key in rows[0]}


def pct(a: np.ndarray, q: float) -> float:
    return float(np.percentile(a, q, method="higher"))


def ranks(a: np.ndarray) -> np.ndarray:
    order = np.argsort(a, kind="stable")
    out = np.empty_like(a, dtype=float)
    out[order] = np.arange(len(a), dtype=float)
    return out / max(1, len(a) - 1)


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    if np.std(a) == 0 or np.std(b) == 0:
        return 0.0
    return float(np.corrcoef(ranks(a), ranks(b))[0, 1])


def aggregate(d: dict[str, np.ndarray]) -> dict[str, float]:
    return {
        "n": int(len(d["qid"])),
        "recall_mean": float(np.mean(d["recall"])),
        "latency_mean_us": float(np.mean(d["total_us"])),
        "latency_p50_us": pct(d["total_us"], 50),
        "latency_p95_us": pct(d["total_us"], 95),
        "latency_p99_us": pct(d["total_us"], 99),
        "traversal_mean_us": float(np.mean(d["traversal_us"])),
        "tail_mean_us": float(np.mean(d["exposed_vector_tail_us"])),
        "tail_p95_us": pct(d["exposed_vector_tail_us"], 95),
        "tail_p99_us": pct(d["exposed_vector_tail_us"], 99),
        "graph_ios_mean": float(np.mean(d["graph_ios"])),
        "vector_ios_mean": float(np.mean(d["vector_ios"])),
        "trigger_rate": float(np.mean(d["stability_expanded"] > 0)),
        "stability_position_mean": float(np.mean(d["stability_position"])),
        "remaining_fraction_mean": float(np.mean(d["trigger_remaining_fraction"])),
        "ready_vector_pages_mean": float(np.mean(d["ready_vector_pages_at_traversal_end"])),
        "unfinished_vector_pages_mean": float(np.mean(d["unfinished_vector_pages_at_traversal_end"])),
        "prefetch_overlap_sum_mean_us": float(np.mean(d["prefetch_overlap_us"])),
        "wasted_prefetch_candidates_mean": float(np.mean(d["wasted_prefetch_candidates"])),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--r1", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    data: dict[tuple[int, int, int], dict[str, np.ndarray]] = {}
    aggregates = []
    for path in sorted(args.r1.glob("*.csv")):
        m = PATTERN.match(path.name)
        if not m:
            continue
        key = tuple(map(int, m.groups()))
        d = load(path)
        data[key] = d
        aggregates.append({"L": key[0], "W": key[1], "B": key[2], **aggregate(d)})
    write_csv(args.out / "r1_aggregate.csv", aggregates)

    representative = {b: data[(100, 4, b)] for b in (10, 20, 40, 80)}
    base = representative[80]
    difficulty = np.mean(
        np.vstack([ranks(base[k]) for k in ("graph_ios", "discovered", "heap_replacements", "total_us")]), axis=0
    )
    edges = np.quantile(difficulty, [0.25, 0.5, 0.75])
    buckets = np.digitize(difficulty, edges, right=True)

    difficulty_rows = []
    for b, d in representative.items():
        for q in range(4):
            mask = buckets == q
            difficulty_rows.append({
                "B": b,
                "difficulty_quartile": q + 1,
                "n": int(mask.sum()),
                "recall_mean": float(np.mean(d["recall"][mask])),
                "latency_p95_us": pct(d["total_us"][mask], 95),
                "tail_mean_us": float(np.mean(d["exposed_vector_tail_us"][mask])),
                "tail_p95_us": pct(d["exposed_vector_tail_us"][mask], 95),
                "trigger_rate": float(np.mean(d["stability_expanded"][mask] > 0)),
                "stability_position_mean": float(np.mean(d["stability_position"][mask])),
                "graph_ios_mean": float(np.mean(d["graph_ios"][mask])),
                "heap_replacements_mean": float(np.mean(d["heap_replacements"][mask])),
            })
    write_csv(args.out / "r1_difficulty_quartiles.csv", difficulty_rows)

    # Per query, choose the fastest B whose recall is no lower than the B=80
    # reference for that same query.  This is deliberately a generous offline
    # selector and therefore an upper bound on query-adaptive tuning.
    choices = []
    bs = (10, 20, 40, 80)
    for i in range(len(base["qid"])):
        feasible = [b for b in bs if representative[b]["recall"][i] + 1e-12 >= base["recall"][i]]
        best = min(feasible, key=lambda b: representative[b]["total_us"][i])
        choices.append(best)
    choices = np.asarray(choices)
    choice_rows = []
    for q in range(4):
        mask = buckets == q
        for b in bs:
            choice_rows.append({
                "difficulty_quartile": q + 1,
                "B": b,
                "count": int(np.sum(choices[mask] == b)),
                "fraction": float(np.mean(choices[mask] == b)),
            })
    write_csv(args.out / "r1_offline_best_b.csv", choice_rows)

    corr_rows = []
    for b, d in representative.items():
        for metric in ("stability_position", "exposed_vector_tail_us", "total_us", "recall"):
            corr_rows.append({"B": b, "metric": metric, "spearman_vs_difficulty": spearman(difficulty, d[metric])})
    write_csv(args.out / "r1_correlations.csv", corr_rows)

    summary = {
        "configs": len(data),
        "queries_per_config_after_warmup": len(base["qid"]),
        "difficulty_edges": edges.tolist(),
        "offline_best_b_distribution": {str(b): int(np.sum(choices == b)) for b in bs},
        "representative": {str(b): aggregate(d) for b, d in representative.items()},
        "spearman_B40_difficulty_vs_stability": spearman(difficulty, representative[40]["stability_position"]),
        "spearman_B40_difficulty_vs_tail": spearman(difficulty, representative[40]["exposed_vector_tail_us"]),
        "spearman_B80_difficulty_vs_tail": spearman(difficulty, representative[80]["exposed_vector_tail_us"]),
    }
    (args.out / "r1_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
