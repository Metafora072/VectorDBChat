#!/usr/bin/env python3
"""Split SIFT1M .bin file into BUILD (first 700K) and INSERT (remaining 300K)."""
import struct
import sys
import numpy as np

src = "/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin"
out_dir = "/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-22/p01_pq_staleness_a0"

with open(src, "rb") as f:
    npts, ndim = struct.unpack("II", f.read(8))
    print(f"Source: {npts} points, {ndim} dims")
    data = np.frombuffer(f.read(npts * ndim * 4), dtype=np.float32).reshape(npts, ndim)

split = 700_000
build = data[:split]
insert = data[split:]
print(f"BUILD: {build.shape[0]} points, INSERT: {insert.shape[0]} points")

for name, arr in [("build_700k.bin", build), ("insert_300k.bin", insert)]:
    path = f"{out_dir}/{name}"
    with open(path, "wb") as f:
        f.write(struct.pack("II", arr.shape[0], arr.shape[1]))
        f.write(arr.tobytes())
    print(f"Wrote {path} ({arr.shape[0]} x {arr.shape[1]})")

print("Done.")
