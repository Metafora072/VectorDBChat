#!/usr/bin/env python3
"""Practical A0 for replica-free Thompson ANN on a CPU HNSW backend.

The exact offline UCB experiment establishes that a small candidate set can be
sound.  This follow-up tests whether an ordinary approximate MIPS index over
the augmented UCB vectors preserves that selectivity, and whether the UCB
ordering carries information beyond simply overfetching from the mean index.
"""

from __future__ import annotations

import argparse
import heapq
import json
import time
from pathlib import Path

import hnswlib
import numpy as np
from scipy.stats import norm

from move_a0 import factorize, read_and_filter


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--ratings",
        type=Path,
        default=Path("/home/ubuntu/pz/VectorDB/data/vaq_semantic_g0/raw/ml-20m/ratings.csv"),
    )
    p.add_argument("--output", type=Path, default=Path("distributional_hnsw_a0_results.json"))
    p.add_argument("--users", type=int, default=20_000)
    p.add_argument("--items", type=int, default=20_000)
    p.add_argument("--rank", type=int, default=32)
    p.add_argument("--queries", type=int, default=256)
    p.add_argument("--samples", type=int, default=5)
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--delta", type=float, default=0.01)
    p.add_argument("--alpha", type=float, default=0.10)
    p.add_argument("--gamma", type=float, default=0.25)
    p.add_argument("--max-candidates", type=int, default=2048)
    p.add_argument("--ef-construction", type=int, default=200)
    p.add_argument("--ef-search", type=int, default=512)
    p.add_argument("--m", type=int, default=16)
    p.add_argument("--seed", type=int, default=37)
    return p.parse_args()


def build_index(x: np.ndarray, args: argparse.Namespace) -> tuple[hnswlib.Index, float]:
    started = time.perf_counter()
    index = hnswlib.Index(space="ip", dim=x.shape[1])
    index.init_index(max_elements=len(x), ef_construction=args.ef_construction, M=args.m, random_seed=args.seed)
    index.add_items(x, np.arange(len(x)))
    index.set_ef(max(args.ef_search, args.max_candidates))
    return index, time.perf_counter() - started


def summarize(values: list[float]) -> dict[str, float]:
    x = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(x.mean()),
        "p50": float(np.quantile(x, 0.50)),
        "p95": float(np.quantile(x, 0.95)),
    }


def main() -> None:
    args = parse_args()
    wall_started = time.time()
    users, items, ts, raw_users, raw_items = read_and_filter(args.ratings, args.users, args.items)
    user_vec, item_vec, interactions = factorize(
        users,
        items,
        ts,
        int(ts.max()),
        len(raw_users),
        len(raw_items),
        args.rank,
        args.seed,
    )
    item_counts = np.bincount(items, minlength=len(raw_items))
    sigma = args.alpha / np.power(1.0 + item_counts, args.gamma)
    beta = float(norm.ppf((1.0 - args.delta / len(item_vec)) ** (1.0 / args.samples)))
    augmented = np.concatenate((item_vec, (beta * sigma)[:, None]), axis=1).astype(np.float32)

    ucb_index, ucb_build = build_index(augmented, args)
    mean_index, mean_build = build_index(item_vec, args)
    user_counts = np.bincount(users, minlength=len(raw_users))
    active = np.flatnonzero(user_counts >= 20)
    rng = np.random.default_rng(args.seed)
    query_ids = rng.choice(active, size=min(args.queries, len(active)), replace=False)

    exact_scan, hnsw_scan = [], []
    hnsw_recall, mean_matched_recall = [], []
    hnsw_latency_ms, mean_latency_ms = [], []
    ucb_prefix_recall = []
    for q in user_vec[query_ids]:
        mean_score = item_vec @ q
        scale = sigma * np.linalg.norm(q)
        u = np.clip(rng.random(len(item_vec)), 1e-12, 1.0 - 1e-12)
        sampled = mean_score + scale * norm.ppf(u ** (1.0 / args.samples))
        truth = set(np.argpartition(sampled, -args.k)[-args.k:].tolist())
        upper = mean_score + beta * scale

        # Exact UCB prefix and its sound stopping location.
        exact_order = np.argsort(-upper)
        exact_stop = len(item_vec)
        exact_heap: list[float] = []
        for pos, item in enumerate(exact_order):
            score = float(sampled[item])
            if len(exact_heap) < args.k:
                heapq.heappush(exact_heap, score)
            elif score > exact_heap[0]:
                heapq.heapreplace(exact_heap, score)
            if len(exact_heap) < args.k:
                continue
            kth = exact_heap[0]
            next_upper = float(upper[exact_order[pos + 1]]) if pos + 1 < len(item_vec) else -np.inf
            if kth >= next_upper:
                exact_stop = pos + 1
                break
        exact_scan.append(exact_stop)

        q_aug = np.concatenate((q, np.asarray([np.linalg.norm(q)], dtype=np.float32)))
        t0 = time.perf_counter()
        labels, _ = ucb_index.knn_query(q_aug, k=min(args.max_candidates, len(item_vec)))
        hnsw_latency_ms.append(1000.0 * (time.perf_counter() - t0))
        order = labels[0]
        stop = len(order)
        ann_heap: list[float] = []
        for pos, item in enumerate(order):
            score = float(sampled[item])
            if len(ann_heap) < args.k:
                heapq.heappush(ann_heap, score)
            elif score > ann_heap[0]:
                heapq.heapreplace(ann_heap, score)
            if len(ann_heap) < args.k:
                continue
            kth = ann_heap[0]
            # This is an empirical ANN frontier, not a sound unseen bound.
            if pos + 1 == len(order) or kth >= upper[order[pos + 1]]:
                stop = pos + 1
                break
        hnsw_scan.append(stop)
        picked = set(order[:stop][np.argsort(-sampled[order[:stop]])[: args.k]].tolist())
        hnsw_recall.append(len(picked.intersection(truth)) / args.k)
        prefix_n = min(exact_stop, len(order))
        ucb_prefix_recall.append(
            len(set(order[:prefix_n].tolist()).intersection(exact_order[:prefix_n].tolist())) / prefix_n
        )

        # Strong simple baseline: mean-MIPS overfetch with exactly the same
        # number of candidates as the UCB method for this query.
        t0 = time.perf_counter()
        mean_labels, _ = mean_index.knn_query(q, k=max(args.k, stop))
        mean_latency_ms.append(1000.0 * (time.perf_counter() - t0))
        mean_seen = mean_labels[0]
        mean_picked = set(mean_seen[np.argsort(-sampled[mean_seen])[: args.k]].tolist())
        mean_matched_recall.append(len(mean_picked.intersection(truth)) / args.k)

    out = {
        "experiment": "replica_free_distributional_ann_hnsw_a0",
        "dataset": str(args.ratings),
        "configuration": vars(args) | {"ratings": str(args.ratings), "output": str(args.output)},
        "selected_users": len(raw_users),
        "selected_items": len(raw_items),
        "interactions": interactions,
        "simultaneous_beta": beta,
        "index": {
            "ucb_vectors": len(augmented),
            "ucb_dimensions": augmented.shape[1],
            "ucb_build_seconds": ucb_build,
            "mean_build_seconds": mean_build,
        },
        "metrics": {
            "exact_ucb_candidates": summarize(exact_scan),
            "hnsw_ucb_candidates": summarize(hnsw_scan),
            "hnsw_world_recall": summarize(hnsw_recall),
            "mean_overfetch_world_recall_at_matched_candidates": summarize(mean_matched_recall),
            "hnsw_ucb_prefix_recall_at_exact_stop": summarize(ucb_prefix_recall),
            "hnsw_ucb_query_latency_ms_for_max_candidates": summarize(hnsw_latency_ms),
            "hnsw_mean_query_latency_ms_for_matched_candidates": summarize(mean_latency_ms),
        },
        "gate": {
            "hnsw_world_recall_ge_0_99": float(np.mean(hnsw_recall)) >= 0.99,
            "ucb_gain_over_mean_ge_0_10": float(np.mean(hnsw_recall) - np.mean(mean_matched_recall)) >= 0.10,
            "p95_candidates_le_50k": float(np.quantile(hnsw_scan, 0.95)) <= 50 * args.k,
        },
        "wall_seconds": time.time() - wall_started,
    }
    out["verdict"] = "GO_DEEPER" if all(out["gate"].values()) else "KILL_OR_RETHINK"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
