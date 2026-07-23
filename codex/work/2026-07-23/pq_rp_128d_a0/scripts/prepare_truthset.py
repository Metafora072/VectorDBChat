#!/usr/bin/env python3
"""Append exact distances to official SIFT1M ground-truth IDs."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np


def matrix(path: Path, dtype: np.dtype) -> np.memmap:
    with path.open("rb") as handle:
        rows, dim = struct.unpack("<II", handle.read(8))
    return np.memmap(path, dtype=dtype, mode="r", offset=8, shape=(rows, dim))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 << 20):
            digest.update(chunk)
    return digest.hexdigest()


parser = argparse.ArgumentParser()
parser.add_argument("--base", type=Path, required=True)
parser.add_argument("--query", type=Path, required=True)
parser.add_argument("--official-ids", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--manifest", type=Path, required=True)
parser.add_argument("--reference", type=Path)
args = parser.parse_args()

base = matrix(args.base, np.float32)
queries = matrix(args.query, np.float32)
ids = matrix(args.official_ids, np.uint32)
if len(queries) != len(ids) or ids.shape[1] < 10 or base.shape[1] != queries.shape[1]:
    raise ValueError("incompatible SIFT matrices")
if np.any(ids >= len(base)):
    raise ValueError("official ground truth contains an out-of-range ID")

distances = np.empty(ids.shape, dtype=np.float32)
for start in range(0, len(ids), 256):
    stop = min(start + 256, len(ids))
    neighbors = np.asarray(base[np.asarray(ids[start:stop])], dtype=np.float32)
    delta = neighbors - np.asarray(queries[start:stop])[:, None, :]
    distances[start:stop] = np.einsum("qkd,qkd->qk", delta, delta)

args.output.parent.mkdir(parents=True, exist_ok=True)
with args.output.open("wb") as handle:
    handle.write(struct.pack("<II", *ids.shape))
    handle.write(np.asarray(ids, dtype=np.uint32).tobytes(order="C"))
    handle.write(distances.tobytes(order="C"))

manifest = {
    "base": str(args.base),
    "base_sha256": sha256(args.base),
    "query": str(args.query),
    "query_sha256": sha256(args.query),
    "official_ids": str(args.official_ids),
    "official_ids_sha256": sha256(args.official_ids),
    "output": str(args.output),
    "output_sha256": sha256(args.output),
    "shape": list(ids.shape),
    "distance": "squared_l2_for_official_ids_only",
    "ids_unchanged": True,
}
if args.reference is not None:
    reference = matrix(args.reference, np.uint32)
    count = min(len(reference), len(ids))
    top10_overlap = [
        len(set(reference[q, :10]) & set(ids[q, :10])) for q in range(count)
    ]
    top100_exact_set = [
        len(set(reference[q]) & set(ids[q])) == reference.shape[1] for q in range(count)
    ]
    manifest["reference"] = str(args.reference)
    manifest["reference_queries"] = count
    manifest["reference_mean_top10_overlap"] = float(np.mean(top10_overlap))
    manifest["reference_exact_top100_set_fraction"] = float(np.mean(top100_exact_set))
args.manifest.parent.mkdir(parents=True, exist_ok=True)
args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
print(json.dumps(manifest, indent=2, sort_keys=True))
