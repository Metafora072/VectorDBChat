#!/usr/bin/env python3
"""Create the immutable Z0A 2K same-tag replacement input."""
import argparse
import hashlib
import json
import struct
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True, type=Path)
    p.add_argument("--data", type=Path)
    p.add_argument("--tags", type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--count", type=int, default=2000)
    a = p.parse_args()
    if a.count != 2000:
        raise SystemExit("Z0A preflight fixes the short workload at 2000 replacements")
    base = a.data or (a.dataset / "base.bin")
    tags = a.tags or (a.dataset / "tags.bin")
    if not base.is_file() or not tags.is_file():
        raise SystemExit("missing sanity_sift10k base.bin/tags.bin")
    with base.open("rb") as f:
        npts, dim = struct.unpack("<II", f.read(8))
    if npts < 1000000 or dim != 128:
        raise SystemExit(f"unexpected dataset shape {(npts, dim)}")
    with tags.open("rb") as f:
        tn, td = struct.unpack("<II", f.read(8))
        active = list(struct.unpack(f"<{tn}I", f.read(4 * tn)))
    if td != 1 or len(active) < a.count or len(set(active)) != len(active):
        raise SystemExit("invalid active tag artifact")
    active_set=set(active)
    deletes=sorted(active)[:a.count]
    inserts=[]
    for value in range(npts):
        if value not in active_set:
            inserts.append(value)
            if len(inserts)==a.count: break
    if len(inserts)!=a.count: raise SystemExit('not enough inactive source rows')
    a.output.mkdir(parents=True, exist_ok=False)
    trace = a.output / "trace.bin"
    with trace.open("xb") as f:
        f.write(struct.pack("<i", a.count))
        f.write(struct.pack(f"<{a.count}I", *deletes))
        f.write(struct.pack(f"<{a.count}I", *inserts))
    expected = a.output / "expected_active.tags.bin"
    expected_values = sorted((active_set-set(deletes))|set(inserts))
    with expected.open('xb') as f:
        f.write(struct.pack('<II',len(expected_values),1))
        f.write(struct.pack(f'<{len(expected_values)}I',*expected_values))
    manifest = {
        "schema": "zns-ann-z0a-short-workload-v1",
        "status": "pass",
        "workload": "sanity-sift10k-fresh-replace-2k",
        "dataset_shape": [npts, dim],
        "replacement_count": a.count,
        "delete_ids": [deletes[0], deletes[-1]],
        "insert_ids": [inserts[0], inserts[-1]],
        "active_count_unchanged": True,
        "trace_bytes": trace.stat().st_size,
        "trace_sha256": sha256(trace),
        "expected_active_sha256": sha256(expected),
        "dataset_sha256": sha256(base),
    }
    (a.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
