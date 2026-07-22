#!/usr/bin/env python3
"""Measure DiskANN PQ reconstruction error for build and held-out insert sets."""

from __future__ import annotations

import argparse
import json
import os
import struct
from pathlib import Path

import numpy as np


HEADER = struct.Struct("<II")


def read_header(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        raw = f.read(HEADER.size)
    if len(raw) != HEADER.size:
        raise ValueError(f"truncated header: {path}")
    return HEADER.unpack(raw)


def matrix_at(path: Path, offset: int, dtype: str) -> np.ndarray:
    item_dtype = np.dtype(dtype)
    with path.open("rb") as f:
        f.seek(offset)
        raw = f.read(HEADER.size)
        if len(raw) != HEADER.size:
            raise ValueError(f"truncated matrix header at {offset}: {path}")
        rows, cols = HEADER.unpack(raw)
        data = np.fromfile(f, dtype=item_dtype, count=rows * cols)
    if data.size != rows * cols:
        raise ValueError(f"truncated matrix payload at {offset}: {path}")
    return data.reshape(rows, cols)


def load_pivots(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[int]]:
    offset_shape = read_header(path)
    if offset_shape not in ((4, 1), (5, 1)):
        raise ValueError(f"unexpected pivot offset shape {offset_shape}")
    with path.open("rb") as f:
        f.seek(HEADER.size)
        offsets = np.fromfile(f, dtype="<u8", count=offset_shape[0])
    if offsets.size != offset_shape[0]:
        raise ValueError("truncated pivot offset table")
    pivots = matrix_at(path, int(offsets[0]), "<f4")
    centroid = matrix_at(path, int(offsets[1]), "<f4").reshape(-1)
    # New files have chunk offsets in entry 2; old five-entry files use entry 3.
    chunk_index = 2 if offsets.size == 4 else 3
    chunks = matrix_at(path, int(offsets[chunk_index]), "<u4").reshape(-1)
    if int(offsets[-1]) != path.stat().st_size:
        raise ValueError(f"last pivot offset {offsets[-1]} != file size {path.stat().st_size}")
    if pivots.shape[1] != centroid.size or chunks[0] != 0 or chunks[-1] != centroid.size:
        raise ValueError("inconsistent pivots/centroid/chunk offsets")
    return pivots, centroid, chunks, [int(x) for x in offsets]


def matrix_memmap(path: Path, dtype: str) -> np.memmap:
    rows, cols = read_header(path)
    want = HEADER.size + rows * cols * np.dtype(dtype).itemsize
    if path.stat().st_size != want:
        raise ValueError(f"{path}: size {path.stat().st_size} != expected {want}")
    return np.memmap(path, mode="r", dtype=dtype, offset=HEADER.size, shape=(rows, cols))


def summarize(values: np.ndarray) -> dict[str, float]:
    nonzero = int(np.count_nonzero(values))
    return {
        "mean": float(np.mean(values, dtype=np.float64)),
        "median": float(np.median(values)),
        "p95": float(np.percentile(values, 95)),
        "p99": float(np.percentile(values, 99)),
        "p99_9": float(np.percentile(values, 99.9)),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "nonzero_count": nonzero,
        "nonzero_fraction": float(nonzero / values.size),
    }


def top_errors(values: np.ndarray, count: int = 10) -> list[dict[str, float | int]]:
    ids = np.argsort(values)[-count:][::-1]
    return [{"point_id": int(i), "pq_error": float(values[i])} for i in ids]


def decode_error(
    vectors: np.memmap,
    codes: np.memmap,
    pivots: np.ndarray,
    centroid: np.ndarray,
    chunks: np.ndarray,
    block_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    npts, dim = vectors.shape
    nchunks = chunks.size - 1
    if codes.shape != (npts, nchunks):
        raise ValueError(f"code shape {codes.shape} != {(npts, nchunks)}")
    errors = np.empty(npts, dtype=np.float64)
    chunk_sum = np.zeros(nchunks, dtype=np.float64)
    for lo in range(0, npts, block_size):
        hi = min(lo + block_size, npts)
        x = np.asarray(vectors[lo:hi], dtype=np.float32)
        total = np.zeros(hi - lo, dtype=np.float64)
        for chunk in range(nchunks):
            begin, end = int(chunks[chunk]), int(chunks[chunk + 1])
            reconstruction = pivots[np.asarray(codes[lo:hi, chunk]), begin:end] + centroid[begin:end]
            residual = x[:, begin:end] - reconstruction
            part = np.einsum("ij,ij->i", residual, residual, dtype=np.float64)
            total += part
            chunk_sum[chunk] += part.sum(dtype=np.float64)
        errors[lo:hi] = total
    return errors, chunk_sum / npts


def encode_chunk(values: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Return original center IDs; optimized exact path for the 1-D chunks in P01."""
    if values.shape[1] == 1:
        raw = values[:, 0]
        center_1d = centers[:, 0]
        order = np.argsort(center_1d, kind="stable")
        sorted_centers = center_1d[order]
        right = np.searchsorted(sorted_centers, raw, side="left")
        right = np.clip(right, 0, sorted_centers.size - 1)
        left = np.maximum(right - 1, 0)
        choose_left = np.square(raw - sorted_centers[left]) <= np.square(raw - sorted_centers[right])
        positions = np.where(choose_left, left, right)
        return order[positions].astype(np.uint8, copy=False)

    # Generic exact fallback, bounded to avoid a large temporary tensor.
    result = np.empty(values.shape[0], dtype=np.uint8)
    center_norms = np.einsum("ij,ij->i", centers, centers)
    mini = 2048
    for lo in range(0, values.shape[0], mini):
        hi = min(lo + mini, values.shape[0])
        batch = values[lo:hi]
        distances = (
            np.einsum("ij,ij->i", batch, batch)[:, None]
            + center_norms[None, :]
            - 2.0 * batch @ centers.T
        )
        result[lo:hi] = np.argmin(distances, axis=1).astype(np.uint8)
    return result


def encode_and_error(
    vectors: np.memmap,
    output_codes: Path,
    pivots: np.ndarray,
    centroid: np.ndarray,
    chunks: np.ndarray,
    block_size: int,
) -> tuple[np.ndarray, np.ndarray, np.memmap]:
    npts, _ = vectors.shape
    nchunks = chunks.size - 1
    with output_codes.open("wb") as f:
        f.write(HEADER.pack(npts, nchunks))
        f.truncate(HEADER.size + npts * nchunks)
    codes = np.memmap(output_codes, mode="r+", dtype="u1", offset=HEADER.size, shape=(npts, nchunks))
    errors = np.empty(npts, dtype=np.float64)
    chunk_sum = np.zeros(nchunks, dtype=np.float64)
    for lo in range(0, npts, block_size):
        hi = min(lo + block_size, npts)
        x = np.asarray(vectors[lo:hi], dtype=np.float32)
        centered = x - centroid
        total = np.zeros(hi - lo, dtype=np.float64)
        for chunk in range(nchunks):
            begin, end = int(chunks[chunk]), int(chunks[chunk + 1])
            code = encode_chunk(centered[:, begin:end], pivots[:, begin:end])
            codes[lo:hi, chunk] = code
            # Measure decoded reconstruction error with the same operation order as BUILD.
            reconstruction = pivots[code, begin:end] + centroid[begin:end]
            residual = x[:, begin:end] - reconstruction
            part = np.einsum("ij,ij->i", residual, residual, dtype=np.float64)
            total += part
            chunk_sum[chunk] += part.sum(dtype=np.float64)
        errors[lo:hi] = total
    codes.flush()
    return errors, chunk_sum / npts, codes


def verify_codes_and_errors(
    vectors: np.memmap,
    codes: np.memmap,
    pivots: np.ndarray,
    centroid: np.ndarray,
    chunks: np.ndarray,
    ids: list[int],
) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    for point_id in ids:
        centered = np.asarray(vectors[point_id], dtype=np.float32) - centroid
        brute_codes = []
        total = 0.0
        for chunk in range(chunks.size - 1):
            begin, end = int(chunks[chunk]), int(chunks[chunk + 1])
            delta = pivots[:, begin:end] - centered[None, begin:end]
            distances = np.einsum("ij,ij->i", delta, delta)
            code = int(np.argmin(distances))
            brute_codes.append(code)
            reconstruction = pivots[code, begin:end] + centroid[begin:end]
            residual = np.asarray(vectors[point_id, begin:end]) - reconstruction
            total += float(np.dot(residual, residual))
        stored = np.asarray(codes[point_id], dtype=np.uint8)
        brute = np.asarray(brute_codes, dtype=np.uint8)
        checks.append(
            {
                "point_id": point_id,
                "pq_error": total,
                "code_mismatches_vs_bruteforce": int(np.count_nonzero(stored != brute)),
                "vector_squared_norm": float(np.dot(vectors[point_id], vectors[point_id])),
            }
        )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-data", type=Path, required=True)
    parser.add_argument("--insert-data", type=Path, required=True)
    parser.add_argument("--pivots", type=Path, required=True)
    parser.add_argument("--build-codes", type=Path, required=True)
    parser.add_argument("--insert-codes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--block-size", type=int, default=32_768)
    args = parser.parse_args()

    pivots, centroid, chunks, pivot_offsets = load_pivots(args.pivots)
    build = matrix_memmap(args.build_data, "<f4")
    insert = matrix_memmap(args.insert_data, "<f4")
    build_codes = matrix_memmap(args.build_codes, "u1")
    if build.shape[1] != insert.shape[1] or build.shape[1] != pivots.shape[1]:
        raise ValueError("dimensionality mismatch")

    build_errors, build_chunk = decode_error(
        build, build_codes, pivots, centroid, chunks, args.block_size
    )
    insert_errors, insert_chunk, insert_codes = encode_and_error(
        insert, args.insert_codes, pivots, centroid, chunks, args.block_size
    )

    sample_ids_build = list(dict.fromkeys([0, 1, 12345, build.shape[0] - 1, int(np.argmax(build_errors))]))
    sample_ids_insert = list(dict.fromkeys([0, 1, 12345, insert.shape[0] - 1, int(np.argmax(insert_errors))]))
    result = {
        "data": {
            "build_count": int(build.shape[0]),
            "insert_count": int(insert.shape[0]),
            "total_count": int(build.shape[0] + insert.shape[0]),
            "dim": int(build.shape[1]),
        },
        "pq": {
            "num_centers": int(pivots.shape[0]),
            "num_chunks": int(chunks.size - 1),
            "chunk_offsets": chunks.astype(int).tolist(),
            "pivot_file_offsets": pivot_offsets,
            "centroid_squared_norm": float(np.dot(centroid, centroid)),
        },
        "build": summarize(build_errors),
        "insert": summarize(insert_errors),
        "mean_ratio_insert_over_build": float(np.mean(insert_errors) / np.mean(build_errors)),
        "top_errors": {
            "build": top_errors(build_errors),
            "insert": top_errors(insert_errors),
        },
        "per_chunk": [
            {
                "chunk": int(i),
                "dim_begin": int(chunks[i]),
                "dim_end": int(chunks[i + 1]),
                "build_mean": float(build_chunk[i]),
                "insert_mean": float(insert_chunk[i]),
                "ratio": (
                    float(insert_chunk[i] / build_chunk[i])
                    if build_chunk[i] != 0
                    else None
                ),
            }
            for i in range(chunks.size - 1)
        ],
        "verification": {
            "build": verify_codes_and_errors(
                build, build_codes, pivots, centroid, chunks, sample_ids_build
            ),
            "insert": verify_codes_and_errors(
                insert, insert_codes, pivots, centroid, chunks, sample_ids_insert
            ),
        },
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "build": result["build"],
        "insert": result["insert"],
        "ratio": result["mean_ratio_insert_over_build"],
        "verification": result["verification"],
    }, indent=2))


if __name__ == "__main__":
    main()
