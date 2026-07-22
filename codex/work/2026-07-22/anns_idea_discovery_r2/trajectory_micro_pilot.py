#!/usr/bin/env python3
"""CPU-only micro pilot for closed-loop ANN trajectory divergence.

This is deliberately a phenomenon check, not paper evidence. It compares ANN
search on an exact-query replay (open loop) with the same ANN inside two simple
vector feedback laws (closed loop).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import hnswlib
import numpy as np


def load_diskann_bin(path: Path, limit: int | None = None) -> np.ndarray:
    header = np.fromfile(path, dtype=np.int32, count=2)
    if header.size != 2:
        raise ValueError(f"invalid DiskANN bin header: {path}")
    n, d = map(int, header)
    if limit is not None:
        n = min(n, limit)
    return np.memmap(path, dtype=np.float32, mode="r", offset=8, shape=(n, d))


class ExactL2:
    def __init__(self, data: np.ndarray):
        self.data = np.asarray(data, dtype=np.float32)
        self.norms = np.einsum("ij,ij->i", self.data, self.data)

    def topk(self, query: np.ndarray, k: int) -> np.ndarray:
        q = np.asarray(query, dtype=np.float32)
        distances = self.norms - 2.0 * (self.data @ q) + float(q @ q)
        ids = np.argpartition(distances, k - 1)[:k]
        return ids[np.argsort(distances[ids])]


def update_query(
    law: str,
    query: np.ndarray,
    initial_query: np.ndarray,
    result_ids: np.ndarray,
    data: np.ndarray,
    beta: float,
) -> np.ndarray:
    if law == "centroid":
        target = np.asarray(data[result_ids[:3]]).mean(axis=0)
        return ((1.0 - beta) * query + beta * target).astype(np.float32)
    if law == "rocchio":
        positive = np.asarray(data[result_ids[:3]]).mean(axis=0)
        negative = np.asarray(data[result_ids[-3:]]).mean(axis=0)
        return (0.35 * initial_query + 0.90 * query + beta * (positive - negative)).astype(
            np.float32
        )
    raise ValueError(f"unknown feedback law: {law}")


def overlap(left: np.ndarray, right: np.ndarray) -> float:
    return len(set(map(int, left)) & set(map(int, right))) / len(left)


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), q))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--npoints", type=int, default=100_000)
    parser.add_argument("--nqueries", type=int, default=80)
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--beta", type=float, default=0.45)
    parser.add_argument("--efs", type=int, nargs="+", default=[12, 20, 40, 80])
    args = parser.parse_args()

    started = time.time()
    data = load_diskann_bin(args.data, args.npoints)
    queries = load_diskann_bin(args.queries, args.nqueries)
    if data.shape[1] != queries.shape[1]:
        raise ValueError("data/query dimensions differ")

    exact = ExactL2(data)
    index = hnswlib.Index(space="l2", dim=data.shape[1])
    index.init_index(max_elements=len(data), ef_construction=120, M=16, random_seed=17)
    index.set_num_threads(16)
    index.add_items(np.asarray(data), np.arange(len(data), dtype=np.int64))

    records: list[dict[str, float | int | str]] = []
    for law in ("centroid", "rocchio"):
        reference: list[list[tuple[np.ndarray, np.ndarray]]] = []
        for initial in np.asarray(queries):
            q = initial.copy()
            trajectory: list[tuple[np.ndarray, np.ndarray]] = []
            for _ in range(args.horizon):
                result = exact.topk(q, args.k)
                trajectory.append((q.copy(), result.copy()))
                q = update_query(law, q, initial, result, data, args.beta)
            reference.append(trajectory)

        for ef in args.efs:
            index.set_ef(max(ef, args.k))
            local_recalls: list[float] = []
            open_recalls: list[float] = []
            trajectory_overlaps: list[float] = []
            terminal_overlaps: list[float] = []
            terminal_divergences: list[float] = []

            for initial, exact_trajectory in zip(np.asarray(queries), reference):
                q = initial.copy()
                initial_scale = max(
                    1e-6,
                    float(np.linalg.norm(initial - np.asarray(data[exact_trajectory[0][1][0]]))),
                )
                for step, (q_star, result_star) in enumerate(exact_trajectory):
                    approx_ids, _ = index.knn_query(q, k=args.k)
                    approx_ids = approx_ids[0]
                    local_exact = exact.topk(q, args.k)
                    local_recalls.append(overlap(approx_ids, local_exact))
                    trajectory_overlaps.append(overlap(approx_ids, result_star))

                    replay_ids, _ = index.knn_query(q_star, k=args.k)
                    open_recalls.append(overlap(replay_ids[0], result_star))

                    if step == args.horizon - 1:
                        terminal_overlaps.append(overlap(approx_ids, result_star))
                        terminal_divergences.append(
                            float(np.linalg.norm(q - q_star)) / initial_scale
                        )
                    q = update_query(law, q, initial, approx_ids, data, args.beta)

            records.append(
                {
                    "law": law,
                    "ef": ef,
                    "mean_local_recall": float(np.mean(local_recalls)),
                    "mean_open_loop_recall": float(np.mean(open_recalls)),
                    "mean_trajectory_overlap": float(np.mean(trajectory_overlaps)),
                    "mean_terminal_overlap": float(np.mean(terminal_overlaps)),
                    "p10_terminal_overlap": percentile(terminal_overlaps, 10),
                    "mean_terminal_query_divergence": float(np.mean(terminal_divergences)),
                    "p90_terminal_query_divergence": percentile(terminal_divergences, 90),
                }
            )

    payload = {
        "status": "phenomenon_micro_pilot_only",
        "dataset": str(args.data),
        "npoints": len(data),
        "nqueries": len(queries),
        "dimension": data.shape[1],
        "horizon": args.horizon,
        "k": args.k,
        "beta": args.beta,
        "elapsed_seconds": time.time() - started,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
