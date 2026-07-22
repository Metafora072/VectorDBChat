#!/usr/bin/env python3
"""A-1: tightness of sound distance envelopes for sparse, small vector motion."""

from __future__ import annotations

import argparse
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


def top_ids(dist: np.ndarray, k: int) -> np.ndarray:
    ids = np.argpartition(dist, k - 1, axis=1)[:, :k]
    vals = np.take_along_axis(dist, ids, axis=1)
    return np.take_along_axis(ids, np.argsort(vals, axis=1), axis=1)


def l2_dist(queries: np.ndarray, docs: np.ndarray) -> np.ndarray:
    qn = np.sum(queries * queries, axis=1, keepdims=True)
    dn = np.sum(docs * docs, axis=1, keepdims=True).T
    sq = np.maximum(qn + dn - 2.0 * (queries @ docs.T), 0.0)
    return np.sqrt(sq, out=sq)


def stats(values: list[float]) -> dict[str, float]:
    x = np.asarray(values, dtype=float)
    return {
        "mean": float(x.mean()),
        "p50": float(np.quantile(x, 0.50)),
        "p95": float(np.quantile(x, 0.95)),
        "p99": float(np.quantile(x, 0.99)),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    base = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/datasets/synthetic_128d_100k")
    p.add_argument("--base", type=Path, default=base / "base.fvecs")
    p.add_argument("--queries", type=Path, default=base / "query.fvecs")
    p.add_argument("--documents", type=int, default=100000)
    p.add_argument("--query-count", type=int, default=240)
    p.add_argument("--move-fractions", type=float, nargs="+", default=[0.01, 0.05, 0.10, 0.20])
    p.add_argument("--radius-fractions", type=float, nargs="+", default=[0.001, 0.005, 0.01, 0.02])
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--batch", type=int, default=20)
    p.add_argument("--seed", type=int, default=41)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    started = time.time()
    rng = np.random.default_rng(args.seed)
    docs = read_fvecs(args.base, args.documents)
    query_all = read_fvecs(args.queries)
    qrows = rng.choice(len(query_all), min(args.query_count, len(query_all)), replace=False)
    queries = query_all[qrows]

    # Establish a dataset-relative motion scale from exact kth distances.
    old_all = l2_dist(queries, docs)
    reference_kth = float(np.median(np.partition(old_all, args.k - 1, axis=1)[:, args.k - 1]))
    old_order_all = top_ids(old_all, 500)

    results = {}
    for moved_fraction in args.move_fractions:
        moved_count = int(round(len(docs) * moved_fraction))
        moved_ids = rng.choice(len(docs), moved_count, replace=False)
        direction = rng.normal(size=(moved_count, docs.shape[1])).astype(np.float32)
        direction /= np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1e-12)
        for radius_fraction in args.radius_fractions:
            radius = reference_kth * radius_fraction
            new_docs = docs.copy()
            new_docs[moved_ids] += direction * radius
            radii = np.zeros(len(docs), dtype=np.float32)
            radii[moved_ids] = radius

            stale_recalls: list[float] = []
            cover = {level: [] for level in (10, 50, 100, 500)}
            candidates: list[float] = []
            boundary_moved: list[float] = []
            new_all = old_all.copy()
            new_all[:, moved_ids] = l2_dist(queries, new_docs[moved_ids])
            for start in range(0, len(queries), args.batch):
                old_dist = old_all[start : start + args.batch]
                new_dist = new_all[start : start + args.batch]
                old_order = old_order_all[start : start + args.batch]
                new_top = top_ids(new_dist, args.k)
                new_kth = np.take_along_axis(new_dist, new_top[:, [-1]], axis=1)[:, 0]
                lower = np.maximum(old_dist - radii[None, :], 0.0)
                for row in range(len(old_dist)):
                    truth = set(new_top[row])
                    stale_recalls.append(len(truth & set(old_order[row, : args.k])) / args.k)
                    for level in cover:
                        cover[level].append(len(truth & set(old_order[row, :level])) / args.k)
                    active = lower[row] <= new_kth[row]
                    candidates.append(float(np.count_nonzero(active)))
                    boundary_moved.append(float(np.count_nonzero(active[moved_ids])))

            key = f"moved_{moved_fraction:.3f}_radius_{radius_fraction:.4f}"
            results[key] = {
                "moved_fraction": moved_fraction,
                "moved_count": moved_count,
                "radius_fraction_of_median_kth": radius_fraction,
                "absolute_radius": radius,
                "stale_recall_at_k": stats(stale_recalls),
                "sound_minimum_candidate_count": stats(candidates),
                "candidate_expansion_over_k": stats([v / args.k for v in candidates]),
                "active_moved_points": stats(boundary_moved),
                **{f"old_top_{level}_coverage": stats(values) for level, values in cover.items()},
            }

    report = {
        "experiment": "motion_bounded_a_minus_1",
        "question": "For sparse small same-space motion, are sound displacement envelopes selective?",
        "dataset": "100K x 128 synthetic benchmark vectors",
        "config": vars(args) | {"base": str(args.base), "queries": str(args.queries), "output": str(args.output)},
        "median_exact_kth_distance": reference_kth,
        "results": results,
        "elapsed_seconds": time.time() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
