#!/usr/bin/env python3
"""Audit the frozen local GIST1M fallback and prepare search inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import time
from pathlib import Path

import numpy as np

ROWS = 1_000_000
QUERIES = 1_000
DIM = 960
GT_K = 100
AUDIT_QIDS = (0, 17, 101, 257, 509, 997)
EXPECTED = {
    "full.bin": "fd57967ae1461c453336b9be9621c74a2b5927e74cafa9f5e899a5dc5df6a5b8",
    "query.bin": "220465f0ab851de6890d87ab1dd5081f526da8d214aa7a3849e738e63cad6775",
    "groundtruth.bin": "bba445688df6f531ce0c2f7a041916a283176d0011b192a5f01e18be563b33f1",
    "gist-960-euclidean.hdf5": "8e95831936bfdbfa0a56086942e2cf98cd703517c67f985914183eb4cdbf026a",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def matrix(path: Path, dtype: np.dtype) -> np.memmap:
    with path.open("rb") as handle:
        rows, dim = struct.unpack("<II", handle.read(8))
    return np.memmap(path, dtype=dtype, mode="r", offset=8, shape=(rows, dim))


def topk_smallest(values: np.ndarray, k: int) -> np.ndarray:
    ids = np.argpartition(values, k - 1)[:k]
    return ids[np.argsort(values[ids], kind="stable")]


parser = argparse.ArgumentParser()
parser.add_argument("--source-root", type=Path, required=True)
parser.add_argument("--hdf5", type=Path, required=True)
parser.add_argument("--data-root", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
started = time.time()

base_path = args.source_root / "full.bin"
query_path = args.source_root / "query.bin"
gt_path = args.source_root / "groundtruth.bin"
paths = [base_path, query_path, gt_path, args.hdf5]
hashes = {}
for path in paths:
    actual = sha256(path)
    expected = EXPECTED[path.name]
    if actual != expected:
        raise ValueError(f"{path}: sha256={actual}, expected={expected}")
    hashes[path.name] = actual

base = matrix(base_path, np.dtype("<f4"))
query = matrix(query_path, np.dtype("<f4"))
gt_ids = matrix(gt_path, np.dtype("<u4"))
if base.shape != (ROWS, DIM) or query.shape != (QUERIES, DIM) or gt_ids.shape != (QUERIES, GT_K):
    raise ValueError(f"shape mismatch: {base.shape}, {query.shape}, {gt_ids.shape}")
if not np.isfinite(base).all() or not np.isfinite(query).all():
    raise ValueError("non-finite GIST vector")
if int(gt_ids.max()) >= ROWS:
    raise ValueError("out-of-range GT ID")
if any(len(np.unique(row)) != GT_K for row in gt_ids):
    raise ValueError("duplicate GT ID")

gt_distances = np.empty((QUERIES, GT_K), dtype=np.float32)
violations = 0
for start in range(0, QUERIES, 8):
    stop = min(start + 8, QUERIES)
    ids = np.asarray(gt_ids[start:stop], dtype=np.int64)
    neighbors = np.asarray(base[ids], dtype=np.float32)
    delta = neighbors - np.asarray(query[start:stop])[:, None, :]
    distances = np.einsum("qkd,qkd->qk", delta, delta)
    gt_distances[start:stop] = distances
    violations += int(np.sum(np.diff(distances, axis=1) < -1e-4))
if violations:
    raise ValueError(f"GT distance order has {violations} violations")

base_norm_sq = np.einsum("ij,ij->i", base, base)
audits = {}
for qid in AUDIT_QIDS:
    q = np.asarray(query[qid])
    distances = base_norm_sq + float(np.dot(q, q)) - 2.0 * np.asarray(base @ q)
    exact = topk_smallest(distances, GT_K)
    supplied = np.asarray(gt_ids[qid], dtype=np.int64)
    overlap = len(set(map(int, exact)) & set(map(int, supplied)))
    if overlap != GT_K:
        raise ValueError(f"qid={qid}: exact/supplied top100 overlap={overlap}")
    audits[str(qid)] = {
        "top100_set_overlap": overlap,
        "tie_safe_top100": True,
        "exact_boundary_distance": float(distances[exact[-1]]),
    }

converted = args.data_root / "converted"
converted.mkdir(parents=True, exist_ok=True)
selected_base = converted / "gist_base.bin"
selected_query = converted / "gist_query.bin"
for source, target in ((base_path, selected_base), (query_path, selected_query)):
    if not target.exists():
        os.link(source, target)
    if os.path.samefile(source, target) is False:
        raise ValueError(f"{target} is not the frozen source inode")

canary = converted / "gist_query_canary200.bin"
warmup = converted / "gist_query_warmup900_999.bin"
truthset = converted / "gist_gt100.truthset"
with canary.open("wb") as handle:
    handle.write(struct.pack("<II", 200, DIM))
    handle.write(np.asarray(query[:200]).tobytes(order="C"))
with warmup.open("wb") as handle:
    handle.write(struct.pack("<II", 100, DIM))
    handle.write(np.asarray(query[900:1000]).tobytes(order="C"))
with truthset.open("wb") as handle:
    handle.write(struct.pack("<II", QUERIES, GT_K))
    handle.write(np.asarray(gt_ids, dtype=np.uint32).tobytes(order="C"))
    handle.write(gt_distances.tobytes(order="C"))

outputs = [selected_base, selected_query, canary, warmup, truthset]
result = {
    "status": "PASS",
    "dataset": "GIST1M-960D",
    "role": "dimension-stress fallback control",
    "maximum_positive_verdict": "HOLD-DATASET-SPECIFIC",
    "shape": {"base": list(base.shape), "query": list(query.shape), "groundtruth": list(gt_ids.shape)},
    "dtype": {"base": "float32", "query": "float32", "groundtruth": "uint32"},
    "source_hashes": hashes,
    "gt_monotonic_distance_violations": violations,
    "exact_audits": audits,
    "outputs": {
        str(path.relative_to(args.data_root)): {"bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in outputs
    },
    "elapsed_s": time.time() - started,
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, indent=2, sort_keys=True))
