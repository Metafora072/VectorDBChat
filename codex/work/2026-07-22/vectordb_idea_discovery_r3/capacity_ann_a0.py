#!/usr/bin/env python3
"""A0 for capacity-constrained collective ANN candidate discovery.

The experiment uses real MovieLens user/item embeddings.  It asks whether
independent per-query top-L truncation can make the global assignment infeasible
or costly, and whether Hall-deficiency-directed list expansion uses materially
fewer candidate distances than uniform doubling.

Full similarities are computed only to provide an offline oracle and exact
assignment baseline; the candidate algorithms see ranked prefixes.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import deque
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from move_a0 import factorize, read_and_filter


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--ratings",
        type=Path,
        default=Path("/home/ubuntu/pz/VectorDB/data/vaq_semantic_g0/raw/ml-20m/ratings.csv"),
    )
    p.add_argument("--output", type=Path, default=Path("capacity_ann_a0_results.json"))
    p.add_argument("--users", type=int, default=10_000)
    p.add_argument("--items", type=int, default=5_000)
    p.add_argument("--rank", type=int, default=32)
    p.add_argument("--batch", type=int, default=512)
    p.add_argument("--capacities", type=int, nargs="+", default=[1, 2, 4])
    p.add_argument("--max-l", type=int, default=128)
    p.add_argument("--seed", type=int, default=23)
    return p.parse_args()


def hopcroft_karp(prefixes: np.ndarray, limits: np.ndarray, capacity: int) -> tuple[np.ndarray, np.ndarray]:
    """Maximum matching on query -> repeated-capacity item slots."""
    m = len(prefixes)
    n_items = int(prefixes.max()) + 1
    n_slots = n_items * capacity
    left = np.full(m, -1, dtype=np.int32)
    right = np.full(n_slots, -1, dtype=np.int32)
    dist = np.empty(m, dtype=np.int32)

    def neighbors(u: int):
        for item in prefixes[u, : limits[u]]:
            base = int(item) * capacity
            for slot in range(base, base + capacity):
                yield slot

    while True:
        q: deque[int] = deque()
        for u in range(m):
            if left[u] < 0:
                dist[u] = 0
                q.append(u)
            else:
                dist[u] = -1
        found = False
        while q:
            u = q.popleft()
            for v in neighbors(u):
                mate = right[v]
                if mate < 0:
                    found = True
                elif dist[mate] < 0:
                    dist[mate] = dist[u] + 1
                    q.append(int(mate))
        if not found:
            break

        def dfs(u: int) -> bool:
            for v in neighbors(u):
                mate = int(right[v])
                if mate < 0 or (dist[mate] == dist[u] + 1 and dfs(mate)):
                    left[u] = v
                    right[v] = u
                    return True
            dist[u] = -1
            return False

        progress = False
        for u in range(m):
            if left[u] < 0 and dfs(u):
                progress = True
        if not progress:
            break
    return left, right


def hall_reachable(
    prefixes: np.ndarray,
    limits: np.ndarray,
    capacity: int,
    left: np.ndarray,
    right: np.ndarray,
) -> np.ndarray:
    """Queries reachable from unmatched queries by alternating paths."""
    m = len(prefixes)
    seen_q = np.zeros(m, dtype=bool)
    seen_slot: set[int] = set()
    queue: deque[int] = deque(np.flatnonzero(left < 0).tolist())
    seen_q[left < 0] = True
    while queue:
        u = queue.popleft()
        matched_slot = int(left[u])
        for item in prefixes[u, : limits[u]]:
            base = int(item) * capacity
            for slot in range(base, base + capacity):
                if slot == matched_slot or slot in seen_slot:
                    continue
                seen_slot.add(slot)
                mate = int(right[slot])
                if mate >= 0 and not seen_q[mate]:
                    seen_q[mate] = True
                    queue.append(mate)
    return seen_q


def hall_adaptive(prefixes: np.ndarray, capacity: int, max_l: int) -> tuple[np.ndarray, bool, int, int]:
    m = len(prefixes)
    limits = np.ones(m, dtype=np.int32)
    rounds = 0
    while True:
        left, right = hopcroft_karp(prefixes, limits, capacity)
        if np.all(left >= 0):
            return limits, True, int(limits.sum()), rounds
        active = hall_reachable(prefixes, limits, capacity, left, right)
        if not np.any(active & (limits < max_l)):
            active = left < 0
        old = limits.copy()
        limits[active] = np.minimum(max_l, np.maximum(2, 2 * limits[active]))
        rounds += 1
        if np.array_equal(old, limits):
            return limits, False, int(limits.sum()), rounds


def uniform_min_l(prefixes: np.ndarray, capacity: int, max_l: int) -> tuple[int, bool]:
    l = 1
    while True:
        limits = np.full(len(prefixes), l, dtype=np.int32)
        left, _ = hopcroft_karp(prefixes, limits, capacity)
        if np.all(left >= 0):
            return l, True
        if l >= max_l:
            return l, False
        l = min(max_l, 2 * l)


def assignment_cost(cost: np.ndarray, prefixes: np.ndarray | None, limits: np.ndarray | None, capacity: int) -> float:
    expanded = np.repeat(cost, capacity, axis=1)
    if prefixes is not None and limits is not None:
        allowed = np.zeros(expanded.shape, dtype=bool)
        for u in range(len(prefixes)):
            for item in prefixes[u, : limits[u]]:
                base = int(item) * capacity
                allowed[u, base : base + capacity] = True
        expanded = np.where(allowed, expanded, 1e6)
    rows, cols = linear_sum_assignment(expanded)
    selected = expanded[rows, cols]
    if np.any(selected >= 1e5):
        return float("inf")
    return float(selected.sum())


def choose_batches(users: np.ndarray, active: np.ndarray, batch: int, seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    random_ids = rng.choice(active, size=batch, replace=False)
    center = int(rng.choice(active))
    sim = users[active] @ users[center]
    correlated_ids = active[np.argpartition(sim, -batch)[-batch:]]
    return {"random": random_ids, "correlated": correlated_ids}


def evaluate_batch(user_vec: np.ndarray, item_vec: np.ndarray, ids: np.ndarray, args: argparse.Namespace) -> dict[str, object]:
    sim = user_vec[ids] @ item_vec.T
    cost = 1.0 - sim
    prefixes = np.argsort(-sim, axis=1)[:, : args.max_l]
    top1_collision = 1.0 - len(np.unique(prefixes[:, 0])) / len(prefixes)
    out: dict[str, object] = {
        "top1_collision_fraction": float(top1_collision),
        "mean_pairwise_query_cosine": float(
            (np.sum((user_vec[ids] @ user_vec[ids].T)) - len(ids)) / (len(ids) * (len(ids) - 1))
        ),
        "capacities": {},
    }
    for capacity in args.capacities:
        exact_cost = assignment_cost(cost, None, None, capacity)
        uniform_l, uniform_feasible = uniform_min_l(prefixes, capacity, args.max_l)
        uniform_limits = np.full(len(ids), uniform_l, dtype=np.int32)
        uniform_cost = assignment_cost(cost, prefixes, uniform_limits, capacity) if uniform_feasible else float("inf")
        limits, adaptive_feasible, adaptive_calls, rounds = hall_adaptive(prefixes, capacity, args.max_l)
        adaptive_cost = assignment_cost(cost, prefixes, limits, capacity) if adaptive_feasible else float("inf")
        out["capacities"][str(capacity)] = {
            "exact_assignment_cost": exact_cost,
            "uniform_min_l": uniform_l,
            "uniform_candidate_calls": int(len(ids) * uniform_l),
            "uniform_feasible": uniform_feasible,
            "uniform_cost_regret_fraction": float(uniform_cost / exact_cost - 1.0),
            "adaptive_candidate_calls": adaptive_calls,
            "adaptive_rounds": rounds,
            "adaptive_feasible": adaptive_feasible,
            "adaptive_limit_mean": float(limits.mean()),
            "adaptive_limit_p95": float(np.quantile(limits, 0.95)),
            "adaptive_cost_regret_fraction": float(adaptive_cost / exact_cost - 1.0),
            "adaptive_call_saving_vs_uniform": float(1.0 - adaptive_calls / (len(ids) * uniform_l)),
        }
    return out


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
    counts = np.bincount(users, minlength=len(raw_users))
    active = np.flatnonzero(counts >= 20)
    batches = choose_batches(user_vec, active, args.batch, args.seed)
    metrics = {name: evaluate_batch(user_vec, item_vec, ids, args) for name, ids in batches.items()}
    cells = [v for b in metrics.values() for v in b["capacities"].values()]
    phenomenon = any(
        b["top1_collision_fraction"] >= 0.10
        and any(v["uniform_min_l"] >= 4 for v in b["capacities"].values())
        for b in metrics.values()
    )
    mechanism = any(
        v["adaptive_call_saving_vs_uniform"] >= 0.25
        and v["adaptive_cost_regret_fraction"] <= 0.05
        for v in cells
    )
    verdict = "GO_DEEPER" if phenomenon and mechanism else "KILL_OR_RETHINK"
    out = {
        "experiment": "capacity_constrained_collective_ann_a0",
        "dataset": str(args.ratings),
        "configuration": vars(args) | {"ratings": str(args.ratings), "output": str(args.output)},
        "selected_users": len(raw_users),
        "selected_items": len(raw_items),
        "interactions": interactions,
        "metrics": metrics,
        "gate": {
            "global_failure_phenomenon": phenomenon,
            "hall_expansion_mechanism": mechanism,
        },
        "verdict": verdict,
        "wall_seconds": time.time() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
