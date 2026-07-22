#!/usr/bin/env python3
"""Corrective A0: actually enumerate a sound bounded-motion top-k via cells.

Unlike the oracle candidate-size probe, the search path never reads all old
point distances or an exact old ordering.  It computes one bound per fixed old-
space cell and visits cells best-first until the next sound lower bound exceeds
the current fresh kth distance.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np


def read_fbin(path: Path, limit: int) -> np.ndarray:
    header = np.fromfile(path, dtype=np.uint32, count=2)
    n, d = map(int, header)
    return np.asarray(
        np.memmap(path, dtype=np.float32, mode="r", offset=8, shape=(n, d))[:limit],
        dtype=np.float32,
    )


def normalize(x: np.ndarray) -> np.ndarray:
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def squared_l2(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    an = np.sum(a * a, axis=1, keepdims=True)
    bn = np.sum(b * b, axis=1, keepdims=True).T
    return np.maximum(an + bn - 2.0 * (a @ b.T), 0.0)


def lloyd_cells(
    docs: np.ndarray,
    cell_count: int,
    iterations: int,
    seed: int,
    block: int = 256,
) -> tuple[np.ndarray, np.ndarray, list[np.ndarray], list[float]]:
    rng = np.random.default_rng(seed)
    centers = docs[rng.choice(len(docs), cell_count, replace=False)].copy()
    assign = np.empty(len(docs), dtype=np.int32)
    objective = []
    for iteration in range(iterations):
        total_sq = 0.0
        for start in range(0, len(docs), block):
            stop = min(start + block, len(docs))
            dist = squared_l2(docs[start:stop], centers)
            labels = np.argmin(dist, axis=1)
            assign[start:stop] = labels
            total_sq += float(np.sum(dist[np.arange(stop - start), labels]))
        objective.append(total_sq / len(docs))
        sums = np.zeros_like(centers)
        counts = np.bincount(assign, minlength=cell_count)
        np.add.at(sums, assign, docs)
        nonempty = counts > 0
        centers[nonempty] = sums[nonempty] / counts[nonempty, None]
        empty = np.flatnonzero(~nonempty)
        if len(empty):
            centers[empty] = docs[rng.choice(len(docs), len(empty), replace=False)]

    # One final exact assignment to the centers actually used by the search.
    for start in range(0, len(docs), block):
        stop = min(start + block, len(docs))
        assign[start:stop] = np.argmin(squared_l2(docs[start:stop], centers), axis=1)
    members = [np.flatnonzero(assign == cell).astype(np.int32) for cell in range(cell_count)]
    radii = np.zeros(cell_count, dtype=np.float32)
    for cell, ids in enumerate(members):
        if len(ids):
            radii[cell] = float(np.sqrt(np.max(squared_l2(docs[ids], centers[cell : cell + 1]))))
    return centers, radii, members, objective


def topk_ids(dist: np.ndarray, k: int) -> np.ndarray:
    ids = np.argpartition(dist, k - 1)[:k]
    return ids[np.argsort(dist[ids])]


def stats(values: list[float]) -> dict[str, float]:
    a = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(a.mean()),
        "p50": float(np.quantile(a, 0.50)),
        "p95": float(np.quantile(a, 0.95)),
        "p99": float(np.quantile(a, 0.99)),
        "max": float(a.max()),
    }


def search_one(
    query: np.ndarray,
    fresh_docs: np.ndarray,
    fresh_norms: np.ndarray,
    centers: np.ndarray,
    radii: np.ndarray,
    cell_motion: np.ndarray,
    members: list[np.ndarray],
    k: int,
) -> tuple[np.ndarray, int, int, float]:
    started = time.perf_counter()
    center_dist = np.sqrt(squared_l2(query[None, :], centers)[0])
    lower = np.maximum(center_dist - radii - cell_motion, 0.0)
    order = np.argsort(lower, kind="stable")
    best_ids = np.empty(0, dtype=np.int32)
    best_dist = np.empty(0, dtype=np.float32)
    point_distances = 0
    visited_cells = 0
    qnorm = float(query @ query)
    for cell in order:
        if len(best_dist) == k and lower[cell] > best_dist[-1] + 1e-6:
            break
        ids = members[int(cell)]
        visited_cells += 1
        if not len(ids):
            continue
        d2 = np.maximum(qnorm + fresh_norms[ids] - 2.0 * (fresh_docs[ids] @ query), 0.0)
        d = np.sqrt(d2)
        point_distances += len(ids)
        merged_ids = np.concatenate((best_ids, ids))
        merged_dist = np.concatenate((best_dist, d.astype(np.float32)))
        take = min(k, len(merged_dist))
        pos = np.argpartition(merged_dist, take - 1)[:take]
        pos = pos[np.argsort(merged_dist[pos])]
        best_ids, best_dist = merged_ids[pos], merged_dist[pos]
    return best_ids, point_distances, visited_cells, time.perf_counter() - started


def main() -> None:
    p = argparse.ArgumentParser()
    root = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/a0_topology_reuse/embeddings/formal_100k/minilm_l6_v1_v2")
    p.add_argument("--docs", type=Path, default=root / "old_corpus.fbin")
    p.add_argument("--queries", type=Path, default=root / "old_queries.fbin")
    p.add_argument("--documents", type=int, default=60000)
    p.add_argument("--query-count", type=int, default=160)
    p.add_argument("--cells", type=int, default=4096)
    p.add_argument("--lloyd-iterations", type=int, default=4)
    p.add_argument("--moved-fraction", type=float, default=0.2)
    p.add_argument("--radius-fraction", type=float, default=0.1)
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--seed", type=int, default=83)
    p.add_argument("--output", type=Path, required=True)
    cfg = p.parse_args()
    all_started = time.time()
    rng = np.random.default_rng(cfg.seed)
    docs = normalize(read_fbin(cfg.docs, cfg.documents))
    all_queries = normalize(read_fbin(cfg.queries, 1000000))
    query_ids = rng.choice(len(all_queries), min(cfg.query_count, len(all_queries)), replace=False)
    queries = all_queries[query_ids]

    # Evaluation-only exact scan establishes scale and ground truth.  These
    # arrays are not passed to search_one.
    old_eval = np.sqrt(squared_l2(queries, docs))
    kth_scale = float(np.median(np.partition(old_eval, cfg.k - 1, axis=1)[:, cfg.k - 1]))
    radius = cfg.radius_fraction * kth_scale
    del old_eval

    build_started = time.time()
    centers, cell_radii, members, objective = lloyd_cells(
        docs, cfg.cells, cfg.lloyd_iterations, cfg.seed + 1
    )
    build_seconds = time.time() - build_started
    point_to_cell = np.empty(len(docs), dtype=np.int32)
    for cell, ids in enumerate(members):
        point_to_cell[ids] = cell

    moved_count = int(round(len(docs) * cfg.moved_fraction))
    moved_ids = rng.choice(len(docs), moved_count, replace=False)
    anchors = queries[: min(16, len(queries))]
    nearest = np.argmin(squared_l2(docs[moved_ids], anchors), axis=1)
    direction = anchors[nearest] - docs[moved_ids]
    direction /= np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1e-12)
    fresh_docs = docs.copy()
    fresh_docs[moved_ids] += radius * direction
    actual_motion = np.linalg.norm(fresh_docs[moved_ids] - docs[moved_ids], axis=1)
    cell_motion = np.zeros(cfg.cells, dtype=np.float32)
    np.maximum.at(cell_motion, point_to_cell[moved_ids], actual_motion)
    fresh_norms = np.sum(fresh_docs * fresh_docs, axis=1)

    truth = []
    flat_times = []
    for q in queries:
        started = time.perf_counter()
        dist = np.sqrt(np.maximum(float(q @ q) + fresh_norms - 2.0 * (fresh_docs @ q), 0.0))
        truth.append(topk_ids(dist, cfg.k))
        flat_times.append(time.perf_counter() - started)

    recalls = []
    work = []
    point_work = []
    visited = []
    search_times = []
    for q, exact in zip(queries, truth):
        found, points, cells, elapsed = search_one(
            q, fresh_docs, fresh_norms, centers, cell_radii, cell_motion, members, cfg.k
        )
        recalls.append(len(set(found.tolist()) & set(exact.tolist())) / cfg.k)
        point_work.append(points)
        work.append(cfg.cells + points)
        visited.append(cells)
        search_times.append(elapsed)

    exact_all = bool(np.all(np.asarray(recalls) == 1.0))
    work_p95 = float(np.quantile(work, 0.95))
    median_ratio = float(np.median(search_times) / np.median(flat_times))
    gate = {
        "all_160_exact": exact_all,
        "p95_centroid_plus_point_distances_le_6000": work_p95 <= 6000,
        "median_wall_time_le_half_flat": median_ratio <= 0.5,
    }
    gate["pass"] = all(gate.values())
    report = {
        "experiment": "motion_cell_enumeration_corrective_a0",
        "claim": "Fixed old-space cells can soundly and sublinearly enumerate fresh top-k under bounded motion without full old-distance access.",
        "config": {**vars(cfg), "docs": str(cfg.docs), "queries": str(cfg.queries), "output": str(cfg.output)},
        "dataset": "60K MiniLM Quora corpus and 160 held-out queries",
        "median_old_kth_distance": kth_scale,
        "absolute_motion_radius": radius,
        "build": {
            "seconds": build_seconds,
            "lloyd_mean_squared_objective": objective,
            "nonempty_cells": int(sum(bool(len(x)) for x in members)),
            "cell_size": stats([len(x) for x in members]),
            "cell_radius": stats(cell_radii.tolist()),
        },
        "search": {
            "recall_at_10": stats(recalls),
            "centroid_plus_point_distances": stats(work),
            "fresh_point_distances": stats(point_work),
            "visited_cells": stats(visited),
            "search_seconds": stats(search_times),
            "flat_scan_seconds": stats(flat_times),
            "median_time_ratio_to_flat": median_ratio,
        },
        "gate": gate,
        "elapsed_seconds": time.time() - all_started,
    }
    cfg.output.parent.mkdir(parents=True, exist_ok=True)
    cfg.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
