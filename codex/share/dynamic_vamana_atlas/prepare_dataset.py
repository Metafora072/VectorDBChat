#!/usr/bin/env python3
"""Prepare deterministic 80/20 replace-new Atlas datasets and traces.

Input and output vector files use DiskANN/BigANN .bin/.fbin layout:
uint32 npts, uint32 dim, followed by row-major float32 vectors. Tags use the
same header with dim=1 followed by uint32 logical vector IDs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import struct
from pathlib import Path

import numpy as np


CHECKPOINTS = (0, 5, 10, 20)


def read_header(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        raw = f.read(8)
    if len(raw) != 8:
        raise ValueError(f"short header: {path}")
    return struct.unpack("<II", raw)


def validate_float_bin(path: Path) -> tuple[int, int]:
    npts, dim = read_header(path)
    expected = 8 + npts * dim * 4
    actual = path.stat().st_size
    if actual != expected:
        raise ValueError(f"size mismatch for {path}: expected={expected}, actual={actual}")
    return npts, dim


def write_rows(source: np.memmap, ids: np.ndarray, output: Path, chunk_rows: int = 8192) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    with tmp.open("wb") as f:
        f.write(struct.pack("<II", int(ids.size), int(source.shape[1])))
        for start in range(0, ids.size, chunk_rows):
            rows = np.asarray(source[ids[start : start + chunk_rows]], dtype="<f4", order="C")
            rows.tofile(f)
    os.replace(tmp, output)


def write_tags(ids: np.ndarray, output: Path) -> None:
    tmp = output.with_suffix(output.suffix + ".tmp")
    with tmp.open("wb") as f:
        f.write(struct.pack("<II", int(ids.size), 1))
        np.asarray(ids, dtype="<u4").tofile(f)
    os.replace(tmp, output)


def link_or_copy(source: Path, output: Path) -> str:
    if output.exists():
        return "existing"
    try:
        os.link(source, output)
        return "hardlink"
    except OSError:
        shutil.copyfile(source, output)
        return "copy"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--query", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--total", type=int, default=1_000_000)
    p.add_argument("--active", type=int, default=800_000)
    p.add_argument("--seed", type=int, default=20260713)
    args = p.parse_args()

    source_n, dim = validate_float_bin(args.source)
    query_n, query_dim = validate_float_bin(args.query)
    if source_n < args.total:
        raise ValueError(f"source has {source_n} points, need {args.total}")
    if query_dim != dim:
        raise ValueError(f"query dim {query_dim} != base dim {dim}")
    if not 0 < args.active < args.total:
        raise ValueError("active must be in (0,total)")
    if args.total - args.active < int(args.active * max(CHECKPOINTS) / 100):
        raise ValueError("insert pool is too small for the largest checkpoint")

    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    source = np.memmap(args.source, dtype="<f4", mode="r", offset=8, shape=(source_n, dim))

    all_ids = np.arange(args.total, dtype=np.uint32)
    initial_ids = all_ids[: args.active]
    pool_ids = all_ids[args.active :]

    full_path = out / "full_1m.bin"
    if source_n == args.total:
        full_method = link_or_copy(args.source, full_path)
    else:
        write_rows(source, all_ids, full_path)
        full_method = "materialized-prefix"
    query_method = link_or_copy(args.query, out / "query.bin")

    rng = np.random.default_rng(args.seed)
    delete_order = rng.permutation(initial_ids)
    insert_order = rng.permutation(pool_ids)
    max_replacements = int(args.active * max(CHECKPOINTS) / 100)

    trace_path = out / "replace_new_trace.csv"
    with trace_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["op_seq", "delete_tag", "insert_tag", "insert_source_row", "cumulative_replacement_pct"])
        for i in range(max_replacements):
            pct = 100.0 * (i + 1) / args.active
            w.writerow([i, int(delete_order[i]), int(insert_order[i]), int(insert_order[i]), f"{pct:.8f}"])

    with (out / "same_vector_control.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["op_seq", "delete_tag", "reinsert_tag", "source_row"])
        for i, tag in enumerate(delete_order[:100]):
            w.writerow([i, int(tag), int(tag), int(tag)])

    with (out / "smoke_replace_new_trace.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["op_seq", "delete_tag", "insert_tag", "insert_source_row"])
        for i in range(100):
            w.writerow([i, int(delete_order[i]), int(insert_order[i]), int(insert_order[i])])

    checkpoint_rows = []
    for pct in CHECKPOINTS:
        nreplace = int(args.active * pct / 100)
        active_ids = np.concatenate((initial_ids[nreplace:], insert_order[:nreplace])).astype(np.uint32)
        active_ids.sort()
        cp = f"cp{pct:02d}"
        data_path = out / f"active_{cp}.bin"
        tag_path = out / f"active_{cp}.tags.bin"
        write_rows(source, active_ids, data_path)
        write_tags(active_ids, tag_path)
        np.asarray(active_ids, dtype="<u4").tofile(out / f"active_{cp}.ids.u32")
        checkpoint_rows.append(
            {
                "checkpoint_pct": pct,
                "replacement_count": nreplace,
                "active_count": int(active_ids.size),
                "min_tag": int(active_ids.min()),
                "max_tag": int(active_ids.max()),
                "data": str(data_path),
                "tags": str(tag_path),
            }
        )

    manifest = {
        "schema": "dynamic-vamana-atlas-dataset-v1",
        "name": args.name,
        "source": str(args.source),
        "query_source": str(args.query),
        "source_npts": source_n,
        "total_npts": args.total,
        "active_npts": args.active,
        "insert_pool_npts": args.total - args.active,
        "query_npts": query_n,
        "dimension": dim,
        "dtype": "float32",
        "metric": "l2",
        "seed": args.seed,
        "full_materialization": full_method,
        "query_materialization": query_method,
        "checkpoint_denominator": "cumulative replaced objects / initial active corpus size",
        "checkpoints": checkpoint_rows,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
