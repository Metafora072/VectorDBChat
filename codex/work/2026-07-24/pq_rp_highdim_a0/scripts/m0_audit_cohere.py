#!/usr/bin/env python3
"""Strict Cohere M0 audit and lossless DiskANN-format conversion."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import time
from pathlib import Path

import numpy as np

BASE_ROWS = 1_000_000
QUERY_ROWS = 1_000
DIM = 768
GT_K = 1_000
AUDIT_QIDS = (0, 17, 101, 257, 509, 997)
NORM_TOL = 1e-4


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def require_size(path: Path, expected: int) -> None:
    actual = path.stat().st_size
    if actual != expected:
        raise ValueError(f"{path.name}: size={actual}, expected={expected}")


def audit_vectors(matrix: np.memmap, label: str, block: int = 8192) -> dict:
    min_norm = float("inf")
    max_norm = float("-inf")
    max_error = 0.0
    for start in range(0, len(matrix), block):
        values = np.asarray(matrix[start : start + block])
        if not np.isfinite(values).all():
            raise ValueError(f"{label}: non-finite value in rows {start}:{start + len(values)}")
        norms = np.linalg.norm(values, axis=1)
        min_norm = min(min_norm, float(norms.min()))
        max_norm = max(max_norm, float(norms.max()))
        max_error = max(max_error, float(np.max(np.abs(norms - 1.0))))
    if max_error > NORM_TOL:
        raise ValueError(f"{label}: max |norm-1|={max_error:.9g} exceeds {NORM_TOL}")
    return {"min_norm": min_norm, "max_norm": max_norm, "max_abs_norm_error": max_error}


def topk(values: np.ndarray, k: int, largest: bool) -> np.ndarray:
    if largest:
        ids = np.argpartition(values, -k)[-k:]
        return ids[np.argsort(values[ids], kind="stable")[::-1]]
    ids = np.argpartition(values, k - 1)[:k]
    return ids[np.argsort(values[ids], kind="stable")]


def write_headered(raw: Path, output: Path, rows: int, dim: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as dst:
        dst.write(struct.pack("<II", rows, dim))
        with raw.open("rb") as src:
            shutil.copyfileobj(src, dst, length=16 << 20)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    started = time.time()
    raw = args.data_root / "raw/cohere"
    converted = args.data_root / "converted"
    base_path = raw / "cohere_train.f32"
    query_path = raw / "cohere_test.f32"
    gt_path = raw / "cohere_groundtruth.i32"
    readme_path = raw / "README.md"

    require_size(base_path, BASE_ROWS * DIM * 4)
    require_size(query_path, QUERY_ROWS * DIM * 4)
    require_size(gt_path, QUERY_ROWS * GT_K * 4)
    readme = readme_path.read_text()
    if "apache-2.0" not in readme.lower():
        raise ValueError("README does not declare apache-2.0")

    base = np.memmap(base_path, dtype="<f4", mode="r", shape=(BASE_ROWS, DIM))
    query = np.memmap(query_path, dtype="<f4", mode="r", shape=(QUERY_ROWS, DIM))
    gt_i32 = np.memmap(gt_path, dtype="<i4", mode="r", shape=(QUERY_ROWS, GT_K))
    if int(gt_i32.min()) < 0 or int(gt_i32.max()) >= BASE_ROWS:
        raise ValueError("ground truth contains out-of-range ID")
    duplicate_rows = sum(len(np.unique(row)) != GT_K for row in gt_i32)
    if duplicate_rows:
        raise ValueError(f"ground truth has duplicate IDs in {duplicate_rows} rows")

    base_norms = audit_vectors(base, "base")
    query_norms = audit_vectors(query, "query", block=1000)

    gt_distances = np.empty((QUERY_ROWS, GT_K), dtype=np.float32)
    monotonic_violations = 0
    for start in range(0, QUERY_ROWS, 8):
        stop = min(start + 8, QUERY_ROWS)
        ids = np.asarray(gt_i32[start:stop], dtype=np.int64)
        neighbors = np.asarray(base[ids], dtype=np.float32)
        delta = neighbors - np.asarray(query[start:stop])[:, None, :]
        distances = np.einsum("qkd,qkd->qk", delta, delta)
        gt_distances[start:stop] = distances
        monotonic_violations += int(np.sum(np.diff(distances, axis=1) < -1e-5))
    if monotonic_violations:
        raise ValueError(f"ground-truth distance order has {monotonic_violations} violations")

    audits = {}
    base_norm_sq = np.einsum("ij,ij->i", base, base)
    for qid in AUDIT_QIDS:
        q = np.asarray(query[qid])
        cosine = np.asarray(base @ q)
        l2_formula = base_norm_sq + float(np.dot(q, q)) - 2.0 * cosine
        cosine_ids = topk(cosine, 100, largest=True)
        l2_ids = topk(l2_formula, 100, largest=False)
        supplied = np.asarray(gt_i32[qid, :100], dtype=np.int64)
        cosine_set = set(map(int, cosine_ids))
        l2_set = set(map(int, l2_ids))
        supplied_set = set(map(int, supplied))
        if cosine_set != supplied_set:
            raise ValueError(
                f"qid={qid}: exact cosine top100 differs from supplied GT "
                f"(overlap={len(cosine_set & supplied_set)})"
            )
        if cosine_set != l2_set:
            raise ValueError(
                f"qid={qid}: cosine/L2 top100 differ "
                f"(overlap={len(cosine_set & l2_set)})"
            )
        audits[str(qid)] = {
            "supplied_cosine_top100_overlap": 100,
            "cosine_l2_top100_overlap": 100,
            "cosine_boundary_score": float(cosine[cosine_ids[-1]]),
            "l2_boundary_distance": float(l2_formula[l2_ids[-1]]),
        }

    base_bin = converted / "cohere_base.bin"
    query_bin = converted / "cohere_query.bin"
    canary_bin = converted / "cohere_query_canary200.bin"
    warmup_bin = converted / "cohere_query_warmup900_999.bin"
    truthset = converted / "cohere_gt1000.truthset"
    write_headered(base_path, base_bin, BASE_ROWS, DIM)
    write_headered(query_path, query_bin, QUERY_ROWS, DIM)
    with canary_bin.open("wb") as handle:
        handle.write(struct.pack("<II", 200, DIM))
        handle.write(np.asarray(query[:200]).tobytes(order="C"))
    with warmup_bin.open("wb") as handle:
        handle.write(struct.pack("<II", 100, DIM))
        handle.write(np.asarray(query[900:1000]).tobytes(order="C"))
    with truthset.open("wb") as handle:
        handle.write(struct.pack("<II", QUERY_ROWS, GT_K))
        handle.write(np.asarray(gt_i32, dtype=np.uint32).tobytes(order="C"))
        handle.write(gt_distances.tobytes(order="C"))

    files = [
        readme_path,
        base_path,
        query_path,
        gt_path,
        base_bin,
        query_bin,
        canary_bin,
        warmup_bin,
        truthset,
    ]
    result = {
        "status": "PASS",
        "dataset": "Cohere-1M-wikipedia-768d",
        "shape": {
            "base": [BASE_ROWS, DIM],
            "query": [QUERY_ROWS, DIM],
            "groundtruth": [QUERY_ROWS, GT_K],
        },
        "dtype": {"base": "float32", "query": "float32", "groundtruth": "int32"},
        "license": "apache-2.0",
        "base_norms": base_norms,
        "query_norms": query_norms,
        "gt_id_min": int(gt_i32.min()),
        "gt_id_max": int(gt_i32.max()),
        "gt_duplicate_rows": duplicate_rows,
        "gt_monotonic_distance_violations": monotonic_violations,
        "exact_audits": audits,
        "files": {
            str(path.relative_to(args.data_root)): {
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in files
        },
        "elapsed_s": time.time() - started,
        "pid": os.getpid(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
