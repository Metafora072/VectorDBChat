#!/usr/bin/env python3
"""Validate Atlas exact-GT files, including an independent brute-force audit."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import numpy as np


def read_header(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        raw = f.read(8)
    if len(raw) != 8:
        raise ValueError(f"short header: {path}")
    return struct.unpack("<II", raw)


def read_float_bin(path: Path) -> np.memmap:
    npts, dim = read_header(path)
    expected = 8 + npts * dim * 4
    if path.stat().st_size != expected:
        raise ValueError(f"size mismatch: {path}")
    return np.memmap(path, dtype="<f4", mode="r", offset=8, shape=(npts, dim))


def read_tags(path: Path) -> np.ndarray:
    npts, dim = read_header(path)
    if dim != 1 or path.stat().st_size != 8 + npts * 4:
        raise ValueError(f"invalid tag file: {path}")
    return np.memmap(path, dtype="<u4", mode="r", offset=8, shape=(npts,))


def read_truthset(path: Path) -> tuple[np.ndarray, np.ndarray]:
    nqueries, k = read_header(path)
    expected = 8 + nqueries * k * 8
    if path.stat().st_size != expected:
        raise ValueError(f"invalid truthset size: {path}")
    ids = np.memmap(path, dtype="<u4", mode="r", offset=8, shape=(nqueries, k))
    dists = np.memmap(
        path,
        dtype="<f4",
        mode="r",
        offset=8 + nqueries * k * 4,
        shape=(nqueries, k),
    )
    return ids, dists


def brute_force_topk(base: np.memmap, tags: np.ndarray, query: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    # Chunking bounds peak temporary memory for GIST-960D.
    best_ids = np.empty(0, dtype=np.uint32)
    best_dists = np.empty(0, dtype=np.float32)
    for start in range(0, base.shape[0], 8192):
        block = np.asarray(base[start : start + 8192], dtype=np.float32)
        diff = block - query
        dists = np.einsum("ij,ij->i", diff, diff, optimize=True)
        block_ids = np.asarray(tags[start : start + block.shape[0]], dtype=np.uint32)
        if best_ids.size:
            dists = np.concatenate((best_dists, dists))
            block_ids = np.concatenate((best_ids, block_ids))
        take = min(k, dists.size)
        idx = np.argpartition(dists, take - 1)[:take]
        order = np.lexsort((block_ids[idx], dists[idx]))
        best_dists = dists[idx][order].astype(np.float32, copy=False)
        best_ids = block_ids[idx][order]
    return best_ids, best_dists


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--groundtruth", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--audit-query-ids", default="0,17")
    p.add_argument(
        "--checkpoints",
        default="0,5,10,20",
        help="comma-separated checkpoint percentages to validate",
    )
    args = p.parse_args()

    queries = read_float_bin(args.dataset / "query.bin")
    audit_qids = [int(value) for value in args.audit_query_ids.split(",")]
    report: dict[str, object] = {
        "schema": "dynamic-vamana-atlas-gt-validation-v1",
        "dataset": args.dataset.name,
        "audit_query_ids": audit_qids,
        "checkpoints": [],
    }

    checkpoints = tuple(int(value) for value in args.checkpoints.split(",") if value)
    if not checkpoints or any(pct not in (0, 5, 10, 20) for pct in checkpoints):
        raise ValueError("--checkpoints must be a non-empty subset of 0,5,10,20")
    for pct in checkpoints:
        cp = f"cp{pct:02d}"
        base = read_float_bin(args.dataset / f"active_{cp}.bin")
        tags = read_tags(args.dataset / f"active_{cp}.tags.bin")
        ids, dists = read_truthset(args.groundtruth / f"gt_{cp}")
        if ids.shape != (queries.shape[0], 100):
            raise ValueError(f"unexpected GT shape for {cp}: {ids.shape}")
        if base.shape[0] != tags.size or base.shape[1] != queries.shape[1]:
            raise ValueError(f"base/tag/query mismatch for {cp}")
        active = set(np.asarray(tags).tolist())
        missing = int(sum(int(tag) not in active for tag in np.asarray(ids).ravel()))
        finite = bool(np.isfinite(dists).all())
        monotonic = bool(np.all(dists[:, 1:] >= dists[:, :-1]))
        audits = []
        tag_to_row = np.full(int(np.max(tags)) + 1, -1, dtype=np.int64)
        tag_to_row[np.asarray(tags, dtype=np.int64)] = np.arange(tags.size, dtype=np.int64)
        for qid in audit_qids:
            exact_ids, exact_dists = brute_force_topk(base, tags, np.asarray(queries[qid]), ids.shape[1])
            id_match = bool(np.array_equal(np.asarray(ids[qid]), exact_ids))
            max_abs_dist_error = float(np.max(np.abs(np.asarray(dists[qid]) - exact_dists)))
            returned_rows = tag_to_row[np.asarray(ids[qid], dtype=np.int64)]
            if np.any(returned_rows < 0):
                raise ValueError(f"GT returned inactive tag for {cp} qid={qid}")
            returned_vectors = np.asarray(base[returned_rows], dtype=np.float32)
            returned_diff = returned_vectors - np.asarray(queries[qid], dtype=np.float32)
            returned_true_dists = np.einsum("ij,ij->i", returned_diff, returned_diff, optimize=True)
            max_reported_distance_error = float(
                np.max(np.abs(np.asarray(dists[qid]) - returned_true_dists))
            )
            overlap = int(np.intersect1d(np.asarray(ids[qid]), exact_ids).size)
            tie_safe = bool(
                max_abs_dist_error <= 5e-3
                and max_reported_distance_error <= 5e-3
                and float(np.max(returned_true_dists)) <= float(exact_dists[-1]) + 5e-3
            )
            if not tie_safe:
                raise ValueError(
                    f"independent audit failed for {cp} qid={qid}: "
                    f"id_match={id_match}, overlap={overlap}, "
                    f"max_abs_dist_error={max_abs_dist_error}, "
                    f"max_reported_distance_error={max_reported_distance_error}"
                )
            audits.append(
                {
                    "query_id": qid,
                    "top100_id_exact_match": id_match,
                    "top100_id_overlap": overlap,
                    "tie_safe_top100": tie_safe,
                    "max_abs_distance_error": max_abs_dist_error,
                    "max_reported_distance_error": max_reported_distance_error,
                }
            )
        if missing or not finite or not monotonic:
            raise ValueError(
                f"structural validation failed for {cp}: "
                f"missing={missing}, finite={finite}, monotonic={monotonic}"
            )
        report["checkpoints"].append(
            {
                "checkpoint_pct": pct,
                "nqueries": int(ids.shape[0]),
                "k": int(ids.shape[1]),
                "all_tags_active": True,
                "distances_finite": finite,
                "distances_monotonic": monotonic,
                "independent_bruteforce_audits": audits,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
