#!/usr/bin/env python3
"""Phenomenon gate for drift-native MOVE(id, x') vector indexing.

The experiment derives successive item/user embeddings from cumulative,
time-ordered MovieLens-20M interactions using a CPU sparse SVD.  Consecutive
spaces are Procrustes-aligned before measuring whether the same item IDs move
slightly enough for stale-anchor distance envelopes to remain selective.

This is deliberately not a full index implementation.  It tests the necessary
geometric premise before any graph/IVF maintenance engineering is attempted.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from scipy.cluster.vq import kmeans2
from scipy.linalg import orthogonal_procrustes
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import svds


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--ratings",
        type=Path,
        default=Path("/home/ubuntu/pz/VectorDB/data/vaq_semantic_g0/raw/ml-20m/ratings.csv"),
    )
    p.add_argument("--output", type=Path, default=Path("move_a0_results.json"))
    p.add_argument("--users", type=int, default=10_000)
    p.add_argument("--items", type=int, default=5_000)
    p.add_argument("--rank", type=int, default=32)
    p.add_argument("--queries", type=int, default=512)
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--ivf-cells", type=int, default=64)
    p.add_argument("--pq-blocks", type=int, default=4)
    p.add_argument("--pq-centroids", type=int, default=32)
    p.add_argument("--seed", type=int, default=7)
    return p.parse_args()


def normalize(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x, axis=1, keepdims=True)
    return x / np.maximum(n, 1e-12)


def top_ids(values: np.ndarray, n: int) -> np.ndarray:
    counts = np.bincount(values)
    n = min(n, np.count_nonzero(counts))
    ids = np.argpartition(counts, -n)[-n:]
    return ids[np.argsort(counts[ids])[::-1]]


def read_and_filter(path: Path, n_users: int, n_items: int) -> tuple[np.ndarray, ...]:
    raw = np.loadtxt(path, delimiter=",", skiprows=1, usecols=(0, 1, 3), dtype=np.int64)
    user_raw, item_raw, ts = raw.T
    keep_users = top_ids(user_raw, n_users)
    keep_items = top_ids(item_raw, n_items)

    user_map = np.full(int(user_raw.max()) + 1, -1, dtype=np.int32)
    item_map = np.full(int(item_raw.max()) + 1, -1, dtype=np.int32)
    user_map[keep_users] = np.arange(len(keep_users), dtype=np.int32)
    item_map[keep_items] = np.arange(len(keep_items), dtype=np.int32)
    mask = (user_map[user_raw] >= 0) & (item_map[item_raw] >= 0)
    return user_map[user_raw[mask]], item_map[item_raw[mask]], ts[mask], keep_users, keep_items


def factorize(
    users: np.ndarray,
    items: np.ndarray,
    ts: np.ndarray,
    cutoff: int,
    n_users: int,
    n_items: int,
    rank: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, int]:
    mask = ts <= cutoff
    # Binary implicit-feedback geometry; duplicate user-item interactions, if any,
    # are collapsed to one so rating frequency does not dominate the embedding.
    mat = coo_matrix(
        (np.ones(int(mask.sum()), dtype=np.float32), (users[mask], items[mask])),
        shape=(n_users, n_items),
    ).tocsr()
    mat.data[:] = 1.0
    u, s, vt = svds(mat, k=rank, which="LM", random_state=np.random.default_rng(seed))
    order = np.argsort(s)[::-1]
    u, s, vt = u[:, order], s[order], vt[order]
    scale = np.sqrt(np.maximum(s, 1e-12))
    user_vec = normalize(u * scale[None, :])
    item_vec = normalize(vt.T * scale[None, :])
    return user_vec.astype(np.float32), item_vec.astype(np.float32), int(mask.sum())


def align(curr_users: np.ndarray, curr_items: np.ndarray, prev_items: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rot, _ = orthogonal_procrustes(curr_items.astype(np.float64), prev_items.astype(np.float64))
    return normalize(curr_users @ rot).astype(np.float32), normalize(curr_items @ rot).astype(np.float32)


def exact_knn(x: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    sim = x @ x.T
    np.fill_diagonal(sim, -np.inf)
    idx = np.argpartition(sim, -(k + 1), axis=1)[:, -(k + 1) :]
    val = np.take_along_axis(sim, idx, axis=1)
    order = np.argsort(val, axis=1)[:, ::-1]
    return np.take_along_axis(idx, order, axis=1), np.take_along_axis(val, order, axis=1)


def row_overlap(a: np.ndarray, b: np.ndarray, k: int) -> np.ndarray:
    return np.asarray([len(set(x[:k]).intersection(y[:k])) / k for x, y in zip(a, b)], dtype=np.float64)


def assign_cells(x: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    d2 = (
        np.sum(x * x, axis=1, keepdims=True)
        + np.sum(centroids * centroids, axis=1)[None, :]
        - 2.0 * (x @ centroids.T)
    )
    return np.argmin(d2, axis=1)


def partition_stability(
    old: np.ndarray,
    new: np.ndarray,
    ivf_cells: int,
    pq_blocks: int,
    pq_centroids: int,
    seed: int,
) -> tuple[float, float]:
    centroids, old_cell = kmeans2(old, ivf_cells, minit="++", iter=30, seed=seed)
    new_cell = assign_cells(new, centroids)
    ivf_stay = float(np.mean(old_cell == new_cell))

    old_codes, new_codes = [], []
    for block, dims in enumerate(np.array_split(np.arange(old.shape[1]), pq_blocks)):
        c, oc = kmeans2(old[:, dims], pq_centroids, minit="++", iter=25, seed=seed + block + 1)
        old_codes.append(oc)
        new_codes.append(assign_cells(new[:, dims], c))
    old_codes = np.stack(old_codes, axis=1)
    new_codes = np.stack(new_codes, axis=1)
    pq_code_stay = float(np.mean(np.all(old_codes == new_codes, axis=1)))
    return ivf_stay, pq_code_stay


def envelope_expansion(
    old_items: np.ndarray,
    new_items: np.ndarray,
    new_users: np.ndarray,
    query_ids: np.ndarray,
    k: int,
) -> dict[str, float]:
    rho = np.linalg.norm(new_items - old_items, axis=1)
    expansions, recalls_2k, recalls_5k = [], [], []
    for start in range(0, len(query_ids), 64):
        q = new_users[query_ids[start : start + 64]]
        old_d = np.sqrt(np.maximum(0.0, 2.0 - 2.0 * (q @ old_items.T)))
        new_d = np.sqrt(np.maximum(0.0, 2.0 - 2.0 * (q @ new_items.T)))
        lower = np.maximum(0.0, old_d - rho[None, :])
        upper = old_d + rho[None, :]
        tau = np.partition(upper, k - 1, axis=1)[:, k - 1]
        candidates = lower <= tau[:, None]
        expansions.extend(candidates.sum(axis=1) / k)

        exact = np.argpartition(new_d, k - 1, axis=1)[:, :k]
        stale_order = np.argsort(old_d, axis=1)
        for row in range(len(q)):
            truth = set(exact[row].tolist())
            recalls_2k.append(len(truth.intersection(stale_order[row, : 2 * k])) / k)
            recalls_5k.append(len(truth.intersection(stale_order[row, : 5 * k])) / k)

    exp = np.asarray(expansions, dtype=np.float64)
    return {
        "candidate_expansion_mean": float(exp.mean()),
        "candidate_expansion_p50": float(np.quantile(exp, 0.50)),
        "candidate_expansion_p95": float(np.quantile(exp, 0.95)),
        "stale_top_2k_recall_mean": float(np.mean(recalls_2k)),
        "stale_top_5k_recall_mean": float(np.mean(recalls_5k)),
        "item_displacement_mean": float(rho.mean()),
        "item_displacement_p95": float(np.quantile(rho, 0.95)),
    }


def summarize_transition(
    old_items: np.ndarray,
    new_items: np.ndarray,
    new_users: np.ndarray,
    query_ids: np.ndarray,
    args: argparse.Namespace,
    transition_seed: int,
) -> dict[str, object]:
    old_knn, old_sim = exact_knn(old_items, args.k)
    new_knn, _ = exact_knn(new_items, args.k)
    overlap = row_overlap(old_knn, new_knn, args.k)
    old_margin = old_sim[:, args.k - 1] - old_sim[:, args.k]
    displacement = np.linalg.norm(new_items - old_items, axis=1)
    # A simple sufficient local condition.  It is intentionally conservative;
    # the envelope experiment below measures the stronger per-object bounds.
    stable_margin = old_margin > 4.0 * displacement
    ivf_stay, pq_stay = partition_stability(
        old_items,
        new_items,
        args.ivf_cells,
        args.pq_blocks,
        args.pq_centroids,
        transition_seed,
    )
    result: dict[str, object] = {
        "knn_overlap_mean": float(overlap.mean()),
        "knn_overlap_p10": float(np.quantile(overlap, 0.10)),
        "exact_topk_unchanged_fraction": float(np.mean(overlap == 1.0)),
        "simple_margin_certificate_fraction": float(np.mean(stable_margin)),
        "ivf_cell_stay_fraction": ivf_stay,
        "pq_full_code_stay_fraction": pq_stay,
    }
    result.update(envelope_expansion(old_items, new_items, new_users, query_ids, args.k))
    return result


def main() -> None:
    args = parse_args()
    started = time.time()
    users, items, ts, raw_users, raw_items = read_and_filter(args.ratings, args.users, args.items)
    # Close checkpoints avoid the artificial many-step interpolation criticized
    # in prior trajectory work; each point is learned from actual added ratings.
    fractions = np.asarray([0.85, 0.90, 0.95, 1.00])
    cutoffs = np.quantile(ts, fractions).astype(np.int64)
    snapshots: list[tuple[np.ndarray, np.ndarray]] = []
    interactions = []
    for step, cutoff in enumerate(cutoffs):
        u, v, used = factorize(
            users,
            items,
            ts,
            int(cutoff),
            len(raw_users),
            len(raw_items),
            args.rank,
            args.seed + step,
        )
        if snapshots:
            u, v = align(u, v, snapshots[-1][1])
        snapshots.append((u, v))
        interactions.append(used)

    rng = np.random.default_rng(args.seed)
    active_counts = np.bincount(users[ts <= cutoffs[0]], minlength=len(raw_users))
    active = np.flatnonzero(active_counts >= 5)
    query_ids = rng.choice(active, size=min(args.queries, len(active)), replace=False)

    transitions = []
    for step in range(1, len(snapshots)):
        entry = summarize_transition(
            snapshots[step - 1][1],
            snapshots[step][1],
            snapshots[step][0],
            query_ids,
            args,
            args.seed + 100 * step,
        )
        entry.update(
            {
                "from_fraction": float(fractions[step - 1]),
                "to_fraction": float(fractions[step]),
                "from_interactions": interactions[step - 1],
                "to_interactions": interactions[step],
            }
        )
        transitions.append(entry)

    gate = {
        "neighborhood_stability": all(t["knn_overlap_mean"] >= 0.80 for t in transitions),
        "partition_stability": all(t["ivf_cell_stay_fraction"] >= 0.80 for t in transitions),
        "envelope_selectivity": all(t["candidate_expansion_p50"] <= 3.0 for t in transitions),
    }
    verdict = "GO_DEEPER" if all(gate.values()) else "KILL_OR_RETHINK"
    out = {
        "experiment": "drift_native_move_a0",
        "dataset": str(args.ratings),
        "configuration": vars(args) | {"ratings": str(args.ratings), "output": str(args.output)},
        "selected_ratings": int(len(users)),
        "selected_users": int(len(raw_users)),
        "selected_items": int(len(raw_items)),
        "cutoffs": cutoffs.tolist(),
        "transitions": transitions,
        "gate": gate,
        "verdict": verdict,
        "wall_seconds": time.time() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
