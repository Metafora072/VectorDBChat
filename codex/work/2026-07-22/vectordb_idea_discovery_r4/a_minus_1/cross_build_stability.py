#!/usr/bin/env python3
"""A-1: cross-build HNSW result churn at matched recall."""

from __future__ import annotations

import argparse
import itertools
import json
import time
from pathlib import Path

import hnswlib
import numpy as np


def read_fbin(path: Path) -> np.ndarray:
    h = np.fromfile(path, dtype=np.uint32, count=2)
    n, d = map(int, h)
    return np.memmap(path, dtype=np.float32, mode="r", offset=8, shape=(n, d))


def normalize(x: np.ndarray) -> np.ndarray:
    y = np.asarray(x, dtype=np.float32)
    return y / np.maximum(np.linalg.norm(y, axis=1, keepdims=True), 1e-12)


def top_ids(scores: np.ndarray, k: int) -> np.ndarray:
    ids = np.argpartition(scores, -k, axis=1)[:, -k:]
    vals = np.take_along_axis(scores, ids, axis=1)
    return np.take_along_axis(ids, np.argsort(-vals, axis=1), axis=1)


def mean_recall(found: np.ndarray, exact: np.ndarray) -> float:
    return float(np.mean([len(set(a) & set(b)) / exact.shape[1] for a, b in zip(found, exact)]))


def main() -> None:
    p = argparse.ArgumentParser()
    root = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/a0_topology_reuse")
    p.add_argument("--docs", type=Path, default=root / "embeddings/formal_100k/minilm_l6_v1_v2/old_corpus.fbin")
    p.add_argument("--queries", type=Path, default=root / "embeddings/formal_100k/minilm_l6_v1_v2/old_queries.fbin")
    p.add_argument("--documents", type=int, default=60000)
    p.add_argument("--query-count", type=int, default=240)
    p.add_argument("--builds", type=int, default=4)
    p.add_argument("--m", type=int, default=16)
    p.add_argument("--ef-construction", type=int, default=100)
    p.add_argument("--ef-values", type=int, nargs="+", default=[10, 20, 40, 80])
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--threads", type=int, default=8)
    p.add_argument("--seed", type=int, default=31)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    started = time.time()
    rng = np.random.default_rng(args.seed)

    docs = normalize(read_fbin(args.docs)[: args.documents])
    all_queries = normalize(read_fbin(args.queries))
    query_rows = rng.choice(len(all_queries), args.query_count, replace=False)
    queries = all_queries[query_rows]
    exact_scores = queries @ docs.T
    exact = top_ids(exact_scores, args.k)
    exact_kth = np.take_along_axis(exact_scores, exact[:, [-1]], axis=1)[:, 0]

    all_results: dict[int, list[np.ndarray]] = {ef: [] for ef in args.ef_values}
    build_seconds = []
    for build in range(args.builds):
        order = np.random.default_rng(args.seed + 1009 * build).permutation(len(docs))
        index = hnswlib.Index(space="cosine", dim=docs.shape[1])
        index.init_index(
            max_elements=len(docs),
            ef_construction=args.ef_construction,
            M=args.m,
            random_seed=args.seed + build,
        )
        t0 = time.time()
        index.add_items(docs[order], order.astype(np.int64), num_threads=args.threads)
        build_seconds.append(time.time() - t0)
        for ef in args.ef_values:
            index.set_ef(max(ef, args.k))
            found, _ = index.knn_query(queries, k=args.k, num_threads=args.threads)
            all_results[ef].append(found)

    summary = {}
    for ef, builds in all_results.items():
        recalls = [mean_recall(found, exact) for found in builds]
        per_query_jaccard = []
        per_query_swaps = []
        differing_items = []
        for left, right in itertools.combinations(builds, 2):
            for qi, (a, b) in enumerate(zip(left, right)):
                sa, sb = set(a), set(b)
                per_query_jaccard.append(len(sa & sb) / len(sa | sb))
                per_query_swaps.append(args.k - len(sa & sb))
                differing_items.extend((qi, int(x)) for x in sa ^ sb)
        indifference = {}
        for eps in (1e-4, 1e-3, 5e-3, 1e-2):
            if differing_items:
                good = [exact_scores[qi, item] >= exact_kth[qi] - eps for qi, item in differing_items]
                indifference[f"fraction_churn_within_{eps:g}_of_exact_kth"] = float(np.mean(good))
        arr = np.asarray(per_query_jaccard)
        swaps = np.asarray(per_query_swaps)
        summary[str(ef)] = {
            "recall_mean": float(np.mean(recalls)),
            "recall_min_build": float(np.min(recalls)),
            "recall_max_build": float(np.max(recalls)),
            "pairwise_jaccard_mean": float(arr.mean()),
            "pairwise_jaccard_p10": float(np.quantile(arr, 0.10)),
            "pairwise_jaccard_p01": float(np.quantile(arr, 0.01)),
            "mean_swaps_out_of_k": float(swaps.mean()),
            "queries_with_any_swap_fraction": float(np.mean(swaps > 0)),
            **indifference,
        }

    report = {
        "experiment": "cross_build_stability_a_minus_1",
        "question": "At matched parameters/recall, is cross-build result churn large and mostly caused by near ties?",
        "dataset": "100K MiniLM corpus (prefix subset) + held-out query embeddings",
        "config": vars(args) | {"docs": str(args.docs), "queries": str(args.queries), "output": str(args.output)},
        "build_seconds": build_seconds,
        "summary": summary,
        "elapsed_seconds": time.time() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
