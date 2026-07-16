#!/usr/bin/env python3
"""Generate one deterministic 1.6M replacement trace and nested checkpoints."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

import numpy as np

SEED = 20260713
ACTIVE = 8_000_000
CORPUS = 10_000_000
MASTER = 1_600_000
CHECKPOINTS = {5: 400_000, 10: 800_000, 20: 1_600_000}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def durable_tree(root: Path) -> None:
    """Flush every regular output and directory entry before a stage exits."""
    for path in sorted(item for item in root.rglob("*") if item.is_file() and not item.is_symlink()):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    directories = sorted([root] + [item for item in root.rglob("*") if item.is_dir()],
                         key=lambda item: len(item.parts), reverse=True)
    for directory in directories:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def header(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        raw = stream.read(8)
    if len(raw) != 8:
        raise ValueError(f"short binary header: {path}")
    return struct.unpack("<II", raw)


def read_tags(path: Path) -> np.ndarray:
    n, d = header(path)
    if d != 1 or path.stat().st_size != 8 + 4 * n:
        raise ValueError(f"invalid tag binary: {path}")
    return np.asarray(np.memmap(path, dtype="<u4", mode="r", offset=8, shape=(n,)))


def read_trace(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with path.open("rb") as stream:
        raw = stream.read(4)
    if len(raw) != 4:
        raise ValueError(f"short trace: {path}")
    count = struct.unpack("<I", raw)[0]
    if path.stat().st_size != 4 + count * 8:
        raise ValueError(f"invalid trace layout: {path}")
    deletes = np.memmap(path, dtype="<u4", mode="r", offset=4, shape=(count,))
    inserts = np.memmap(path, dtype="<u4", mode="r", offset=4 + count * 4, shape=(count,))
    return np.asarray(deletes), np.asarray(inserts)


def atomic_trace(path: Path, deletes: np.ndarray, inserts: np.ndarray) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(struct.pack("<I", deletes.size))
            deletes.astype("<u4", copy=False).tofile(stream)
            inserts.astype("<u4", copy=False).tofile(stream)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_tags(path: Path, values: np.ndarray) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(struct.pack("<II", values.size, 1))
            values.astype("<u4", copy=False).tofile(stream)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_tsv(path: Path, deletes: np.ndarray, inserts: np.ndarray) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w") as stream:
            stream.write("op_seq\tdelete_tag\tinsert_tag\tinsert_source_row\n")
            for start in range(0, deletes.size, 100_000):
                stop = min(start + 100_000, deletes.size)
                stream.write("".join(f"{i}\t{int(deletes[i])}\t{int(inserts[i])}\t{int(inserts[i])}\n"
                                     for i in range(start, stop)))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--cp01", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dataset, cp01, output = args.dataset.resolve(), args.cp01.resolve(), args.output.resolve()
    if output.exists():
        raise SystemExit("trajectory output reuse refused")
    cp00 = read_tags(dataset / "active_cp00.tags.bin")
    if cp00.size != ACTIVE or not np.array_equal(cp00, np.arange(ACTIVE, dtype="<u4")):
        raise SystemExit("checkpoint-0 active tags are not the frozen original domain")
    old_deletes, old_inserts = read_trace(cp01 / "replace_cp01_80k.bin")
    if old_deletes.size != 80_000:
        raise SystemExit("historical CP01 trace is not 80K")
    if (np.unique(old_deletes).size != old_deletes.size or np.unique(old_inserts).size != old_inserts.size
            or np.any(old_deletes >= ACTIVE) or np.any(old_inserts < ACTIVE) or np.any(old_inserts >= CORPUS)):
        raise SystemExit("historical CP01 domains/uniqueness invalid")
    with (cp01 / "replace_cp01_80k.tsv").open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    tsv_semantic_exact = (len(rows) == 80_000
                          and all(int(row["op_seq"]) == i and int(row["delete_tag"]) == int(old_deletes[i])
                                  and int(row["insert_tag"]) == int(old_inserts[i])
                                  and int(row["insert_source_row"]) == int(old_inserts[i]) for i, row in enumerate(rows)))
    if not tsv_semantic_exact:
        raise SystemExit("historical CP01 TSV differs from frozen binary trace semantics")

    delete_unused = np.setdiff1d(np.arange(ACTIVE, dtype="<u4"), old_deletes, assume_unique=True)
    insert_unused = np.setdiff1d(np.arange(ACTIVE, CORPUS, dtype="<u4"), old_inserts, assume_unique=True)
    extension = MASTER - old_deletes.size
    delete_rng = np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence([SEED, 0x44454C])))
    insert_rng = np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence([SEED, 0x494E53])))
    deletes = np.concatenate((old_deletes, delete_rng.permutation(delete_unused)[:extension])).astype("<u4")
    inserts = np.concatenate((old_inserts, insert_rng.permutation(insert_unused)[:extension])).astype("<u4")
    if (np.unique(deletes).size != MASTER or np.unique(inserts).size != MASTER
            or np.intersect1d(deletes, inserts).size or np.any(deletes >= ACTIVE)
            or np.any(inserts < ACTIVE) or np.any(inserts >= CORPUS)):
        raise SystemExit("master trace domain/uniqueness validation failed")

    output.mkdir(parents=True, exist_ok=False)
    master_bin = output / "master_replacements_1600k.bin"
    master_tsv = output / "master_replacements_1600k.tsv"
    atomic_trace(master_bin, deletes, inserts)
    atomic_tsv(master_tsv, deletes, inserts)
    prefix = {
        "schema": "dynamic-vamana-w1-trajectory-cp01-prefix-v1", "status": "pass",
        "record_layout": "columnar uint32 delete[count], uint32 insert[count]", "record_size_bytes": 8,
        "prefix_record_count": 80_000, "historical_cp01_realpath": str((cp01 / "replace_cp01_80k.bin").resolve()),
        "historical_cp01_sha256": sha(cp01 / "replace_cp01_80k.bin"), "historical_cp01_tsv_sha256": sha(cp01 / "replace_cp01_80k.tsv"),
        "master_trace_sha256": sha(master_bin), "delete_payload_byte_identical": old_deletes.tobytes() == deletes[:80_000].tobytes(),
        "insert_payload_byte_identical": old_inserts.tobytes() == inserts[:80_000].tobytes(),
        "ordered_record_payload_exact": bool(np.array_equal(old_deletes, deletes[:80_000]) and np.array_equal(old_inserts, inserts[:80_000])),
        "historical_tsv_semantic_exact": tsv_semantic_exact,
    }
    if not prefix["ordered_record_payload_exact"]:
        raise SystemExit("master trace does not preserve CP01 record prefix")
    (output / "cp01_prefix_validation.json").write_text(json.dumps(prefix, indent=2) + "\n")

    manifest = {
        "schema": "dynamic-vamana-w1-trajectory-master-v1", "status": "pass", "seed": SEED,
        "prng": "numpy.random.PCG64DXSM", "numpy_version": np.__version__, "python_version": sys.version,
        "domain_separation": {"delete_seed_sequence": [SEED, 0x44454C], "insert_seed_sequence": [SEED, 0x494E53]},
        "generator_realpath": str(Path(__file__).resolve()), "generator_sha256": sha(Path(__file__).resolve()),
        "historical_cp01": {"binary_sha256": sha(cp01 / "replace_cp01_80k.bin"), "tsv_sha256": sha(cp01 / "replace_cp01_80k.tsv"),
                            "manifest_sha256": sha(cp01 / "replace_cp01_manifest.json")},
        "master_count": MASTER, "master_binary_sha256": sha(master_bin), "master_tsv_sha256": sha(master_tsv),
        "delete_domain": [0, ACTIVE], "insert_domain": [ACTIVE, CORPUS], "delete_unique": True, "insert_unique": True,
        "cp01_prefix_validation_sha256": sha(output / "cp01_prefix_validation.json"),
        "checkpoint_prefix_counts": {"cp05": 400_000, "cp10": 800_000, "cp20": 1_600_000},
    }
    (output / "master_trace_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    durable_tree(output)


if __name__ == "__main__":
    main()
