#!/usr/bin/env python3
"""A-1: candidate-survival frontier for speculative result payload reads."""

from __future__ import annotations

import argparse
import heapq
import json
import time
from pathlib import Path

import numpy as np


def read_fvecs(path: Path, limit: int | None = None) -> np.ndarray:
    raw = np.memmap(path, dtype=np.int32, mode="r")
    d = int(raw[0])
    rows = raw.size // (d + 1)
    if limit is not None:
        rows = min(rows, limit)
    shaped = np.memmap(path, dtype=np.float32, mode="r", shape=(rows, d + 1))
    return np.asarray(shaped[:, 1:], dtype=np.float32)


def read_adjacency(path: Path, n: int) -> list[np.ndarray]:
    graph: list[np.ndarray] = [np.empty(0, dtype=np.int32) for _ in range(n)]
    with path.open() as f:
        for line in f:
            values = np.fromstring(line, dtype=np.int64, sep=" ")
            if values.size <= 1:
                continue
            node = int(values[0])
            if node < n:
                graph[node] = values[1:][values[1:] < n].astype(np.int32)
    return graph


def graph_trace(
    docs: np.ndarray,
    graph: list[np.ndarray],
    query: np.ndarray,
    entry: int,
    expansions: int,
    k: int,
    policies: list[tuple[int, int]],
) -> tuple[np.ndarray, dict, dict[int, int]]:
    n = len(docs)
    seen = np.zeros(n, dtype=bool)
    expanded = np.zeros(n, dtype=bool)
    distance: dict[int, float] = {}
    first_seen: dict[int, int] = {}
    frontier: list[tuple[float, int]] = []

    d0 = float(np.linalg.norm(docs[entry] - query))
    heapq.heappush(frontier, (d0, entry))
    seen[entry] = True
    distance[entry] = d0
    first_seen[entry] = 0
    policy_state = {
        (step, width): {"prefetched": set(), "first": {}}
        for step, width in policies
    }

    actual_expansions = 0
    for turn in range(1, expansions + 1):
        while frontier and expanded[frontier[0][1]]:
            heapq.heappop(frontier)
        if not frontier:
            break
        _, node = heapq.heappop(frontier)
        expanded[node] = True
        actual_expansions = turn
        neighbors = graph[node]
        unseen = neighbors[~seen[neighbors]] if neighbors.size else neighbors
        if unseen.size:
            vals = np.linalg.norm(docs[unseen] - query, axis=1)
            for child, value in zip(unseen.tolist(), vals.tolist()):
                seen[child] = True
                distance[child] = float(value)
                first_seen[child] = turn
                heapq.heappush(frontier, (float(value), int(child)))

        due = [(step, width) for step, width in policies if turn % step == 0]
        if due:
            max_width = max(width for _, width in due)
            current = sorted(distance, key=distance.get)[: max_width * k]
            for step, width in due:
                state = policy_state[(step, width)]
                for candidate in current[: width * k]:
                    state["prefetched"].add(candidate)
                    state["first"].setdefault(candidate, turn)

    final = np.asarray(sorted(distance, key=distance.get)[:k], dtype=np.int32)
    metrics = {}
    final_set = set(final.tolist())
    for (step, width), state in policy_state.items():
        prefetched = state["prefetched"]
        first = state["first"]
        hit = len(final_set & prefetched)
        entry = {
            "prefetch_count": len(prefetched),
            "final_coverage": hit / k,
            "wasted_fraction": (len(prefetched - final_set) / len(prefetched)) if prefetched else 0.0,
            "all_final_prefetched_before_end": hit == k,
        }
        for io_work in (10, 25, 50, 100):
            ready = max(first.get(item, actual_expansions) + io_work for item in final_set)
            baseline = actual_expansions + io_work
            entry[f"payload_complete_saving_at_io_{io_work}"] = max(0, baseline - ready)
        metrics[f"step_{step}_width_{width}k"] = entry
    return final, metrics, first_seen


def aggregate(records: list[dict]) -> dict:
    keys = sorted(records[0])
    out = {}
    for key in keys:
        values = np.asarray([r[key] for r in records], dtype=float)
        out[key] = {
            "mean": float(values.mean()),
            "p10": float(np.quantile(values, 0.10)),
            "p50": float(np.quantile(values, 0.50)),
            "p90": float(np.quantile(values, 0.90)),
        }
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    data = Path("/home/ubuntu/pz/VectorDB/data/VectorDB")
    p.add_argument("--base", type=Path, default=data / "datasets/synthetic_128d_100k/base.fvecs")
    p.add_argument("--queries", type=Path, default=data / "datasets/synthetic_128d_100k/query.fvecs")
    p.add_argument("--adjacency", type=Path, default=Path("/home/ubuntu/pz/VectorDB/experiment/exp_m08/results/exp0_indices/diskann_R64/adjacency.txt"))
    p.add_argument("--documents", type=int, default=100000)
    p.add_argument("--query-count", type=int, default=160)
    p.add_argument("--expansions", type=int, default=300)
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--seed", type=int, default=53)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    started = time.time()
    rng = np.random.default_rng(args.seed)
    docs = read_fvecs(args.base, args.documents)
    query_all = read_fvecs(args.queries)
    qrows = rng.choice(len(query_all), min(args.query_count, len(query_all)), replace=False)
    queries = query_all[qrows]
    graph = read_adjacency(args.adjacency, len(docs))
    centroid = docs.mean(axis=0)
    entry = int(np.argmin(np.linalg.norm(docs - centroid, axis=1)))
    base_step = max(5, args.expansions // 60)
    policies = [
        (step, width)
        for step in (base_step, 2 * base_step, 4 * base_step, 10 * base_step)
        for width in (1, 2, 5)
    ]

    policy_records: dict[str, list[dict]] = {}
    discovery = []
    recalls = []
    for query in queries:
        final, policy_metrics, first_seen = graph_trace(
            docs, graph, query, entry, args.expansions, args.k, policies
        )
        exact_dist = np.linalg.norm(docs - query, axis=1)
        exact = set(np.argpartition(exact_dist, args.k - 1)[: args.k].tolist())
        recalls.append(len(exact & set(final.tolist())) / args.k)
        discovery.extend(first_seen[int(item)] / args.expansions for item in final)
        for name, metrics in policy_metrics.items():
            policy_records.setdefault(name, []).append(metrics)

    report = {
        "experiment": "payload_speculation_a_minus_1",
        "question": "Do final ANN winners appear early enough to hide payload I/O under a low wasted-read budget?",
        "dataset": "60/100K graph over 128-D benchmark vectors",
        "config": vars(args) | {"base": str(args.base), "queries": str(args.queries), "adjacency": str(args.adjacency), "output": str(args.output)},
        "entry_node": entry,
        "ann_recall_at_k": aggregate([{"value": x} for x in recalls])["value"],
        "winner_first_seen_fraction_of_search": aggregate([{"value": x} for x in discovery])["value"],
        "policies": {name: aggregate(records) for name, records in policy_records.items()},
        "elapsed_seconds": time.time() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
