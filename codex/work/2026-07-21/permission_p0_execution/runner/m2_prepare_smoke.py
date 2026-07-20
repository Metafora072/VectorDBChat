#!/usr/bin/env python3
"""Generate an all-authorized 1M filtered-path smoke workload.

All vectors and queries receive role 0. Therefore the existing ordinary exact
ground truth is also the authorized exact ground truth. This tests file formats
and execution plumbing only; it is not an ACL-fragmentation experiment.
"""

from __future__ import annotations

import argparse
import array
import json
import struct
from pathlib import Path


def read_bin_shape(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        raw = handle.read(8)
    if len(raw) != 8:
        raise ValueError(f"short bin header: {path}")
    return struct.unpack("<II", raw)


def write_single_label_spmat(path: Path, nrows: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(struct.pack("<qqq", nrows, 1, nrows))
        indptr = array.array("q", range(nrows + 1))
        indices = array.array("i", [0]) * nrows
        values = array.array("f", [1.0]) * nrows
        if not all(x.itemsize == y for x, y in ((indptr, 8), (indices, 4), (values, 4))):
            raise RuntimeError("unexpected native array item size")
        handle.write(indptr.tobytes())
        handle.write(indices.tobytes())
        handle.write(values.tobytes())


def copy_bin_prefix(source: Path, destination: Path, rows: int) -> tuple[int, int]:
    nrows, dim = read_bin_shape(source)
    if rows > nrows:
        raise ValueError(f"requested {rows} rows from {source} with only {nrows}")
    item_bytes = 4
    with source.open("rb") as src, destination.open("wb") as dst:
        src.read(8)
        dst.write(struct.pack("<II", rows, dim))
        payload = src.read(rows * dim * item_bytes)
        if len(payload) != rows * dim * item_bytes:
            raise ValueError(f"short bin payload: {source}")
        dst.write(payload)
    return rows, dim


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--query", required=True, type=Path)
    parser.add_argument("--index-prefix", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--smoke-queries", type=int, default=16)
    args = parser.parse_args()

    npoints, dim = read_bin_shape(args.data)
    nqueries, qdim = read_bin_shape(args.query)
    if (npoints, dim) != (1_000_000, 128):
        raise ValueError(f"expected SIFT1M float32 shape, got {(npoints, dim)}")
    if qdim != dim:
        raise ValueError(f"query dim mismatch: {qdim} != {dim}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    base_spmat = args.output_dir / "base_all_role0.spmat"
    query_subset = args.output_dir / "query_16.bin"
    gt_subset = args.output_dir / "groundtruth_16.bin"
    query_spmat = args.output_dir / "query_all_role0.spmat"
    config = args.output_dir / "filter_all_role0.json"
    write_single_label_spmat(base_spmat, npoints)
    smoke_queries = min(args.smoke_queries, nqueries)
    copy_bin_prefix(args.query, query_subset, smoke_queries)
    gt_source = args.query.parent / "groundtruth.bin"
    if not gt_source.exists():
        raise ValueError(f"ground truth not found next to query: {gt_source}")
    copy_bin_prefix(gt_source, gt_subset, smoke_queries)
    write_single_label_spmat(query_spmat, smoke_queries)

    payload = {
        "attr_indexes": [
            {
                "name": "roles",
                "key": 0,
                "type": "label",
                "file": str(args.index_prefix) + ".label.0",
            }
        ],
        "filter": "array_contains_all(roles, $$query_roles)",
        "bindings": {"query_roles": str(query_spmat)},
    }
    config.write_text(json.dumps(payload, indent=2) + "\n")
    (args.output_dir / "workload_manifest.json").write_text(json.dumps({
        "purpose": "all-authorized artifact-path smoke only",
        "npoints": npoints,
        "dimension": dim,
        "source_nqueries": nqueries,
        "nqueries": smoke_queries,
        "role_count": 1,
        "global_authorized_selectivity": 1.0,
        "base_spmat": str(base_spmat),
        "query_spmat": str(query_spmat),
        "query_subset": str(query_subset),
        "groundtruth_subset": str(gt_subset),
        "config": str(config),
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
