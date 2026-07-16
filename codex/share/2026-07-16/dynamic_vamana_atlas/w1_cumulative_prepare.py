#!/usr/bin/env python3
"""Prepare immutable inputs for the W1 CP05 cumulative state machine.

This program only derives traces, tag sets, and visibility probes.  It never
opens an index, invokes an experiment worker, or starts a service/scope.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import stat
import struct
import sys
from pathlib import Path
from typing import Iterable

import numpy as np


FORMAL_ACTIVE = 8_000_000
FORMAL_CORPUS = 10_000_000
FORMAL_CP01 = 80_000
FORMAL_CP05 = 400_000
REPLAY_ACTIVE = 800_000
REPLAY_CORPUS = 1_000_000
REPLAY_CP1 = 16
REPLAY_CP2 = 80


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def file_identity(path: Path) -> dict[str, object]:
    path = path.resolve(strict=True)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or path.is_symlink():
        raise ValueError(f"source is not a non-symlink regular file: {path}")
    digest = sha256(path)
    info = path.stat()
    stable_fields = ("st_dev", "st_ino", "st_size", "st_uid", "st_gid", "st_mode", "st_mtime_ns")
    if any(getattr(before, field) != getattr(info, field) for field in stable_fields):
        raise ValueError(f"source changed while hashing: {path}")
    return {
        "realpath": str(path),
        "size_bytes": info.st_size,
        "sha256": digest,
        "device": info.st_dev,
        "inode": info.st_ino,
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": stat.S_IMODE(info.st_mode),
        "mtime_ns": info.st_mtime_ns,
    }


def snapshot_sources(paths: Iterable[Path]) -> dict[str, dict[str, object]]:
    identities: dict[str, dict[str, object]] = {}
    for path in paths:
        identity = file_identity(path)
        realpath = str(identity["realpath"])
        if realpath in identities:
            raise ValueError(f"duplicate source realpath: {realpath}")
        identities[realpath] = identity
    return identities


def atomic_bytes(path: Path, writer) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    if temporary.exists():
        raise FileExistsError(f"stale temporary output: {temporary}")
    try:
        with temporary.open("wb") as stream:
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_text(path: Path, text: str) -> None:
    data = text.encode("utf-8")
    atomic_bytes(path, lambda stream: stream.write(data))


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def read_trace(path: Path) -> tuple[np.ndarray, np.ndarray]:
    path = path.resolve(strict=True)
    with path.open("rb") as stream:
        raw = stream.read(4)
    if len(raw) != 4:
        raise ValueError(f"short trace header: {path}")
    count = struct.unpack("<I", raw)[0]
    if path.stat().st_size != 4 + 8 * count:
        raise ValueError(f"invalid columnar trace size: {path}")
    deletes = np.memmap(path, dtype="<u4", mode="r", offset=4, shape=(count,))
    inserts = np.memmap(path, dtype="<u4", mode="r", offset=4 + 4 * count, shape=(count,))
    return np.asarray(deletes), np.asarray(inserts)


def read_tags(path: Path) -> np.ndarray:
    path = path.resolve(strict=True)
    with path.open("rb") as stream:
        raw = stream.read(8)
    if len(raw) != 8:
        raise ValueError(f"short tag header: {path}")
    count, dimensions = struct.unpack("<II", raw)
    if dimensions != 1 or path.stat().st_size != 8 + 4 * count:
        raise ValueError(f"invalid tag binary: {path}")
    return np.asarray(np.memmap(path, dtype="<u4", mode="r", offset=8, shape=(count,)))


def vector_matrix(path: Path) -> np.memmap:
    path = path.resolve(strict=True)
    with path.open("rb") as stream:
        raw = stream.read(8)
    if len(raw) != 8:
        raise ValueError(f"short vector header: {path}")
    count, dimensions = struct.unpack("<II", raw)
    if dimensions == 0 or path.stat().st_size != 8 + 4 * count * dimensions:
        raise ValueError(f"invalid float vector binary: {path}")
    return np.memmap(path, dtype="<f4", mode="r", offset=8, shape=(count, dimensions))


def write_trace(path: Path, deletes: np.ndarray, inserts: np.ndarray) -> None:
    if deletes.dtype != np.dtype("<u4") or inserts.dtype != np.dtype("<u4"):
        deletes = deletes.astype("<u4", copy=False)
        inserts = inserts.astype("<u4", copy=False)
    if deletes.shape != inserts.shape or deletes.ndim != 1:
        raise ValueError("trace arrays must be equal-length vectors")

    def writer(stream) -> None:
        stream.write(struct.pack("<I", deletes.size))
        deletes.tofile(stream)
        inserts.tofile(stream)

    atomic_bytes(path, writer)


def write_tags(path: Path, values: np.ndarray) -> None:
    values = values.astype("<u4", copy=False)

    def writer(stream) -> None:
        stream.write(struct.pack("<II", values.size, 1))
        values.tofile(stream)

    atomic_bytes(path, writer)


def write_vectors(path: Path, vectors: np.ndarray) -> None:
    vectors = np.asarray(vectors, dtype="<f4")
    if vectors.ndim != 2:
        raise ValueError("probe vectors must be a matrix")

    def writer(stream) -> None:
        stream.write(struct.pack("<II", vectors.shape[0], vectors.shape[1]))
        vectors.tofile(stream)

    atomic_bytes(path, writer)


def write_groundtruth(path: Path, ids: np.ndarray, distances: np.ndarray) -> None:
    ids = np.asarray(ids, dtype="<u4")
    distances = np.asarray(distances, dtype="<f4")
    if ids.ndim != 2 or ids.shape != distances.shape:
        raise ValueError("ground-truth IDs/distances must have the same matrix shape")

    def writer(stream) -> None:
        stream.write(struct.pack("<II", ids.shape[0], ids.shape[1]))
        ids.tofile(stream)
        distances.tofile(stream)

    atomic_bytes(path, writer)


def exact_groundtruth(full: np.ndarray, active: np.ndarray, queries: np.ndarray, k: int = 100) -> tuple[np.ndarray, np.ndarray]:
    """Compute canonical squared-L2 GT, tie-breaking equal distances by tag."""
    if active.ndim != 1 or active.size < k or not np.all(active[:-1] < active[1:]):
        raise ValueError("active tags for exact GT must be sorted, unique, and contain K rows")
    ids = np.empty((queries.shape[0], k), dtype="<u4")
    result_distances = np.empty((queries.shape[0], k), dtype="<f4")
    distances = np.empty(active.size, dtype="<f4")
    for query_index, query in enumerate(np.asarray(queries, dtype="<f4")):
        for start in range(0, active.size, 16_384):
            stop = min(start + 16_384, active.size)
            vectors = np.asarray(full[active[start:stop]], dtype="<f4")
            difference = vectors - query
            distances[start:stop] = np.einsum("ij,ij->i", difference, difference, optimize=True)
        if not np.all(np.isfinite(distances)):
            raise ValueError(f"non-finite replay GT distances for query {query_index}")
        threshold = np.partition(distances, k - 1)[k - 1]
        candidates = np.flatnonzero(distances <= threshold)
        if candidates.size < k:
            raise ValueError("GT partition produced fewer than K candidates")
        candidate_tags = active[candidates]
        order = np.lexsort((candidate_tags, distances[candidates]))[:k]
        selected = candidates[order]
        ids[query_index] = active[selected]
        result_distances[query_index] = distances[selected]
    return ids, result_distances


def validate_groundtruth(path: Path, full: np.ndarray, active: np.ndarray, queries: np.ndarray) -> dict[str, object]:
    with path.open("rb") as stream:
        raw = stream.read(8)
    if len(raw) != 8:
        raise ValueError(f"short GT header: {path}")
    query_count, k = struct.unpack("<II", raw)
    expected_size = 8 + query_count * k * 8
    if query_count != queries.shape[0] or k != 100 or path.stat().st_size != expected_size:
        raise ValueError(f"invalid replay GT shape/size: {path}")
    ids = np.asarray(np.memmap(path, dtype="<u4", mode="r", offset=8, shape=(query_count, k)))
    distances = np.asarray(np.memmap(path, dtype="<f4", mode="r", offset=8 + query_count * k * 4,
                                     shape=(query_count, k)))
    if not np.all(np.isfinite(distances)) or np.any(distances < 0):
        raise ValueError(f"invalid replay GT distances: {path}")
    locations = np.searchsorted(active, ids)
    if np.any(locations >= active.size) or not np.array_equal(active[locations], ids):
        raise ValueError(f"replay GT contains inactive IDs: {path}")
    for query_index in range(query_count):
        if np.unique(ids[query_index]).size != k:
            raise ValueError(f"replay GT row contains duplicate IDs: {path}:{query_index}")
        canonical = np.lexsort((ids[query_index], distances[query_index]))
        if not np.array_equal(canonical, np.arange(k)):
            raise ValueError(f"replay GT row is not canonical: {path}:{query_index}")
        vectors = np.asarray(full[ids[query_index]], dtype="<f4")
        difference = vectors - queries[query_index]
        recomputed = np.einsum("ij,ij->i", difference, difference, optimize=True)
        if not np.allclose(recomputed, distances[query_index], rtol=1e-6, atol=1e-5):
            raise ValueError(f"replay GT distance recomputation failed: {path}:{query_index}")
    return {"path": path.name, "sha256": sha256(path), "shape": [query_count, k],
            "size_bytes": path.stat().st_size, "active_only": True, "row_unique": True,
            "finite_monotonic_canonical": True, "distance_recomputed": True}


def write_tsv(path: Path, deletes: np.ndarray, inserts: np.ndarray, master_offset: int) -> None:
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    if temporary.exists():
        raise FileExistsError(f"stale temporary output: {temporary}")
    try:
        with temporary.open("w", newline="") as stream:
            stream.write("op_seq\tdelete_tag\tinsert_tag\tinsert_source_row\n")
            for start in range(0, deletes.size, 100_000):
                stop = min(start + 100_000, deletes.size)
                stream.write("".join(
                    f"{master_offset + i}\t{int(deletes[i])}\t{int(inserts[i])}\t{int(inserts[i])}\n"
                    for i in range(start, stop)
                ))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_tsv(path: Path, deletes: np.ndarray, inserts: np.ndarray, master_offset: int = 0) -> int:
    rows = 0
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        expected_fields = ["op_seq", "delete_tag", "insert_tag", "insert_source_row"]
        if reader.fieldnames != expected_fields:
            raise ValueError(f"unexpected TSV fields in {path}: {reader.fieldnames}")
        for row in reader:
            if rows >= deletes.size:
                raise ValueError(f"too many TSV records: {path}")
            if (int(row["op_seq"]) != master_offset + rows
                    or int(row["delete_tag"]) != int(deletes[rows])
                    or int(row["insert_tag"]) != int(inserts[rows])
                    or int(row["insert_source_row"]) != int(inserts[rows])):
                raise ValueError(f"TSV semantic mismatch at record {rows}: {path}")
            rows += 1
    if rows != deletes.size:
        raise ValueError(f"TSV record count mismatch: {path}: {rows} != {deletes.size}")
    return rows


def validate_master_tsv(path: Path, deletes: np.ndarray, inserts: np.ndarray) -> int:
    """Validate the entire frozen master TSV without retaining 1.6M rows."""
    return validate_tsv(path, deletes, inserts)


def floor_positions(count: int) -> list[int]:
    if count < 9:
        raise ValueError("at least nine records are required for visibility probes")
    positions = [j * (count - 1) // 8 for j in range(9)]
    if len(set(positions)) != 9:
        raise ValueError("floor probe positions are not unique")
    return positions


def micro_round_positions(count: int) -> list[int]:
    positions = sorted({0, count - 1, *(round(j * (count - 1) / 8) for j in range(1, 8))})
    if len(positions) != 9:
        raise ValueError("micro checkpoint-global positions are not unique")
    return positions


def probe_document(
    *,
    deletes: np.ndarray,
    inserts: np.ndarray,
    positions: list[int],
    selection: str,
    master_offset: int,
    schema: str,
) -> tuple[dict[str, object], np.ndarray]:
    probes: list[dict[str, object]] = []
    query_tags: list[int] = []
    for position in positions:
        insert = int(inserts[position])
        delete = int(deletes[position])
        probes.append({
            "ordinal": len(probes), "op_seq": position, "master_op_seq": master_offset + position,
            "kind": "insert", "query_tag": insert, "expected_tag": insert,
        })
        query_tags.append(insert)
        probes.append({
            "ordinal": len(probes), "op_seq": position, "master_op_seq": master_offset + position,
            "kind": "delete", "query_tag": delete, "forbidden_tag": delete,
        })
        query_tags.append(delete)
    document = {
        "schema": schema,
        "selection": selection,
        "replacement_count": int(deletes.size),
        "master_record_offset": master_offset,
        "positions": positions,
        "probe_count": len(probes),
        "mapping_rule": "insert_source_row == insert_tag",
        "probes": probes,
    }
    return document, np.asarray(query_tags, dtype="<u4")


def expected_active(cp00: np.ndarray, deletes: np.ndarray, inserts: np.ndarray) -> np.ndarray:
    if np.unique(cp00).size != cp00.size:
        raise ValueError("CP00 active tags are not unique")
    if np.unique(deletes).size != deletes.size or np.unique(inserts).size != inserts.size:
        raise ValueError("trace delete/insert tags are not unique")
    if not np.all(np.isin(deletes, cp00, assume_unique=False)):
        raise ValueError("a delete tag is not active at checkpoint 0")
    if np.any(np.isin(inserts, cp00, assume_unique=False)):
        raise ValueError("an insert tag is already active at checkpoint 0")
    active = np.sort(np.concatenate((cp00[~np.isin(cp00, deletes)], inserts))).astype("<u4")
    if active.size != cp00.size or np.unique(active).size != cp00.size:
        raise ValueError("active-set cardinality/uniqueness failed")
    return active


def create_probe_files(
    directory: Path,
    basename: str,
    document: dict[str, object],
    query_tags: np.ndarray,
    full: np.ndarray,
) -> dict[str, object]:
    if np.any(query_tags >= full.shape[0]):
        raise ValueError("probe query tag is outside the full corpus")
    json_path = directory / f"{basename}.json"
    bin_path = directory / f"{basename}.bin"
    atomic_json(json_path, document)
    write_vectors(bin_path, np.asarray(full[query_tags], dtype="<f4"))
    return {
        "json_path": json_path.name, "json_sha256": sha256(json_path),
        "binary_path": bin_path.name, "binary_sha256": sha256(bin_path),
        "query_tags": [int(value) for value in query_tags],
    }


def vector_payload(path: Path) -> tuple[int, int, bytes]:
    with path.open("rb") as stream:
        raw = stream.read(8)
        if len(raw) != 8:
            raise ValueError(f"short vector header: {path}")
        count, dimensions = struct.unpack("<II", raw)
        payload = stream.read()
    if dimensions == 0 or len(payload) != 4 * count * dimensions:
        raise ValueError(f"invalid vector payload: {path}")
    return count, dimensions, payload


def create_combined_probes(
    *, directory: Path, local_bin: Path, local_json: Path,
    global_bin: Path, global_json: Path, full: np.ndarray,
) -> dict[str, object]:
    local_spec = json.loads(local_json.read_text())
    global_spec = json.loads(global_json.read_text())
    local_probes = local_spec.get("probes")
    global_probes = global_spec.get("probes")
    if not isinstance(local_probes, list) or len(local_probes) != 18:
        raise ValueError("local probe specification is not 18 rows")
    if not isinstance(global_probes, list) or len(global_probes) != 18:
        raise ValueError("frozen checkpoint-global probe specification is not 18 rows")
    local_count, local_dim, local_payload = vector_payload(local_bin)
    global_count, global_dim, global_payload = vector_payload(global_bin)
    if (local_count, global_count) != (18, 18) or local_dim != global_dim or local_dim != full.shape[1]:
        raise ValueError("local/global probe binary shape mismatch")
    global_tags = np.asarray([int(probe["query_tag"]) for probe in global_probes], dtype="<u4")
    if np.any(global_tags >= full.shape[0]):
        raise ValueError("frozen checkpoint-global probe tag is outside the full corpus")
    expected_global_payload = np.asarray(full[global_tags], dtype="<f4").tobytes(order="C")
    if global_payload != expected_global_payload:
        raise ValueError("frozen checkpoint-global probe vectors do not match query tags")
    combined_bin = directory / "combined_visibility_probes.bin"

    def writer(stream) -> None:
        stream.write(struct.pack("<II", 36, local_dim))
        stream.write(local_payload)
        stream.write(global_payload)

    atomic_bytes(combined_bin, writer)
    combined_count, combined_dim, combined_payload = vector_payload(combined_bin)
    local_bytes = len(local_payload)
    if (combined_count, combined_dim) != (36, local_dim):
        raise ValueError("combined probe binary shape mismatch")
    if combined_payload[:local_bytes] != local_payload or combined_payload[local_bytes:] != global_payload:
        raise ValueError("combined local/global payload is not byte exact")
    combined_probes: list[dict[str, object]] = []
    for group, probes in (("local", local_probes), ("global", global_probes)):
        for group_ordinal, probe in enumerate(probes):
            item = dict(probe)
            item["source_ordinal"] = int(probe.get("ordinal", group_ordinal))
            item["group"] = group
            item["group_ordinal"] = group_ordinal
            item["ordinal"] = len(combined_probes)
            combined_probes.append(item)
    if global_bin.parent.resolve() == directory.resolve():
        global_source_references = {"source_binary": global_bin.name, "source_spec": global_json.name}
    else:
        global_source_references = {"source_binary_realpath": str(global_bin.resolve()),
                                    "source_spec_realpath": str(global_json.resolve())}
    combined_spec = {
        "schema": "dynamic-vamana-w1-cumulative-combined-probes-v1",
        "probe_count": 36,
        "binary_shape": [36, local_dim],
        "groups": [
            {"name": "local", "row_range": [0, 18], "source_binary": local_bin.name,
             "source_binary_sha256": sha256(local_bin), "source_spec": local_json.name,
             "source_spec_sha256": sha256(local_json), "payload_sha256": hashlib.sha256(local_payload).hexdigest()},
            {"name": "global", "row_range": [18, 36], **global_source_references,
             "source_binary_sha256": sha256(global_bin),
             "source_spec_sha256": sha256(global_json), "payload_sha256": hashlib.sha256(global_payload).hexdigest(),
             "positions": global_spec.get("positions"), "selection": global_spec.get("selection")},
        ],
        "assertions": {"local_payload_byte_exact": True, "global_payload_byte_exact": True,
                       "global_positions_reused_without_selection": True},
        "probes": combined_probes,
    }
    combined_json = directory / "combined_visibility_probes.json"
    atomic_json(combined_json, combined_spec)
    return {
        "binary_path": combined_bin.name, "binary_sha256": sha256(combined_bin),
        "json_path": combined_json.name, "json_sha256": sha256(combined_json),
        "shape": [36, local_dim], "group_row_offsets": {"local": [0, 18], "global": [18, 36]},
        "local_payload_sha256": hashlib.sha256(local_payload).hexdigest(),
        "global_payload_sha256": hashlib.sha256(global_payload).hexdigest(),
        "global_source_binary_sha256": sha256(global_bin),
        "global_source_spec_sha256": sha256(global_json),
        "global_payload_byte_exact": True,
    }


def write_stage(
    *,
    directory: Path,
    label: str,
    deletes: np.ndarray,
    inserts: np.ndarray,
    master_offset: int,
    full: np.ndarray,
    expected_tags: np.ndarray | None,
    checkpoint_deletes: np.ndarray | None,
    checkpoint_inserts: np.ndarray | None,
    checkpoint_positions: list[int] | None,
    checkpoint_selection: str | None,
    frozen_global_probe_bin: Path | None,
    frozen_global_probe_json: Path | None,
    source_identities: dict[str, dict[str, object]],
) -> dict[str, object]:
    directory.mkdir()
    trace_path = directory / f"delta_{label}.bin"
    tsv_path = directory / f"delta_{label}.tsv"
    write_trace(trace_path, deletes, inserts)
    write_tsv(tsv_path, deletes, inserts, master_offset)
    local_positions = floor_positions(deletes.size)
    local_document, local_tags = probe_document(
        deletes=deletes, inserts=inserts, positions=local_positions,
        selection="floor(j*(Ndelta-1)/8), j=0..8", master_offset=master_offset,
        schema="dynamic-vamana-w1-cumulative-local-probes-v1",
    )
    local_files = create_probe_files(
        directory, "delta_visibility_probes", local_document, local_tags, full,
    )
    active_identity = None
    global_files = None
    if expected_tags is not None:
        active_path = directory / "expected_active.tags.bin"
        write_tags(active_path, expected_tags)
        active_identity = {
            "path": active_path.name, "size_bytes": active_path.stat().st_size,
            "sha256": sha256(active_path), "count": int(expected_tags.size),
        }
    if checkpoint_deletes is not None:
        assert checkpoint_inserts is not None and checkpoint_positions is not None and checkpoint_selection is not None
        global_document, global_tags = probe_document(
            deletes=checkpoint_deletes, inserts=checkpoint_inserts,
            positions=checkpoint_positions, selection=checkpoint_selection,
            master_offset=0, schema="dynamic-vamana-w1-cumulative-checkpoint-probes-v1",
        )
        global_files = create_probe_files(
            directory, "checkpoint_visibility_probes", global_document, global_tags, full,
        )
        frozen_global_probe_bin = directory / "checkpoint_visibility_probes.bin"
        frozen_global_probe_json = directory / "checkpoint_visibility_probes.json"
    if (frozen_global_probe_bin is None) != (frozen_global_probe_json is None):
        raise ValueError("checkpoint-global probe binary/spec must be supplied together")
    combined_files = None
    if frozen_global_probe_bin is not None:
        combined_files = create_combined_probes(
            directory=directory,
            local_bin=directory / "delta_visibility_probes.bin",
            local_json=directory / "delta_visibility_probes.json",
            global_bin=frozen_global_probe_bin,
            global_json=frozen_global_probe_json,
            full=full,
        )
    parsed_deletes, parsed_inserts = read_trace(trace_path)
    tsv_rows = validate_tsv(tsv_path, parsed_deletes, parsed_inserts, master_offset)
    if not np.array_equal(parsed_deletes, deletes) or not np.array_equal(parsed_inserts, inserts):
        raise ValueError(f"written trace roundtrip failed: {label}")
    manifest = {
        "schema": "dynamic-vamana-w1-cumulative-delta-v1",
        "status": "pass",
        "label": label,
        "record_layout": "uint32 count; uint32 delete[count]; uint32 insert[count]",
        "record_order": "logical record i is (delete[i], insert[i])",
        "master_record_range": [master_offset, master_offset + int(deletes.size)],
        "incremental_replacements": int(deletes.size),
        "primitive_mutations": int(2 * deletes.size),
        "trace": {"path": trace_path.name, "size_bytes": trace_path.stat().st_size, "sha256": sha256(trace_path)},
        "tsv": {"path": tsv_path.name, "size_bytes": tsv_path.stat().st_size, "sha256": sha256(tsv_path), "rows": tsv_rows},
        "local_probes": local_files,
        "checkpoint_global_probes": global_files,
        "combined_probes": combined_files,
        "expected_active": active_identity,
        "assertions": {
            "delete_unique": bool(np.unique(deletes).size == deletes.size),
            "insert_unique": bool(np.unique(inserts).size == inserts.size),
            "insert_source_row_equals_insert_tag": True,
            "no_random_sampling": True,
        },
        "sources": source_identities,
    }
    atomic_json(directory / "delta_manifest.json", manifest)
    return manifest


def assert_formal_domains(deletes: np.ndarray, inserts: np.ndarray, count: int) -> None:
    if deletes.size != count or inserts.size != count:
        raise ValueError(f"formal trace count mismatch: expected {count}")
    if (np.unique(deletes).size != count or np.unique(inserts).size != count
            or np.any(deletes >= FORMAL_ACTIVE)
            or np.any(inserts < FORMAL_ACTIVE) or np.any(inserts >= FORMAL_CORPUS)):
        raise ValueError("formal trace uniqueness/domain assertion failed")


def prepare_formal(args: argparse.Namespace, partial: Path) -> tuple[dict[str, object], list[Path], dict[str, dict[str, object]]]:
    dataset = args.dataset.resolve(strict=True)
    trajectory = args.trajectory.resolve(strict=True)
    cp01 = args.cp01.resolve(strict=True)
    master_bin = trajectory / "master_replacements_1600k.bin"
    master_tsv = trajectory / "master_replacements_1600k.tsv"
    master_manifest = trajectory / "master_trace_manifest.json"
    cp05_bin = trajectory / "cp05/replace_cp05.bin"
    cp05_tsv = trajectory / "cp05/replace_cp05.tsv"
    cp05_active = trajectory / "cp05/active_cp05.tags.bin"
    cp05_manifest = trajectory / "cp05/checkpoint_manifest.json"
    cp01_bin = cp01 / "replace_cp01_80k.bin"
    cp01_tsv = cp01 / "replace_cp01_80k.tsv"
    cp01_active = cp01 / "active_cp01.tags.bin"
    cp01_probe_bin = cp01 / "visibility_probes.bin"
    cp01_probe_json = cp01 / "visibility_probes.json"
    cp05_probe_bin = trajectory / "cp05/visibility_probes.bin"
    cp05_probe_json = trajectory / "cp05/visibility_probes.json"
    cp00_active_path = dataset / "active_cp00.tags.bin"
    full_path = dataset / "full_10m.bin"
    sources = [master_bin, master_tsv, master_manifest, cp05_bin, cp05_tsv, cp05_active,
               cp05_manifest, cp01_bin, cp01_tsv, cp01_active, cp01_probe_bin,
               cp01_probe_json, cp05_probe_bin, cp05_probe_json, cp00_active_path, full_path]
    source_identities = snapshot_sources(sources)
    master_deletes, master_inserts = read_trace(master_bin)
    if master_deletes.size != 1_600_000:
        raise ValueError("frozen master trace is not 1.6M")
    assert_formal_domains(master_deletes, master_inserts, 1_600_000)
    master_tsv_rows = validate_master_tsv(master_tsv, master_deletes, master_inserts)
    cp01_deletes, cp01_inserts = read_trace(cp01_bin)
    cp05_deletes, cp05_inserts = read_trace(cp05_bin)
    assert_formal_domains(cp01_deletes, cp01_inserts, FORMAL_CP01)
    assert_formal_domains(cp05_deletes, cp05_inserts, FORMAL_CP05)
    validate_tsv(cp01_tsv, cp01_deletes, cp01_inserts)
    validate_tsv(cp05_tsv, cp05_deletes, cp05_inserts)
    if not (np.array_equal(cp01_deletes, master_deletes[:FORMAL_CP01])
            and np.array_equal(cp01_inserts, master_inserts[:FORMAL_CP01])):
        raise ValueError("historical CP01 is not the exact ordered master prefix")
    if not (np.array_equal(cp05_deletes, master_deletes[:FORMAL_CP05])
            and np.array_equal(cp05_inserts, master_inserts[:FORMAL_CP05])):
        raise ValueError("prepared CP05 is not the exact ordered master prefix")
    first_deletes = master_deletes[:FORMAL_CP01].astype("<u4", copy=False)
    first_inserts = master_inserts[:FORMAL_CP01].astype("<u4", copy=False)
    second_deletes = master_deletes[FORMAL_CP01:FORMAL_CP05].astype("<u4", copy=False)
    second_inserts = master_inserts[FORMAL_CP01:FORMAL_CP05].astype("<u4", copy=False)
    if np.intersect1d(first_deletes, second_deletes).size or np.intersect1d(first_inserts, second_inserts).size:
        raise ValueError("formal delta sets overlap")
    cp00_active = read_tags(cp00_active_path)
    if cp00_active.size != FORMAL_ACTIVE or not np.array_equal(cp00_active, np.arange(FORMAL_ACTIVE, dtype="<u4")):
        raise ValueError("formal CP00 active tags are not the frozen original domain")
    derived_cp01 = expected_active(cp00_active, first_deletes, first_inserts)
    derived_cp05 = expected_active(cp00_active, master_deletes[:FORMAL_CP05], master_inserts[:FORMAL_CP05])
    frozen_cp01 = read_tags(cp01_active)
    frozen_cp05 = read_tags(cp05_active)
    if not np.array_equal(derived_cp01, frozen_cp01):
        raise ValueError("derived CP01 active set differs from frozen CP01")
    if not np.array_equal(derived_cp05, frozen_cp05):
        raise ValueError("derived CP05 active set differs from prepared CP05")
    transitioned_cp05 = expected_active(derived_cp01, second_deletes, second_inserts)
    if not np.array_equal(transitioned_cp05, frozen_cp05):
        raise ValueError("CP01 + 320K delta does not equal frozen CP05 active set")
    full = vector_matrix(full_path)
    if full.shape != (FORMAL_CORPUS, 128):
        raise ValueError(f"unexpected SIFT10M full corpus shape: {full.shape}")
    first = write_stage(
        directory=partial / "cp00_to_cp01", label="cp00_to_cp01",
        deletes=first_deletes, inserts=first_inserts, master_offset=0, full=full,
        expected_tags=None, checkpoint_deletes=None, checkpoint_inserts=None,
        checkpoint_positions=None, checkpoint_selection=None, source_identities=source_identities,
        frozen_global_probe_bin=cp01_probe_bin, frozen_global_probe_json=cp01_probe_json,
    )
    second = write_stage(
        directory=partial / "cp01_to_cp05", label="cp01_to_cp05",
        deletes=second_deletes, inserts=second_inserts, master_offset=FORMAL_CP01, full=full,
        expected_tags=None, checkpoint_deletes=None, checkpoint_inserts=None,
        checkpoint_positions=None, checkpoint_selection=None, source_identities=source_identities,
        frozen_global_probe_bin=cp05_probe_bin, frozen_global_probe_json=cp05_probe_json,
    )
    first_path = partial / "cp00_to_cp01/delta_cp00_to_cp01.bin"
    second_path = partial / "cp01_to_cp05/delta_cp01_to_cp05.bin"
    first_out_d, first_out_i = read_trace(first_path)
    second_out_d, second_out_i = read_trace(second_path)
    joined_d = np.concatenate((first_out_d, second_out_d))
    joined_i = np.concatenate((first_out_i, second_out_i))
    parse_aware_exact = bool(
        np.array_equal(joined_d, master_deletes[:FORMAL_CP05])
        and np.array_equal(joined_i, master_inserts[:FORMAL_CP05])
    )
    cp01_binary_byte_exact = sha256(first_path) == sha256(cp01_bin) and first_path.read_bytes() == cp01_bin.read_bytes()
    cp01_tsv_byte_exact = sha256(partial / "cp00_to_cp01/delta_cp00_to_cp01.tsv") == sha256(cp01_tsv)
    if not parse_aware_exact or not cp01_binary_byte_exact:
        raise ValueError("formal delta composition/CP01 byte identity failed")
    output_inodes = {(path.stat().st_dev, path.stat().st_ino) for path in partial.rglob("*") if path.is_file()}
    source_inodes = {(identity["device"], identity["inode"]) for identity in source_identities.values()}
    if output_inodes & source_inodes:
        raise ValueError("a formal output aliases a source inode")
    validation = {
        "schema": "dynamic-vamana-w1-cumulative-formal-preparation-v1", "status": "pass",
        "classification": "input derivation only; no index/worker/scope execution",
        "preparer": {"realpath": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__).resolve()),
                     "python": sys.version, "numpy": np.__version__},
        "master_tsv_rows_validated": master_tsv_rows,
        "delta_counts": [FORMAL_CP01, FORMAL_CP05 - FORMAL_CP01],
        "parse_aware_logical_concatenation_equals_cp05_prefix": parse_aware_exact,
        "tsv_logical_concatenation_preserves_master_op_seq": True,
        "delta_cp00_to_cp01_binary_exact_historical_cp01": cp01_binary_byte_exact,
        "delta_cp00_to_cp01_tsv_exact_historical_cp01": cp01_tsv_byte_exact,
        "delta_cp00_to_cp01_tsv_semantic_exact_historical_cp01": True,
        "delete_sets_disjoint": True, "insert_sets_disjoint": True,
        "insert_source_row_equals_insert_tag": True,
        "cp01_active_exact": True, "cp01_plus_delta_equals_cp05_active": True,
        "no_random_sampling": True, "output_source_inode_disjoint": True,
        "stages": {"cp00_to_cp01": first, "cp01_to_cp05": second},
        "checkpoint_global_probe_inputs": {
            "cp01_binary": source_identities[str(cp01_probe_bin.resolve())],
            "cp01_json": source_identities[str(cp01_probe_json.resolve())],
            "cp05_binary": source_identities[str(cp05_probe_bin.resolve())],
            "cp05_json": source_identities[str(cp05_probe_json.resolve())],
        },
    }
    # Global probes are frozen upstream inputs, not regenerated or copied here.
    atomic_json(partial / "preparation_manifest.json", validation)
    return validation, sources, source_identities


def prepare_replay(args: argparse.Namespace, partial: Path) -> tuple[dict[str, object], list[Path], dict[str, dict[str, object]]]:
    dataset = args.dataset.resolve(strict=True)
    trace_csv = dataset / "smoke_replace_new_trace.csv"
    trace_bin = dataset / "smoke_replace_new_trace.bin"
    cp00_active_path = dataset / "active_cp00.tags.bin"
    full_path = dataset / "full_1m.bin"
    sources = [trace_csv, trace_bin, cp00_active_path, full_path]
    source_identities = snapshot_sources(sources)
    smoke_deletes, smoke_inserts = read_trace(trace_bin)
    if smoke_deletes.size < REPLAY_CP2:
        raise ValueError("SIFT1M smoke trace contains fewer than 80 records")
    rows: list[dict[str, str]] = []
    with trace_csv.open(newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"op_seq", "delete_tag", "insert_tag", "insert_source_row"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("SIFT1M smoke CSV lacks required columns")
        for row in reader:
            rows.append(row)
    if len(rows) < REPLAY_CP2:
        raise ValueError("SIFT1M smoke CSV contains fewer than 80 records")
    for index in range(REPLAY_CP2):
        row = rows[index]
        if (int(row["op_seq"]) != index
                or int(row["delete_tag"]) != int(smoke_deletes[index])
                or int(row["insert_tag"]) != int(smoke_inserts[index])
                or int(row["insert_source_row"]) != int(smoke_inserts[index])):
            raise ValueError(f"SIFT1M smoke CSV/binary mismatch at {index}")
    deletes = smoke_deletes[:REPLAY_CP2].astype("<u4", copy=False)
    inserts = smoke_inserts[:REPLAY_CP2].astype("<u4", copy=False)
    if (np.unique(deletes).size != REPLAY_CP2 or np.unique(inserts).size != REPLAY_CP2
            or np.any(deletes >= REPLAY_ACTIVE)
            or np.any(inserts < REPLAY_ACTIVE) or np.any(inserts >= REPLAY_CORPUS)
            or np.intersect1d(deletes, inserts).size):
        raise ValueError("SIFT1M replay domain/uniqueness failed")
    first_deletes, first_inserts = deletes[:REPLAY_CP1], inserts[:REPLAY_CP1]
    second_deletes, second_inserts = deletes[REPLAY_CP1:REPLAY_CP2], inserts[REPLAY_CP1:REPLAY_CP2]
    if np.intersect1d(first_deletes, second_deletes).size or np.intersect1d(first_inserts, second_inserts).size:
        raise ValueError("SIFT1M replay delta sets overlap")
    cp00_active = read_tags(cp00_active_path)
    if cp00_active.size != REPLAY_ACTIVE:
        raise ValueError("SIFT1M CP00 active count is not 800K")
    cp16_active = expected_active(cp00_active, first_deletes, first_inserts)
    cp80_active = expected_active(cp00_active, deletes, inserts)
    if not np.array_equal(expected_active(cp16_active, second_deletes, second_inserts), cp80_active):
        raise ValueError("SIFT1M CP16 + 64 delta does not equal CP80")
    full = vector_matrix(full_path)
    if full.shape != (REPLAY_CORPUS, 128):
        raise ValueError(f"unexpected SIFT1M full corpus shape: {full.shape}")
    first = write_stage(
        directory=partial / "cp00_to_cp16", label="cp00_to_cp16",
        deletes=first_deletes, inserts=first_inserts, master_offset=0, full=full,
        expected_tags=cp16_active, checkpoint_deletes=first_deletes,
        checkpoint_inserts=first_inserts, checkpoint_positions=micro_round_positions(REPLAY_CP1),
        checkpoint_selection="legacy w1_micro_prepare round(j*(N-1)/8), endpoints included",
        frozen_global_probe_bin=None, frozen_global_probe_json=None,
        source_identities=source_identities,
    )
    second = write_stage(
        directory=partial / "cp16_to_cp80", label="cp16_to_cp80",
        deletes=second_deletes, inserts=second_inserts, master_offset=REPLAY_CP1, full=full,
        expected_tags=cp80_active, checkpoint_deletes=deletes, checkpoint_inserts=inserts,
        checkpoint_positions=micro_round_positions(REPLAY_CP2),
        checkpoint_selection="w1_micro_prepare round(j*(N-1)/8), endpoints included",
        frozen_global_probe_bin=None, frozen_global_probe_json=None,
        source_identities=source_identities,
    )
    query_source = partial / "cp16_to_cp80/combined_visibility_probes.bin"
    query_path = partial / "query_36.bin"
    atomic_bytes(query_path, lambda stream: stream.write(query_source.read_bytes()))
    if query_path.stat().st_ino == query_source.stat().st_ino or sha256(query_path) != sha256(query_source):
        raise ValueError("replay query_36 is not an inode-independent exact combined-probe copy")
    queries = np.asarray(vector_matrix(query_path), dtype="<f4")
    if queries.shape != (36, 128):
        raise ValueError("replay query_36 does not have shape 36x128")
    gt_evidence: dict[str, dict[str, object]] = {}
    for name, active in (("gt_cp00_36", cp00_active), ("gt_cp16_36", cp16_active), ("gt_cp80_36", cp80_active)):
        ids, distances = exact_groundtruth(full, active, queries)
        gt_path = partial / name
        write_groundtruth(gt_path, ids, distances)
        gt_evidence[name] = validate_groundtruth(gt_path, full, active, queries)
    d1, i1 = read_trace(partial / "cp00_to_cp16/delta_cp00_to_cp16.bin")
    d2, i2 = read_trace(partial / "cp16_to_cp80/delta_cp16_to_cp80.bin")
    parse_aware_exact = bool(np.array_equal(np.concatenate((d1, d2)), deletes)
                             and np.array_equal(np.concatenate((i1, i2)), inserts))
    if not parse_aware_exact:
        raise ValueError("replay parse-aware concatenation failed")
    # The first stage must exactly preserve the historical 16-op micro trace semantics.
    legacy_positions = micro_round_positions(REPLAY_CP1)
    if legacy_positions != [0, 2, 4, 6, 8, 9, 11, 13, 15]:
        raise ValueError("legacy 16-op micro positions changed")
    output_inodes = {(path.stat().st_dev, path.stat().st_ino) for path in partial.rglob("*") if path.is_file()}
    source_inodes = {(identity["device"], identity["inode"]) for identity in source_identities.values()}
    if output_inodes & source_inodes:
        raise ValueError("a replay output aliases a source inode")
    validation = {
        "schema": "dynamic-vamana-w1-cumulative-replay-preparation-v1", "status": "pass",
        "classification": "1M infrastructure correctness replay only; no performance interpretation",
        "preparer": {"realpath": str(Path(__file__).resolve()), "sha256": sha256(Path(__file__).resolve()),
                     "python": sys.version, "numpy": np.__version__},
        "cumulative_replacements": [REPLAY_CP1, REPLAY_CP2], "stage_delta_replacements": [REPLAY_CP1, REPLAY_CP2 - REPLAY_CP1],
        "parse_aware_logical_concatenation_equals_first_80_smoke_records": parse_aware_exact,
        "tsv_logical_concatenation_preserves_smoke_op_seq": True,
        "legacy_16_record_semantics_reused": True, "legacy_16_checkpoint_probe_positions": legacy_positions,
        "stage_local_selection": "floor(j*(Ndelta-1)/8)",
        "checkpoint_global_selection": "w1_micro_prepare round(j*(Ncumulative-1)/8)",
        "identity_query": {"path": query_path.name, "sha256": sha256(query_path),
                           "size_bytes": query_path.stat().st_size, "shape": [36, 128],
                           "source": "cp16_to_cp80/combined_visibility_probes.bin",
                           "source_byte_exact": True, "inode_independent": True},
        "exact_groundtruth": gt_evidence,
        "cp16_active_exact": True, "cp16_plus_delta_equals_cp80_active": True,
        "delete_sets_disjoint": True, "insert_sets_disjoint": True,
        "insert_source_row_equals_insert_tag": True, "no_random_sampling": True,
        "output_source_inode_disjoint": True,
        "stages": {"cp00_to_cp16": first, "cp16_to_cp80": second},
    }
    atomic_json(partial / "preparation_manifest.json", validation)
    return validation, sources, source_identities


def fsync_tree(root: Path) -> None:
    for path in sorted(item for item in root.rglob("*") if item.is_file() and not item.is_symlink()):
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    directories = sorted([root, *(item for item in root.rglob("*") if item.is_dir())],
                         key=lambda item: len(item.parts), reverse=True)
    for directory in directories:
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def freeze_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"output symlink forbidden: {path}")
        if path.is_file():
            os.chmod(path, 0o444)
        elif not path.is_dir():
            raise ValueError(f"non-regular output forbidden: {path}")
    directories = sorted([root, *(item for item in root.rglob("*") if item.is_dir())],
                         key=lambda item: len(item.parts), reverse=True)
    for directory in directories:
        os.chmod(directory, 0o555)


def validate_frozen_tree(root: Path, sources: dict[str, dict[str, object]]) -> dict[str, object]:
    files: dict[str, dict[str, object]] = {}
    seen_inodes: set[tuple[int, int]] = set()
    source_inodes = {(int(value["device"]), int(value["inode"])) for value in sources.values()}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        relative = str(path.relative_to(root))
        if path.is_symlink():
            raise ValueError(f"frozen output symlink: {path}")
        if path.is_dir():
            if stat.S_IMODE(info.st_mode) != 0o555:
                raise ValueError(f"directory is not 0555: {path}")
            continue
        if not path.is_file() or stat.S_IMODE(info.st_mode) != 0o444:
            raise ValueError(f"output is not a 0444 regular file: {path}")
        inode = (info.st_dev, info.st_ino)
        if inode in seen_inodes or inode in source_inodes:
            raise ValueError(f"output inode is not independent: {path}")
        seen_inodes.add(inode)
        files[relative] = {"size_bytes": info.st_size, "sha256": sha256(path),
                           "device": info.st_dev, "inode": info.st_ino, "mode": 0o444}
    if stat.S_IMODE(root.stat().st_mode) != 0o555:
        raise ValueError("published output root is not 0555")
    return {"status": "pass", "directories_mode": "0555", "regular_files_mode": "0444",
            "inode_independent": True, "files": files}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("formal", "replay"), required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trajectory", type=Path, help="formal frozen w1_trajectory directory")
    parser.add_argument("--cp01", type=Path, help="formal frozen historical w1_cp01 directory")
    args = parser.parse_args()
    if args.mode == "formal" and (args.trajectory is None or args.cp01 is None):
        parser.error("formal mode requires --trajectory and --cp01")
    if args.mode == "replay" and (args.trajectory is not None or args.cp01 is not None):
        parser.error("replay mode does not accept --trajectory/--cp01")
    return args


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    if output.exists() or output.is_symlink():
        raise SystemExit(f"output reuse refused: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(f".{output.name}.partial.{os.getpid()}")
    if partial.exists() or partial.is_symlink():
        raise SystemExit(f"partial output collision: {partial}")
    partial.mkdir()
    try:
        if args.mode == "formal":
            validation, source_paths, before = prepare_formal(args, partial)
        else:
            validation, source_paths, before = prepare_replay(args, partial)
        after = snapshot_sources(source_paths)
        if before != after:
            raise ValueError("source input changed during final preservation audit")
        atomic_json(partial / "source_preservation.json", {
            "schema": "dynamic-vamana-w1-cumulative-source-preservation-v1",
            "status": "pass", "before": before, "after": after,
        })
        fsync_tree(partial)
        freeze_tree(partial)
        os.replace(partial, output)
        parent_descriptor = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
        frozen = validate_frozen_tree(output, after)
        result = {
            "status": "pass", "mode": args.mode, "output": str(output),
            "preparation_schema": validation["schema"],
            "preparation_manifest_sha256": sha256(output / "preparation_manifest.json"),
            "source_preservation_sha256": sha256(output / "source_preservation.json"),
            "frozen": frozen,
        }
        print(json.dumps(result, sort_keys=True))
    except BaseException:
        if partial.exists() and not partial.is_symlink():
            for path in partial.rglob("*"):
                if path.is_dir():
                    os.chmod(path, 0o700)
                elif path.is_file():
                    os.chmod(path, 0o600)
            os.chmod(partial, 0o700)
            shutil.rmtree(partial)
        raise


if __name__ == "__main__":
    main()
