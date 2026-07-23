#!/usr/bin/env python3
"""Materialize one deterministic 10% PQ training sample and its row IDs."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 << 20):
            digest.update(chunk)
    return digest.hexdigest()


parser = argparse.ArgumentParser()
parser.add_argument("--base", type=Path, required=True)
parser.add_argument("--rows", type=int, default=100_000)
parser.add_argument("--seed", type=int, default=20_260_724)
parser.add_argument("--ids", type=Path, required=True)
parser.add_argument("--sample", type=Path, required=True)
parser.add_argument("--manifest", type=Path, required=True)
args = parser.parse_args()

with args.base.open("rb") as handle:
    npts, dim = struct.unpack("<II", handle.read(8))
if args.rows != npts // 10:
    raise ValueError(f"sample must be exactly 10%, got {args.rows}/{npts}")
base = np.memmap(args.base, dtype="<f4", mode="r", offset=8, shape=(npts, dim))
rng = np.random.default_rng(args.seed)
ids = np.sort(rng.choice(npts, size=args.rows, replace=False).astype(np.uint32))

args.ids.parent.mkdir(parents=True, exist_ok=True)
with args.ids.open("wb") as handle:
    handle.write(struct.pack("<II", args.rows, 1))
    handle.write(ids.tobytes(order="C"))
with args.sample.open("wb") as handle:
    handle.write(struct.pack("<II", args.rows, dim))
    for start in range(0, args.rows, 4096):
        handle.write(np.asarray(base[ids[start : start + 4096]], dtype="<f4").tobytes(order="C"))

manifest = {
    "status": "PASS",
    "seed": args.seed,
    "population_rows": npts,
    "sample_rows": args.rows,
    "fraction": args.rows / npts,
    "dimension": dim,
    "ids": str(args.ids),
    "ids_sha256": sha256(args.ids),
    "sample": str(args.sample),
    "sample_sha256": sha256(args.sample),
    "first_ids": ids[:10].tolist(),
    "last_ids": ids[-10:].tolist(),
}
args.manifest.parent.mkdir(parents=True, exist_ok=True)
args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
print(json.dumps(manifest, indent=2, sort_keys=True))
