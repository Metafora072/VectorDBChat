#!/usr/bin/env python3
"""A0 kill test for motion-bounded ANN.

This is intentionally an algorithm-headroom test, not a full index.  It compares
a sound displacement-envelope candidate set with the strongest trivial baseline:
rerank a fixed prefix of the old exact order after sparse bounded vector motion.
If old-order overfetch already captures the fresh answer, a new ANN structure has
little room to justify itself.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np


def read_vectors(path: Path, limit: int) -> np.ndarray:
    if path.suffix == ".fbin":
        header = np.fromfile(path, dtype=np.uint32, count=2)
        n, d = map(int, header)
        return np.asarray(
            np.memmap(path, dtype=np.float32, mode="r", offset=8, shape=(n, d))[:limit],
            dtype=np.float32,
        )
    raw = np.memmap(path, dtype=np.int32, mode="r")
    d = int(raw[0])
    n = min(limit, raw.size // (d + 1))
    shaped = np.memmap(path, dtype=np.float32, mode="r", shape=(n, d + 1))
    return np.asarray(shaped[:, 1:], dtype=np.float32)


def normalize(x: np.ndarray) -> np.ndarray:
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def l2(queries: np.ndarray, docs: np.ndarray) -> np.ndarray:
    qn = np.sum(queries * queries, axis=1, keepdims=True)
    dn = np.sum(docs * docs, axis=1, keepdims=True).T
    sq = np.maximum(qn + dn - 2.0 * (queries @ docs.T), 0.0)
    return np.sqrt(sq, out=sq)


def topk(dist: np.ndarray, k: int) -> np.ndarray:
    ids = np.argpartition(dist, k - 1, axis=1)[:, :k]
    vals = np.take_along_axis(dist, ids, axis=1)
    return np.take_along_axis(ids, np.argsort(vals, axis=1), axis=1)


def dist_stats(values: list[float]) -> dict[str, float]:
    a = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(a.mean()),
        "p50": float(np.quantile(a, 0.50)),
        "p95": float(np.quantile(a, 0.95)),
        "p99": float(np.quantile(a, 0.99)),
        "max": float(a.max()),
    }


def movement(
    docs: np.ndarray,
    moved_ids: np.ndarray,
    radius: float,
    mode: str,
    queries: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    old = docs[moved_ids]
    if mode == "random":
        direction = rng.normal(size=old.shape).astype(np.float32)
        direction /= np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1e-12)
    elif mode == "workload_aligned":
        # A coherent stress case: updated profiles move toward one of a small set
        # of workload intents, rather than in independent random directions.
        anchors = queries[: min(16, len(queries))]
        nearest = np.argmin(l2(old, anchors), axis=1)
        direction = anchors[nearest] - old
        direction /= np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1e-12)
    else:
        raise ValueError(mode)
    updated = old + radius * direction
    actual = np.linalg.norm(updated - old, axis=1)
    return updated.astype(np.float32), actual.astype(np.float32)


def evaluate_regime(
    docs: np.ndarray,
    queries: np.ndarray,
    old_dist: np.ndarray,
    old_order: np.ndarray,
    moved_fraction: float,
    radius_fraction: float,
    reference_kth: float,
    mode: str,
    k: int,
    overfetch: list[int],
    seed: int,
) -> dict:
    rng = np.random.default_rng(seed)
    moved_count = int(round(len(docs) * moved_fraction))
    moved_ids = rng.choice(len(docs), moved_count, replace=False)
    radius = radius_fraction * reference_kth
    updated, actual_radii = movement(docs, moved_ids, radius, mode, queries, rng)
    radii = np.zeros(len(docs), dtype=np.float32)
    radii[moved_ids] = actual_radii

    new_dist = old_dist.copy()
    new_dist[:, moved_ids] = l2(queries, updated)
    truth = topk(new_dist, k)
    new_kth = np.take_along_axis(new_dist, truth[:, [-1]], axis=1)[:, 0]

    stale_recall = []
    fixed = {width: [] for width in overfetch}
    certificate_count = []
    oracle_count = []
    certificate_recall = []
    moved_winners = []
    for qi in range(len(queries)):
        truth_set = set(truth[qi].tolist())
        stale_recall.append(len(truth_set & set(old_order[qi, :k].tolist())) / k)
        moved_winners.append(len(truth_set & set(moved_ids.tolist())))
        for width in overfetch:
            ids = old_order[qi, :width]
            reranked = ids[np.argsort(new_dist[qi, ids])[:k]]
            fixed[width].append(len(truth_set & set(reranked.tolist())) / k)

        seed_ids = old_order[qi, :k]
        upper = float(np.max(new_dist[qi, seed_ids]))
        certified = np.flatnonzero(np.maximum(old_dist[qi] - radii, 0.0) <= upper)
        cert_answer = certified[np.argsort(new_dist[qi, certified])[:k]]
        certificate_count.append(len(certified))
        certificate_recall.append(len(truth_set & set(cert_answer.tolist())) / k)
        oracle_count.append(int(np.count_nonzero(np.maximum(old_dist[qi] - radii, 0.0) <= new_kth[qi])))

    return {
        "mode": mode,
        "moved_fraction": moved_fraction,
        "moved_count": moved_count,
        "radius_fraction_of_median_kth": radius_fraction,
        "absolute_radius": radius,
        "stale_recall_at_k": dist_stats(stale_recall),
        "fresh_topk_moved_items": dist_stats(moved_winners),
        "sound_envelope_candidate_count": dist_stats(certificate_count),
        "sound_envelope_expansion_over_k": dist_stats([x / k for x in certificate_count]),
        "oracle_minimum_candidate_count": dist_stats(oracle_count),
        "sound_envelope_recall_at_k": dist_stats(certificate_recall),
        "fixed_old_prefix_rerank_recall": {str(w): dist_stats(v) for w, v in fixed.items()},
    }


def main() -> None:
    p = argparse.ArgumentParser()
    root = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/a0_topology_reuse")
    p.add_argument("--docs", type=Path, default=root / "embeddings/formal_100k/minilm_l6_v1_v2/old_corpus.fbin")
    p.add_argument("--queries", type=Path, default=root / "embeddings/formal_100k/minilm_l6_v1_v2/old_queries.fbin")
    p.add_argument("--documents", type=int, default=60000)
    p.add_argument("--query-count", type=int, default=160)
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--moved-fractions", type=float, nargs="+", default=[0.1, 0.2])
    p.add_argument("--radius-fractions", type=float, nargs="+", default=[0.05, 0.1])
    p.add_argument("--modes", nargs="+", default=["random", "workload_aligned"])
    p.add_argument("--overfetch", type=int, nargs="+", default=[20, 50, 100, 200, 500])
    p.add_argument("--seed", type=int, default=71)
    p.add_argument("--output", type=Path, required=True)
    cfg = p.parse_args()
    started = time.time()
    rng = np.random.default_rng(cfg.seed)
    docs = normalize(read_vectors(cfg.docs, cfg.documents))
    query_all = normalize(read_vectors(cfg.queries, 1000000))
    query_ids = rng.choice(len(query_all), min(cfg.query_count, len(query_all)), replace=False)
    queries = query_all[query_ids]
    old_dist = l2(queries, docs)
    old_order = np.argsort(old_dist, axis=1)[:, : max(cfg.overfetch)]
    reference_kth = float(np.median(np.partition(old_dist, cfg.k - 1, axis=1)[:, cfg.k - 1]))

    records = []
    counter = 0
    for mode in cfg.modes:
        for moved_fraction in cfg.moved_fractions:
            for radius_fraction in cfg.radius_fractions:
                records.append(
                    evaluate_regime(
                        docs,
                        queries,
                        old_dist,
                        old_order,
                        moved_fraction,
                        radius_fraction,
                        reference_kth,
                        mode,
                        cfg.k,
                        cfg.overfetch,
                        cfg.seed + 1009 * counter,
                    )
                )
                counter += 1

    # Pre-registered paper-level A0 gate: a nontrivial regime must have stale
    # recall <= .95, certified p95 expansion <= 5x, and beat fixed top-50.
    gate_rows = []
    for r in records:
        nontrivial = r["stale_recall_at_k"]["mean"] <= 0.95
        selective = r["sound_envelope_expansion_over_k"]["p95"] <= 5.0
        baseline_not_enough = r["fixed_old_prefix_rerank_recall"]["50"]["mean"] < 0.99 - 1e-12
        gate_rows.append({
            "mode": r["mode"],
            "moved_fraction": r["moved_fraction"],
            "radius_fraction": r["radius_fraction_of_median_kth"],
            "nontrivial": nontrivial,
            "selective": selective,
            "fixed_top50_not_enough": baseline_not_enough,
            "row_pass": nontrivial and selective and baseline_not_enough,
        })
    passed = any(row["row_pass"] for row in gate_rows)
    report = {
        "experiment": "motion_bounded_a0",
        "hypothesis": "Bounded-motion envelopes expose a selective candidate set in regimes where stale search fails and fixed old-order overfetch is insufficient.",
        "dataset": "MiniLM Quora corpus and held-out query embeddings",
        "config": {**vars(cfg), "docs": str(cfg.docs), "queries": str(cfg.queries), "output": str(cfg.output)},
        "median_exact_kth_distance": reference_kth,
        "gate": {
            "definition": "exists regime with stale recall <=0.95, envelope p95 <=5k, and fixed-old-top50 recall <0.99",
            "rows": gate_rows,
            "pass": passed,
        },
        "records": records,
        "elapsed_seconds": time.time() - started,
    }
    cfg.output.parent.mkdir(parents=True, exist_ok=True)
    cfg.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
