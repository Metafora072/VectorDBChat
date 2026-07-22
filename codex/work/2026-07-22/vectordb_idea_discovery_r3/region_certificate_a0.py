#!/usr/bin/env python3
"""A0 for sound region lower bounds in high-dimensional vector search.

For each IVF-like ball region, store its centroid and exact covering radius.
For a query q this gives the sound lower bound d(q, c)-R.  The script measures
the *best possible* exact top-k certificate cost obtainable from those bounds:
all regions whose lower bound is below the true kth distance must be opened.
If even this oracle-order cost approaches a scan, an online branch-and-bound
implementation cannot rescue the idea with the same metadata.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from scipy.cluster.vq import kmeans2


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--base",
        type=Path,
        default=Path("/home/ubuntu/pz/VectorDB/data/VectorDB/datasets/synthetic_128d_100k/base.fvecs"),
    )
    p.add_argument(
        "--queries",
        type=Path,
        default=Path("/home/ubuntu/pz/VectorDB/data/VectorDB/datasets/synthetic_128d_100k/query.fvecs"),
    )
    p.add_argument("--output", type=Path, default=Path("region_certificate_a0_results.json"))
    p.add_argument("--n", type=int, default=100_000)
    p.add_argument("--nq", type=int, default=256)
    p.add_argument("--cells", type=int, default=128)
    p.add_argument("--subcells", type=int, default=4)
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--train", type=int, default=20_000)
    p.add_argument("--seed", type=int, default=11)
    return p.parse_args()


def read_fvecs(path: Path, limit: int | None = None) -> np.ndarray:
    raw = np.fromfile(path, dtype=np.int32)
    d = int(raw[0])
    rows = raw.reshape(-1, d + 1)
    if not np.all(rows[:, 0] == d):
        raise ValueError(f"invalid fvecs file: {path}")
    out = rows[:, 1:].view(np.float32)
    return np.asarray(out[:limit], dtype=np.float32)


def assign(x: np.ndarray, centers: np.ndarray, block: int = 4096) -> np.ndarray:
    out = np.empty(len(x), dtype=np.int32)
    c2 = np.sum(centers * centers, axis=1)
    for start in range(0, len(x), block):
        xb = x[start : start + block]
        d2 = np.sum(xb * xb, axis=1, keepdims=True) + c2[None, :] - 2.0 * xb @ centers.T
        out[start : start + len(xb)] = np.argmin(d2, axis=1)
    return out


def make_regions(
    x: np.ndarray,
    cells: int,
    subcells: int,
    train: int,
    seed: int,
) -> list[tuple[str, np.ndarray, np.ndarray, np.ndarray]]:
    rng = np.random.default_rng(seed)
    sample = x[rng.choice(len(x), size=min(train, len(x)), replace=False)]
    centers, _ = kmeans2(sample, cells, minit="++", iter=20, seed=seed)
    labels = assign(x, centers)

    def summarize(c: np.ndarray, lab: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        sizes = np.bincount(lab, minlength=len(c)).astype(np.int64)
        radii = np.zeros(len(c), dtype=np.float32)
        for rid in range(len(c)):
            ids = np.flatnonzero(lab == rid)
            if len(ids):
                radii[rid] = np.sqrt(np.max(np.sum((x[ids] - c[rid]) ** 2, axis=1)))
        return c.astype(np.float32), radii, sizes

    coarse = summarize(centers, labels)
    levels = [("coarse",) + coarse]
    if subcells <= 1:
        return levels

    fine_centers: list[np.ndarray] = []
    fine_labels = np.empty(len(x), dtype=np.int32)
    offset = 0
    for cid in range(cells):
        ids = np.flatnonzero(labels == cid)
        if len(ids) < subcells:
            fine_centers.append(centers[cid : cid + 1])
            fine_labels[ids] = offset
            offset += 1
            continue
        local_train = x[rng.choice(ids, size=min(len(ids), max(256, train // cells)), replace=False)]
        local_c, _ = kmeans2(local_train, subcells, minit="++", iter=15, seed=seed + cid + 1)
        local_lab = assign(x[ids], local_c)
        fine_centers.append(local_c)
        fine_labels[ids] = offset + local_lab
        offset += len(local_c)
    fine_c = np.concatenate(fine_centers, axis=0)
    fine = summarize(fine_c, fine_labels)
    levels.append((f"fine_x{subcells}",) + fine)
    return levels


def evaluate(
    x: np.ndarray,
    q: np.ndarray,
    regions: list[tuple[str, np.ndarray, np.ndarray, np.ndarray]],
    k: int,
) -> dict[str, object]:
    result: dict[str, object] = {}
    scan_fractions: dict[str, list[float]] = {name: [] for name, *_ in regions}
    zero_lb: dict[str, list[float]] = {name: [] for name, *_ in regions}
    for start in range(0, len(q), 32):
        qb = q[start : start + 32]
        # Exact ground truth is used only by the offline gate.
        d2 = (
            np.sum(qb * qb, axis=1, keepdims=True)
            + np.sum(x * x, axis=1)[None, :]
            - 2.0 * qb @ x.T
        )
        dk = np.sqrt(np.maximum(0.0, np.partition(d2, k - 1, axis=1)[:, k - 1]))
        for name, centers, radii, sizes in regions:
            cd = np.sqrt(
                np.maximum(
                    0.0,
                    np.sum(qb * qb, axis=1, keepdims=True)
                    + np.sum(centers * centers, axis=1)[None, :]
                    - 2.0 * qb @ centers.T,
                )
            )
            lower = np.maximum(0.0, cd - radii[None, :])
            must_open = lower < dk[:, None]
            scan_fractions[name].extend((must_open @ sizes / len(x)).tolist())
            zero_lb[name].extend(np.mean(lower <= 1e-12, axis=1).tolist())

    for name, *_ in regions:
        f = np.asarray(scan_fractions[name])
        z = np.asarray(zero_lb[name])
        result[name] = {
            "regions": int(next(len(c) for n, c, *_ in regions if n == name)),
            "oracle_certificate_scan_fraction_mean": float(f.mean()),
            "oracle_certificate_scan_fraction_p50": float(np.quantile(f, 0.50)),
            "oracle_certificate_scan_fraction_p95": float(np.quantile(f, 0.95)),
            "zero_lower_bound_region_fraction_mean": float(z.mean()),
        }
    return result


def main() -> None:
    args = parse_args()
    started = time.time()
    x = read_fvecs(args.base, args.n)
    q = read_fvecs(args.queries, args.nq)
    regions = make_regions(x, args.cells, args.subcells, args.train, args.seed)
    metrics = evaluate(x, q, regions, args.k)
    best = min(v["oracle_certificate_scan_fraction_p50"] for v in metrics.values())
    verdict = "GO_DEEPER" if best <= 0.50 else "KILL_OR_RETHINK"
    out = {
        "experiment": "sound_region_certificate_a0",
        "dataset": {"base": str(args.base), "queries": str(args.queries)},
        "configuration": vars(args) | {
            "base": str(args.base),
            "queries": str(args.queries),
            "output": str(args.output),
        },
        "metrics": metrics,
        "gate": {"best_p50_scan_fraction_le_0_50": bool(best <= 0.50)},
        "verdict": verdict,
        "wall_seconds": time.time() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
