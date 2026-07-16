#!/usr/bin/env python3
"""Compute, remap, deeply audit, and atomically publish one trajectory GT."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
from pathlib import Path

import numpy as np

from w1_trajectory_generate import durable_tree

AUDIT_SEED = 20260713
FIXED_QIDS = [0, 17, 7150, 9999]


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def block_sha(path: Path, offset: int, length: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(offset)
        for block in iter(lambda: stream.read(min(8 << 20, length)), b""):
            take = min(len(block), length)
            digest.update(block[:take]); length -= take
            if length == 0: break
    if length:
        raise ValueError("short binary block")
    return digest.hexdigest()


def head(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        raw = stream.read(8)
    if len(raw) != 8: raise ValueError(f"short header: {path}")
    return struct.unpack("<II", raw)


def float_bin(path: Path) -> np.memmap:
    n, d = head(path)
    if path.stat().st_size != 8 + n * d * 4: raise ValueError(f"float binary size mismatch: {path}")
    return np.memmap(path, dtype="<f4", mode="r", offset=8, shape=(n, d))


def tags_bin(path: Path) -> np.memmap:
    n, d = head(path)
    if d != 1 or path.stat().st_size != 8 + n * 4: raise ValueError(f"tag binary size mismatch: {path}")
    return np.memmap(path, dtype="<u4", mode="r", offset=8, shape=(n,))


def truth(path: Path) -> tuple[np.memmap, np.memmap]:
    n, k = head(path)
    if path.stat().st_size != 8 + n * k * 8: raise ValueError(f"truthset size mismatch: {path}")
    return (np.memmap(path, dtype="<u4", mode="r", offset=8, shape=(n, k)),
            np.memmap(path, dtype="<f4", mode="r", offset=8 + n * k * 4, shape=(n, k)))


def brute(base: np.memmap, tags: np.memmap, query: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    best_ids = np.empty(0, dtype="<u4"); best_distances = np.empty(0, dtype="<f4")
    for start in range(0, base.shape[0], 8192):
        block = np.asarray(base[start:start + 8192], dtype=np.float32)
        diff = block - query
        distances = np.einsum("ij,ij->i", diff, diff, optimize=True)
        ids = np.asarray(tags[start:start + block.shape[0]], dtype="<u4")
        if best_ids.size:
            distances = np.concatenate((best_distances, distances)); ids = np.concatenate((best_ids, ids))
        indexes = np.argpartition(distances, min(k, distances.size) - 1)[:k]
        order = np.lexsort((ids[indexes], distances[indexes]))
        best_ids = ids[indexes][order].astype("<u4", copy=False)
        best_distances = distances[indexes][order].astype("<f4", copy=False)
    return best_ids, best_distances


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=int, choices=(5, 10, 20), required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, pct = args.root.resolve(), args.checkpoint
    checkpoint = args.checkpoint_dir.resolve(); output = args.output.resolve()
    partial = output.with_name("." + output.name + ".partial")
    if checkpoint.name != f"cp{pct:02d}" or output.name != f"cp{pct:02d}" or output.exists() or partial.exists():
        raise SystemExit("GT checkpoint identity/freshness guard failed")
    vector_path = checkpoint / f"active_cp{pct:02d}.bin"
    tag_path = checkpoint / f"active_cp{pct:02d}.tags.bin"
    trace_path = checkpoint / f"replace_cp{pct:02d}.bin"
    query_path = root / "datasets/sift10m/query.bin"
    tool = root / "build/DiskANN/apps/utils/compute_groundtruth"
    openblas = root / "build/openblas-install/lib/libopenblas.so"
    for path in (vector_path, tag_path, trace_path, query_path, tool, openblas):
        if not path.exists(): raise SystemExit(f"missing GT input: {path}")
    preflight = json.loads(args.preflight.read_text())
    if preflight.get("status") != "pass": raise SystemExit("GT preflight is not a pass")
    for name, path in (("query", query_path), ("compute_groundtruth", tool), ("openblas", openblas)):
        identity = preflight["formal_inputs"][name]
        if (path.resolve() != Path(identity["realpath"]).resolve() or path.stat().st_size != identity["size_bytes"]
                or sha(path) != identity["sha256"]):
            raise SystemExit(f"GT frozen input changed: {name}")
    partial.mkdir(parents=True, exist_ok=False)
    locations = partial / "locations_top100.bin"; log = partial / "compute_groundtruth.log"
    env = dict(os.environ, OPENBLAS_NUM_THREADS="56", OMP_NUM_THREADS="56", LD_PRELOAD=str(openblas),
               TMPDIR=str((root / "tmp/w1_trajectory_prep").resolve()))
    command = [str(tool), "--data_type", "float", "--dist_fn", "l2", "--base_file", str(vector_path),
               "--query_file", str(query_path), "--gt_file", str(locations), "--K", "100"]
    with log.open("w") as stream:
        completed = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, check=False)
    log_text = log.read_text(errors="replace")
    if completed.returncode != 0 or "WARNING: found less than k GT entries" in log_text:
        raise SystemExit("location-ID compute_groundtruth failed or returned less than K")
    location_ids, location_distances = truth(locations)
    if location_ids.shape != (10_000, 100) or int(location_ids.max()) >= 8_000_000:
        raise SystemExit("location truthset shape/range invalid")
    if (np.any(np.diff(np.sort(np.asarray(location_ids), axis=1), axis=1) == 0)
            or not np.isfinite(location_distances).all()
            or np.any(location_distances[:, 1:] < location_distances[:, :-1])):
        raise SystemExit("location truthset uniqueness/distance validation failed")
    tags = tags_bin(tag_path)
    if tags.size != 8_000_000 or np.unique(tags).size != tags.size:
        raise SystemExit("active tags invalid")
    distance_offset = 8 + 10_000 * 100 * 4; distance_bytes = 10_000 * 100 * 4
    before_distance_sha = block_sha(locations, distance_offset, distance_bytes)
    candidate = partial / f"gt_cp{pct:02d}.candidate"
    mapped = np.asarray(tags[location_ids], dtype="<u4")
    with candidate.open("wb") as stream:
        stream.write(struct.pack("<II", 10_000, 100)); mapped.tofile(stream); np.asarray(location_distances, dtype="<f4").tofile(stream)
    after_distance_sha = block_sha(candidate, distance_offset, distance_bytes)
    if before_distance_sha != after_distance_sha:
        raise SystemExit("distance block changed during location-to-tag remap")
    ids, distances = truth(candidate)
    active_mask = np.zeros(10_000_000, dtype=np.bool_); active_mask[np.asarray(tags, dtype=np.int64)] = True
    with trace_path.open("rb") as stream: count = struct.unpack("<I", stream.read(4))[0]
    deleted = np.memmap(trace_path, dtype="<u4", mode="r", offset=4, shape=(count,))
    if (not active_mask[np.asarray(ids, dtype=np.int64)].all()
            or np.any(np.isin(np.asarray(ids), np.asarray(deleted)))
            or np.any(np.diff(np.sort(np.asarray(ids), axis=1), axis=1) == 0)
            or not np.isfinite(distances).all() or np.any(distances[:, 1:] < distances[:, :-1])):
        raise SystemExit("final tag truthset structural validation failed")
    base = float_bin(vector_path); queries = float_bin(query_path)
    rng = np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence([AUDIT_SEED, 0x415544])))
    candidates = np.setdiff1d(np.arange(10_000, dtype=np.int64), np.asarray(FIXED_QIDS, dtype=np.int64), assume_unique=True)
    extra = rng.choice(candidates, size=32, replace=False).tolist()
    audit_qids = FIXED_QIDS + [int(value) for value in extra]
    audits = []
    tag_to_row = np.full(10_000_000, -1, dtype=np.int64); tag_to_row[np.asarray(tags, dtype=np.int64)] = np.arange(tags.size)
    for qid in audit_qids:
        exact_ids, exact_distances = brute(base, tags, np.asarray(queries[qid]), 100)
        formal_ids = np.asarray(ids[qid]); formal_distances = np.asarray(distances[qid])
        rows = tag_to_row[formal_ids.astype(np.int64)]
        returned = np.asarray(base[rows], dtype=np.float32) - np.asarray(queries[qid], dtype=np.float32)
        returned_distances = np.einsum("ij,ij->i", returned, returned, optimize=True).astype("<f4")
        overlap = int(np.intersect1d(formal_ids, exact_ids).size)
        max_report_error = float(np.max(np.abs(formal_distances - returned_distances)))
        formal_order = np.lexsort((formal_ids, returned_distances))
        exact_order = np.lexsort((exact_ids, exact_distances))
        canonical_formal_ids = formal_ids[formal_order]
        canonical_exact_ids = exact_ids[exact_order]
        canonical_formal_distances = returned_distances[formal_order]
        canonical_exact_distances = exact_distances[exact_order]
        max_position_distance_error = float(np.max(np.abs(canonical_formal_distances - canonical_exact_distances)))
        raw_ids_position_exact = bool(np.array_equal(formal_ids, exact_ids))
        canonical_ids_position_exact = bool(np.array_equal(canonical_formal_ids, canonical_exact_ids))
        distance_comparison_pass = bool(max_position_distance_error <= 5e-3 and max_report_error <= 5e-3)
        canonical_exact = bool(overlap == 100 and canonical_ids_position_exact and distance_comparison_pass)
        raw_order_tie_only = bool(raw_ids_position_exact or (canonical_exact and np.array_equal(returned_distances, exact_distances)))
        tie_aware_exact = bool(canonical_exact and raw_order_tie_only)
        if not tie_aware_exact:
            raise SystemExit(f"brute-force canonical tie-aware audit failed qid={qid}")
        audits.append({"query_id": qid, "formal_top100_ids": formal_ids.tolist(),
                       "formal_top100_distances": [float(x) for x in formal_distances],
                       "bruteforce_top100_ids": exact_ids.tolist(),
                       "bruteforce_top100_distances": [float(x) for x in exact_distances],
                       "raw_position_id_equal": (formal_ids == exact_ids).tolist(),
                       "raw_top100_id_exact_match": raw_ids_position_exact,
                       "canonical_order": "recomputed squared-L2 distance then uint32 tag",
                       "canonical_formal_top100_ids": canonical_formal_ids.tolist(),
                       "canonical_formal_top100_distances": [float(x) for x in canonical_formal_distances],
                       "canonical_bruteforce_top100_ids": canonical_exact_ids.tolist(),
                       "canonical_bruteforce_top100_distances": [float(x) for x in canonical_exact_distances],
                       "canonical_position_id_equal": (canonical_formal_ids == canonical_exact_ids).tolist(),
                       "canonical_position_distance_abs_error": [float(x) for x in np.abs(canonical_formal_distances - canonical_exact_distances)],
                       "canonical_top100_id_exact_match": canonical_ids_position_exact,
                       "top100_id_overlap": overlap, "max_reported_distance_error": max_report_error,
                       "max_position_distance_error": max_position_distance_error,
                       "position_distance_tolerance": 5e-3,
                       "position_distance_comparison_pass": distance_comparison_pass,
                       "tie_aware_top100_exact": tie_aware_exact,
                       "raw_order_difference_only_equal_distance_ties": raw_order_tie_only})
    tag_zero_active = bool(active_mask[0])
    validation = {"schema": "dynamic-vamana-w1-trajectory-gt-validation-v1", "status": "pass",
                  "checkpoint_pct": pct, "shape": [10_000, 100], "all_location_ids_in_range": True,
                  "location_row_ids_unique": True, "final_tags_all_active": True, "deleted_tags_absent": True,
                  "final_row_tags_unique": True, "distances_finite": True, "distances_monotonic": True,
                  "distance_block_sha256_before_remap": before_distance_sha,
                  "distance_block_sha256_after_remap": after_distance_sha, "distance_block_byte_identical": True,
                  "less_than_k_warning_absent": True, "audit_seed": AUDIT_SEED,
                  "audit_prng": "numpy.random.PCG64DXSM", "audit_qids": audit_qids,
                  "independent_bruteforce_audits": audits, "tag_zero_active": tag_zero_active,
                  "tag_zero_deleted": not tag_zero_active}
    validation_path = partial / "gt_validation.json"
    validation_path.write_text(json.dumps(validation, indent=2) + "\n")
    final_gt = partial / f"gt_cp{pct:02d}"
    os.replace(candidate, final_gt)
    artifact_names = ["locations_top100.bin", "compute_groundtruth.log", f"gt_cp{pct:02d}", "gt_validation.json"]
    manifest = {"schema": "dynamic-vamana-w1-trajectory-gt-manifest-v1", "status": "pass",
                "checkpoint_pct": pct, "atomic_directory_publish": True, "compute_command": command,
                "compute_environment": {"OPENBLAS_NUM_THREADS": "56", "OMP_NUM_THREADS": "56",
                                        "LD_PRELOAD": str(openblas.resolve()), "TMPDIR": env["TMPDIR"]},
                "active_vectors_sha256": sha(vector_path), "active_tags_sha256": sha(tag_path),
                "query_sha256": sha(query_path), "compute_groundtruth_sha256": sha(tool),
                "openblas_realpath": str(openblas.resolve()), "openblas_size_bytes": openblas.stat().st_size,
                "openblas_sha256": sha(openblas), "preflight_sha256": sha(args.preflight),
                "artifacts": {name: {"size_bytes": (partial / name).stat().st_size, "sha256": sha(partial / name)}
                              for name in artifact_names},
                "published_directory": str(output), "published_truthset": str(output / f"gt_cp{pct:02d}")}
    (partial / "gt_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    output.parent.mkdir(parents=True, exist_ok=True)
    durable_tree(partial)
    os.replace(partial, output)
    directory_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


if __name__ == "__main__":
    main()
