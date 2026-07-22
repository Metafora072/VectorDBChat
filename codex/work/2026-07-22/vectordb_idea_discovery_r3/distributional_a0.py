#!/usr/bin/env python3
"""A0 for replica-free distributional ANN.

DINOSAUR-style retrieval stores several sampled vectors for every item.  For
isotropic Gaussian item posteriors and inner product, the maximum score among
S fresh replicas has a one-dimensional order-statistic distribution.  This
script tests the necessary selectivity premise of a replica-free alternative:
rank items by a simultaneous upper confidence bound, sample exact maxima only
for visited items, and stop when the current kth sampled score exceeds every
remaining bound.

The simulation computes all scores only to evaluate the offline gate.  The
reported number of visited items is the work that an ordered UCB/MIPS oracle
would expose.  If the simultaneous bounds require most of the catalogue, the
compact-index idea is killed before implementing an ANN backend.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

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
    p.add_argument("--output", type=Path, default=Path("distributional_a0_results.json"))
    p.add_argument("--users", type=int, default=10_000)
    p.add_argument("--items", type=int, default=5_000)
    p.add_argument("--rank", type=int, default=32)
    p.add_argument("--queries", type=int, default=256)
    p.add_argument("--samples", type=int, nargs="+", default=[2, 5, 10])
    p.add_argument("--ks", type=int, nargs="+", default=[10, 50, 100])
    p.add_argument("--deltas", type=float, nargs="+", default=[0.10, 0.01])
    p.add_argument("--alpha", type=float, default=0.10)
    p.add_argument("--gamma", type=float, default=0.25)
    p.add_argument("--seed", type=int, default=31)
    return p.parse_args()


def evaluate(
    means: np.ndarray,
    sigma: np.ndarray,
    queries: np.ndarray,
    samples: int,
    k: int,
    delta: float,
    rng: np.random.Generator,
) -> dict[str, float]:
    n = len(means)
    # Allocate delta/n to every item and use the exact maximum-of-S Gaussian
    # quantile rather than the looser sqrt(log nS/delta) tail inequality.
    per_item_cdf = (1.0 - delta / n) ** (1.0 / samples)
    beta = float(norm.ppf(per_item_cdf))
    scan_fractions: list[float] = []
    candidate_expansions: list[float] = []
    exact_world_recall: list[float] = []
    for q in queries:
        mean_score = means @ q
        scale = sigma * np.linalg.norm(q)
        # Inverse CDF of max of S iid standard normals.
        u = np.clip(rng.random(n), 1e-12, 1.0 - 1e-12)
        sampled_score = mean_score + scale * norm.ppf(u ** (1.0 / samples))
        upper = mean_score + beta * scale
        order = np.argsort(-upper)

        # Offline replay of best-first UCB enumeration.
        heap_scores: list[float] = []
        stop = n
        for pos, item in enumerate(order):
            heap_scores.append(float(sampled_score[item]))
            if len(heap_scores) >= k:
                kth = float(np.partition(np.asarray(heap_scores), -k)[-k])
                next_upper = float(upper[order[pos + 1]]) if pos + 1 < n else -np.inf
                if kth >= next_upper:
                    stop = pos + 1
                    break
        visited = order[:stop]
        result = visited[np.argsort(-sampled_score[visited])[:k]]
        truth = np.argpartition(sampled_score, -k)[-k:]
        exact_world_recall.append(len(set(result.tolist()).intersection(truth.tolist())) / k)
        scan_fractions.append(stop / n)
        candidate_expansions.append(stop / k)

    f = np.asarray(scan_fractions)
    e = np.asarray(candidate_expansions)
    return {
        "simultaneous_beta": beta,
        "scan_fraction_mean": float(f.mean()),
        "scan_fraction_p50": float(np.quantile(f, 0.50)),
        "scan_fraction_p95": float(np.quantile(f, 0.95)),
        "candidate_expansion_p50": float(np.quantile(e, 0.50)),
        "candidate_expansion_p95": float(np.quantile(e, 0.95)),
        "sampled_world_recall_mean": float(np.mean(exact_world_recall)),
    }


def main() -> None:
    args = parse_args()
    started = time.time()
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
    user_counts = np.bincount(users, minlength=len(raw_users))
    active = np.flatnonzero(user_counts >= 20)
    rng = np.random.default_rng(args.seed)
    query_ids = rng.choice(active, size=min(args.queries, len(active)), replace=False)

    metrics: dict[str, object] = {}
    for samples in args.samples:
        for k in args.ks:
            for delta in args.deltas:
                key = f"S={samples},k={k},delta={delta:g}"
                metrics[key] = evaluate(item_vec, sigma, user_vec[query_ids], samples, k, delta, rng)

    best_p50 = min(float(v["scan_fraction_p50"]) for v in metrics.values())
    gate = {"some_simultaneous_bound_p50_scan_le_0_20": best_p50 <= 0.20}
    out = {
        "experiment": "replica_free_distributional_ann_a0",
        "dataset": str(args.ratings),
        "configuration": vars(args) | {"ratings": str(args.ratings), "output": str(args.output)},
        "selected_users": len(raw_users),
        "selected_items": len(raw_items),
        "interactions": interactions,
        "sigma": {
            "mean": float(sigma.mean()),
            "p50": float(np.quantile(sigma, 0.50)),
            "p95": float(np.quantile(sigma, 0.95)),
        },
        "metrics": metrics,
        "gate": gate,
        "verdict": "GO_DEEPER" if all(gate.values()) else "KILL_OR_RETHINK",
        "wall_seconds": time.time() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
