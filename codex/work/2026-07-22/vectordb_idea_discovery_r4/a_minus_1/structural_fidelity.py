#!/usr/bin/env python3
"""A-1 probe: equal edge recall need not imply equal graph-structure fidelity.

The probe deliberately separates a phenomenon test from an ANN implementation.
It builds an exact k-NN graph, then creates equal-recall approximations whose
missed edges are concentrated on locally bridge-like or redundant edges.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import eigsh


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--data",
        default="/home/ubuntu/pz/VectorDB/data/vaq_semantic_g0/prepared/movielens_q12.npz",
    )
    p.add_argument("--per-group", type=int, default=250)
    p.add_argument("--k", type=int, default=15)
    p.add_argument("--candidate-k", type=int, default=45)
    p.add_argument("--recalls", type=float, nargs="+", default=[0.8, 0.9])
    p.add_argument("--seeds", type=int, nargs="+", default=[17, 29, 43])
    p.add_argument("--eigenvectors", type=int, default=10)
    p.add_argument("--output", required=True)
    return p.parse_args()


def stratified(vectors: np.ndarray, groups: np.ndarray, per_group: int, rng: np.random.Generator):
    chosen = []
    for g in np.unique(groups):
        ids = np.flatnonzero(groups == g)
        chosen.extend(rng.choice(ids, size=min(per_group, len(ids)), replace=False).tolist())
    chosen = np.asarray(chosen, dtype=np.int64)
    rng.shuffle(chosen)
    x = vectors[chosen].astype(np.float32, copy=True)
    x /= np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)
    return x, groups[chosen]


def exact_neighbors(x: np.ndarray, width: int, block: int = 256) -> np.ndarray:
    n = len(x)
    out = np.empty((n, width), dtype=np.int32)
    for start in range(0, n, block):
        stop = min(start + block, n)
        sim = x[start:stop] @ x.T
        sim[np.arange(stop - start), np.arange(start, stop)] = -np.inf
        ids = np.argpartition(sim, -width, axis=1)[:, -width:]
        vals = np.take_along_axis(sim, ids, axis=1)
        order = np.argsort(-vals, axis=1)
        out[start:stop] = np.take_along_axis(ids, order, axis=1)
    return out


def common_neighbor_scores(knn: np.ndarray) -> np.ndarray:
    n, k = knn.shape
    neighbor_sets = [set(row.tolist()) for row in knn]
    scores = np.empty((n, k), dtype=np.float32)
    for i, row in enumerate(knn):
        left = neighbor_sets[i]
        for j, dst in enumerate(row):
            right = neighbor_sets[int(dst)]
            scores[i, j] = len(left & right) / max(1, len(left | right))
    return scores


def approximate_neighbors(
    candidates: np.ndarray,
    overlap: np.ndarray,
    k: int,
    recall: float,
    policy: str,
    rng: np.random.Generator,
) -> np.ndarray:
    keep = int(round(k * recall))
    keep = min(k, max(1, keep))
    output = np.empty((len(candidates), k), dtype=np.int32)
    for i in range(len(candidates)):
        if policy == "random":
            retained = rng.choice(k, size=keep, replace=False)
        elif policy == "damage_bridge_like":
            # Delete low-overlap edges; retain the most locally redundant ones.
            retained = np.argsort(-overlap[i], kind="stable")[:keep]
        elif policy == "damage_redundant":
            # Delete high-overlap edges; retain locally bridge-like ones.
            retained = np.argsort(overlap[i], kind="stable")[:keep]
        else:
            raise ValueError(policy)
        wrong_pool = candidates[i, k:]
        wrong = rng.choice(wrong_pool, size=k - keep, replace=False)
        output[i] = np.concatenate((candidates[i, retained], wrong))
    return output


def adjacency(neighbors: np.ndarray) -> sparse.csr_matrix:
    n, k = neighbors.shape
    rows = np.repeat(np.arange(n), k)
    cols = neighbors.reshape(-1)
    a = sparse.coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n)).tocsr()
    a = a.maximum(a.T)
    a.data[:] = 1.0
    return a


def spectrum(a: sparse.csr_matrix, r: int):
    lap = sparse.csgraph.laplacian(a, normed=True)
    vals, vecs = eigsh(lap, k=r + 1, which="SM", tol=1e-4)
    order = np.argsort(vals)
    return lap, vals[order][1 : r + 1], vecs[:, order][:, 1 : r + 1]


def normalized_cut_proxy(a: sparse.csr_matrix, labels: np.ndarray) -> float:
    coo = sparse.triu(a, k=1).tocoo()
    if coo.nnz == 0:
        return 0.0
    return float(np.mean(labels[coo.row] != labels[coo.col]))


def metrics(
    exact_neighbors_: np.ndarray,
    exact_lap: sparse.csr_matrix,
    exact_vals: np.ndarray,
    exact_vecs: np.ndarray,
    approx_neighbors_: np.ndarray,
    labels: np.ndarray,
) -> dict:
    a = adjacency(approx_neighbors_)
    lap, vals, vecs = spectrum(a, len(exact_vals))
    edge_recall = np.mean(
        [len(set(e.tolist()) & set(q.tolist())) / len(e) for e, q in zip(exact_neighbors_, approx_neighbors_)]
    )
    singular = np.linalg.svd(exact_vecs.T @ vecs, compute_uv=False)
    max_sin_theta = float(np.sqrt(max(0.0, 1.0 - float(np.min(singular)) ** 2)))
    diff = lap - exact_lap
    spectral_error = float(max(abs(eigsh(diff, k=1, which="LM", return_eigenvectors=False, tol=1e-3)[0]), 0.0))
    return {
        "directed_edge_recall": float(edge_recall),
        "laplacian_operator_error": spectral_error,
        "low_eigenspace_max_sin_theta": max_sin_theta,
        "low_eigenvalue_l2_error": float(np.linalg.norm(vals - exact_vals)),
        "cross_label_edge_fraction": normalized_cut_proxy(a, labels),
        "connected_components": int(sparse.csgraph.connected_components(a, directed=False, return_labels=False)),
    }


def summarize(records: list[dict]) -> dict:
    keys = [k for k in records[0] if k not in {"policy", "seed"}]
    return {
        key: {
            "mean": float(np.mean([r[key] for r in records])),
            "min": float(np.min([r[key] for r in records])),
            "max": float(np.max([r[key] for r in records])),
        }
        for key in keys
    }


def main() -> None:
    cfg = args()
    started = time.time()
    raw = np.load(cfg.data)
    x, labels = stratified(raw["vectors"], raw["groups"], cfg.per_group, np.random.default_rng(7))
    candidates = exact_neighbors(x, cfg.candidate_k)
    exact = candidates[:, : cfg.k]
    overlap = common_neighbor_scores(exact)
    exact_a = adjacency(exact)
    exact_lap, exact_vals, exact_vecs = spectrum(exact_a, cfg.eigenvectors)
    records = []
    summaries = {}
    for recall in cfg.recalls:
        per_recall = []
        for seed in cfg.seeds:
            for policy in ["random", "damage_bridge_like", "damage_redundant"]:
                approx = approximate_neighbors(
                    candidates, overlap, cfg.k, recall, policy, np.random.default_rng(seed)
                )
                record = {
                    "target_recall": recall,
                    "policy": policy,
                    "seed": seed,
                    **metrics(exact, exact_lap, exact_vals, exact_vecs, approx, labels),
                }
                records.append(record)
                per_recall.append(record)
        summaries[str(recall)] = {
            policy: summarize([r for r in per_recall if r["policy"] == policy])
            for policy in ["random", "damage_bridge_like", "damage_redundant"]
        }
    result = {
        "experiment": "structural_fidelity_a_minus_1",
        "question": "At equal k-NN edge recall, does error placement materially alter graph structure?",
        "dataset": "MovieLens semantic vectors with genre groups",
        "config": {
            "data": cfg.data,
            "n": len(x),
            "dimension": x.shape[1],
            "groups": int(len(np.unique(labels))),
            "k": cfg.k,
            "candidate_k": cfg.candidate_k,
            "target_recalls": cfg.recalls,
            "seeds": cfg.seeds,
        },
        "exact_graph": {
            "cross_label_edge_fraction": normalized_cut_proxy(exact_a, labels),
            "connected_components": int(
                sparse.csgraph.connected_components(exact_a, directed=False, return_labels=False)
            ),
            "first_nontrivial_eigenvalues": exact_vals.tolist(),
        },
        "summary": summaries,
        "records": records,
        "elapsed_seconds": time.time() - started,
    }
    output = Path(cfg.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
