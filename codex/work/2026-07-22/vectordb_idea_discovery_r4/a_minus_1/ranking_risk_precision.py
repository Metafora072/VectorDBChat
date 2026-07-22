#!/usr/bin/env python3
"""A-1: oracle headroom for workload/ranking-risk precision allocation.

This intentionally evaluates exhaustive quantized scoring.  It asks a necessary
question before an ANN implementation: at the same average bits/vector, can an
oracle variable-precision allocation preserve top-k rankings better than uniform
precision?  If not, a mixed-precision ANN index has no paper-worthy headroom.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np


def read_fbin(path: Path) -> np.ndarray:
    header = np.fromfile(path, dtype=np.uint32, count=2)
    if header.size != 2:
        raise ValueError(f"bad fbin header: {path}")
    n, d = map(int, header)
    expected = 8 + n * d * 4
    if path.stat().st_size != expected:
        raise ValueError(f"bad fbin size: {path} expected={expected}")
    return np.memmap(path, dtype=np.float32, mode="r", offset=8, shape=(n, d))


def normalize(x: np.ndarray) -> np.ndarray:
    y = np.asarray(x, dtype=np.float32)
    denom = np.linalg.norm(y, axis=1, keepdims=True)
    return y / np.maximum(denom, 1e-12)


def quantize_global(x: np.ndarray, bits: int, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    levels = (1 << bits) - 1
    span = np.maximum(hi - lo, 1e-8)
    code = np.rint(np.clip((x - lo) / span, 0.0, 1.0) * levels)
    return (lo + code * (span / levels)).astype(np.float32)


def topk_ids(scores: np.ndarray, k: int) -> np.ndarray:
    ids = np.argpartition(scores, -k, axis=1)[:, -k:]
    vals = np.take_along_axis(scores, ids, axis=1)
    order = np.argsort(-vals, axis=1)
    return np.take_along_axis(ids, order, axis=1)


def risk_from_queries(
    docs: np.ndarray,
    queries: np.ndarray,
    k: int,
    candidate_k: int,
    batch: int,
) -> tuple[np.ndarray, np.ndarray]:
    risk = np.zeros(docs.shape[0], dtype=np.float64)
    frequency = np.zeros(docs.shape[0], dtype=np.float64)
    tau = max(4.0, candidate_k / 8.0)
    for start in range(0, len(queries), batch):
        q = queries[start : start + batch]
        scores = q @ docs.T
        ids = topk_ids(scores, candidate_k)
        ordered = np.take_along_axis(scores, ids, axis=1)
        kth = ordered[:, [k - 1]]
        rank = np.arange(candidate_k, dtype=np.float64)[None, :]
        rank_weight = np.exp(-np.abs(rank - (k - 1)) / tau)
        margin_weight = 1.0 / (np.abs(ordered - kth) + 1e-3)
        weights = rank_weight * np.minimum(margin_weight, 1000.0)
        np.add.at(risk, ids.ravel(), weights.ravel())
        np.add.at(frequency, ids.ravel(), np.broadcast_to(1.0 / (rank + 1.0), ids.shape).ravel())
    return risk, frequency


def high_mask(score: np.ndarray, count: int) -> np.ndarray:
    mask = np.zeros(score.size, dtype=bool)
    chosen = np.argpartition(score, -count)[-count:]
    mask[chosen] = True
    return mask


def evaluate(
    docs_exact: np.ndarray,
    docs_approx: np.ndarray,
    queries: np.ndarray,
    k: int,
    batch: int,
) -> dict[str, float]:
    recalls: list[float] = []
    score_regrets: list[float] = []
    for start in range(0, len(queries), batch):
        q = queries[start : start + batch]
        exact_scores = q @ docs_exact.T
        approx_scores = q @ docs_approx.T
        exact = topk_ids(exact_scores, k)
        approx = topk_ids(approx_scores, k)
        for row in range(len(q)):
            recalls.append(len(set(exact[row]).intersection(approx[row])) / k)
            exact_k_score = exact_scores[row, exact[row]].mean()
            approx_true_score = exact_scores[row, approx[row]].mean()
            score_regrets.append(float(exact_k_score - approx_true_score))
    arr = np.asarray(recalls)
    regret = np.asarray(score_regrets)
    return {
        "mean_recall_at_k": float(arr.mean()),
        "p10_recall_at_k": float(np.quantile(arr, 0.10)),
        "perfect_query_fraction": float(np.mean(arr == 1.0)),
        "mean_true_score_regret": float(regret.mean()),
        "p95_true_score_regret": float(np.quantile(regret, 0.95)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    root = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/a0_topology_reuse")
    parser.add_argument(
        "--docs",
        type=Path,
        default=root / "embeddings/formal_100k/minilm_l6_v1_v2/old_corpus.fbin",
    )
    parser.add_argument(
        "--queries",
        type=Path,
        default=root / "embeddings/formal_100k/minilm_l6_v1_v2/old_queries.fbin",
    )
    parser.add_argument("--train-queries", type=int, default=400)
    parser.add_argument("--test-queries", type=int, default=400)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--candidate-k", type=int, default=64)
    parser.add_argument("--low-bits", type=int, default=2)
    parser.add_argument("--uniform-bits", type=int, default=4)
    parser.add_argument("--high-bits", type=int, default=8)
    parser.add_argument("--batch", type=int, default=20)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    started = time.time()
    rng = np.random.default_rng(args.seed)
    docs = normalize(read_fbin(args.docs))
    all_queries = normalize(read_fbin(args.queries))
    required = args.train_queries + args.test_queries
    if required > len(all_queries):
        raise ValueError(f"need {required} queries, have {len(all_queries)}")
    perm = rng.permutation(len(all_queries))[:required]
    train = all_queries[perm[: args.train_queries]]
    test = all_queries[perm[args.train_queries :]]

    # Robust global per-coordinate range; clipping a tiny number of outliers is
    # preferable to letting them determine every code step.
    lo = np.quantile(docs, 0.001, axis=0).astype(np.float32)
    hi = np.quantile(docs, 0.999, axis=0).astype(np.float32)
    low = quantize_global(docs, args.low_bits, lo, hi)
    uniform = quantize_global(docs, args.uniform_bits, lo, hi)
    high = quantize_global(docs, args.high_bits, lo, hi)

    fraction = (args.uniform_bits - args.low_bits) / (args.high_bits - args.low_bits)
    high_count = int(round(len(docs) * fraction))
    if not 0 < high_count < len(docs):
        raise ValueError("invalid matched-bit allocation")

    train_risk, train_frequency = risk_from_queries(
        docs, train, args.k, args.candidate_k, args.batch
    )
    test_risk, _ = risk_from_queries(docs, test, args.k, args.candidate_k, args.batch)
    low_error = np.mean((docs - low) ** 2, axis=1)

    masks = {
        "train_ranking_risk": high_mask(train_risk, high_count),
        "train_top_frequency": high_mask(train_frequency, high_count),
        "mse_oracle": high_mask(low_error, high_count),
        "test_risk_oracle_upper_bound": high_mask(test_risk, high_count),
    }
    random_mask = np.zeros(len(docs), dtype=bool)
    random_mask[rng.choice(len(docs), high_count, replace=False)] = True
    masks["random_mixed"] = random_mask

    results: dict[str, dict[str, float]] = {
        "uniform_4bit": evaluate(docs, uniform, test, args.k, args.batch),
        "uniform_low_bit": evaluate(docs, low, test, args.k, args.batch),
        "uniform_high_bit": evaluate(docs, high, test, args.k, args.batch),
    }
    for name, mask in masks.items():
        mixed = low.copy()
        mixed[mask] = high[mask]
        metrics = evaluate(docs, mixed, test, args.k, args.batch)
        metrics["high_precision_fraction"] = float(mask.mean())
        metrics["train_test_risk_jaccard"] = float(
            np.count_nonzero(mask & masks["test_risk_oracle_upper_bound"])
            / np.count_nonzero(mask | masks["test_risk_oracle_upper_bound"])
        )
        results[name] = metrics

    report = {
        "experiment": "ranking_risk_precision_a_minus_1",
        "question": "Does matched-byte variable precision have oracle top-k headroom over uniform precision?",
        "dataset": {"docs": str(args.docs), "queries": str(args.queries)},
        "shape": {"documents": list(docs.shape), "queries": list(all_queries.shape)},
        "config": {
            "train_queries": args.train_queries,
            "test_queries": args.test_queries,
            "k": args.k,
            "candidate_k": args.candidate_k,
            "low_bits": args.low_bits,
            "uniform_bits": args.uniform_bits,
            "high_bits": args.high_bits,
            "matched_high_fraction": fraction,
            "allocation_metadata_excluded": True,
            "seed": args.seed,
        },
        "results": results,
        "elapsed_seconds": time.time() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
