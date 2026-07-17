#!/usr/bin/env python3
"""Derive one immutable M0 nested-prefix trace, exact active set, and probes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_trace(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with path.open("rb") as stream:
        count = struct.unpack("<I", stream.read(4))[0]
    if path.stat().st_size != 4 + 8 * count:
        raise ValueError("source trace layout mismatch")
    deletes = np.asarray(np.memmap(path, dtype="<u4", mode="r", offset=4, shape=(count,)))
    inserts = np.asarray(np.memmap(path, dtype="<u4", mode="r", offset=4 + 4 * count, shape=(count,)))
    return deletes, inserts


def read_tags(path: Path) -> np.ndarray:
    with path.open("rb") as stream:
        count, dim = struct.unpack("<II", stream.read(8))
    if dim != 1 or path.stat().st_size != 8 + 4 * count:
        raise ValueError("active-tag layout mismatch")
    return np.asarray(np.memmap(path, dtype="<u4", mode="r", offset=8, shape=(count,)))


def vectors(path: Path) -> np.memmap:
    with path.open("rb") as stream:
        count, dim = struct.unpack("<II", stream.read(8))
    if dim != 128 or path.stat().st_size != 8 + 4 * count * dim:
        raise ValueError("full corpus layout mismatch")
    return np.memmap(path, dtype="<f4", mode="r", offset=8, shape=(count, dim))


def write_atomic(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--source-trace", type=Path, required=True)
    parser.add_argument("--before-active", type=Path, required=True)
    parser.add_argument("--full-corpus", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.size not in (50_000, 100_000, 200_000, 400_000):
        raise SystemExit("M0 size is outside the authorized matrix")
    if args.output_dir.exists() or args.output_dir.is_symlink():
        raise SystemExit("refusing to reuse an M0 input directory")
    args.output_dir.mkdir(parents=True, mode=0o700)

    source_deletes, source_inserts = read_trace(args.source_trace.resolve(strict=True))
    if source_deletes.size != 800_000:
        raise SystemExit("source is not the frozen CP10->CP20 800K delta")
    deletes = source_deletes[: args.size].astype("<u4", copy=True)
    inserts = source_inserts[: args.size].astype("<u4", copy=True)
    before = read_tags(args.before_active.resolve(strict=True))
    if before.size != 8_000_000 or np.unique(before).size != before.size:
        raise SystemExit("CP10 active set is not exact 8M unique tags")
    before_set = set(int(x) for x in before)
    if len(set(map(int, deletes))) != args.size or not set(map(int, deletes)).issubset(before_set):
        raise SystemExit("prefix deletes are not unique active CP10 tags")
    if len(set(map(int, inserts))) != args.size or set(map(int, inserts)) & before_set:
        raise SystemExit("prefix inserts are not unique fresh tags")

    trace = args.output_dir / "trace.bin"
    write_atomic(trace, struct.pack("<I", args.size) + deletes.tobytes() + inserts.tobytes())
    expected_values = np.array(sorted((before_set - set(map(int, deletes))) | set(map(int, inserts))), dtype="<u4")
    if expected_values.size != 8_000_000:
        raise SystemExit("derived active-set cardinality drift")
    expected = args.output_dir / "expected_active.tags.bin"
    write_atomic(expected, struct.pack("<II", expected_values.size, 1) + expected_values.tobytes())

    positions = np.floor(np.linspace(0, args.size - 1, 9)).astype(np.int64)
    full = vectors(args.full_corpus.resolve(strict=True))
    probe_rows: list[np.ndarray] = []
    probe_spec: list[dict[str, int | str]] = []
    for position in positions:
        delete_tag = int(deletes[position])
        insert_tag = int(inserts[position])
        ordinal = len(probe_rows)
        probe_rows.append(np.asarray(full[insert_tag], dtype="<f4"))
        probe_spec.append({"ordinal": ordinal, "op_seq": int(position), "master_op_seq": 800_000 + int(position),
                           "kind": "insert", "query_tag": insert_tag, "expected_tag": insert_tag})
        ordinal = len(probe_rows)
        probe_rows.append(np.asarray(full[delete_tag], dtype="<f4"))
        probe_spec.append({"ordinal": ordinal, "op_seq": int(position), "master_op_seq": 800_000 + int(position),
                           "kind": "delete", "query_tag": delete_tag, "forbidden_tag": delete_tag})
    probe_matrix = np.asarray(probe_rows, dtype="<f4")
    probes = args.output_dir / "probes.bin"
    write_atomic(probes, struct.pack("<II", probe_matrix.shape[0], probe_matrix.shape[1]) + probe_matrix.tobytes())
    spec = args.output_dir / "probes.json"
    spec_payload = {"schema": "dynamic-vamana-write-attribution-m0-probes-v1",
                    "positions": [int(x) for x in positions], "probe_count": len(probe_spec), "probes": probe_spec}
    write_atomic(spec, (json.dumps(spec_payload, indent=2, sort_keys=True) + "\n").encode())

    manifest = {
        "schema": "dynamic-vamana-write-attribution-m0-input-v1", "status": "pass",
        "size": args.size, "master_record_range": [800_000, 800_000 + args.size],
        "primitive_mutations": 2 * args.size, "active_count": int(expected_values.size),
        "trace": {"path": trace.name, "sha256": sha256(trace), "size_bytes": trace.stat().st_size},
        "expected_active": {"path": expected.name, "sha256": sha256(expected), "size_bytes": expected.stat().st_size},
        "probes": {"binary": probes.name, "binary_sha256": sha256(probes), "spec": spec.name,
                   "spec_sha256": sha256(spec), "shape": list(probe_matrix.shape)},
        "sources": {str(args.source_trace.resolve()): sha256(args.source_trace),
                    str(args.before_active.resolve()): sha256(args.before_active),
                    str(args.full_corpus.resolve()): sha256(args.full_corpus)},
        "assertions": {"nested_prefix": True, "delete_unique_active": True, "insert_unique_fresh": True,
                       "active_set_exact": True, "insert_source_row_equals_tag": True},
    }
    manifest_path = args.output_dir / "manifest.json"
    write_atomic(manifest_path, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    for path in args.output_dir.iterdir():
        path.chmod(0o444)
    args.output_dir.chmod(0o555)
    print(manifest_path)


if __name__ == "__main__":
    main()
