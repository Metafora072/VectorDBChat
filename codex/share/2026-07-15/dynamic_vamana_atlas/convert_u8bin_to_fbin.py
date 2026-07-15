#!/usr/bin/env python3
"""Audit/normalize official u8bin files and convert values to float32 exactly."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from pathlib import Path

import numpy as np


def sha256_stream(path: Path, offset: int = 0) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        handle.seek(offset)
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def header(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        raw = handle.read(8)
    if len(raw) != 8:
        raise ValueError(f"short u8bin header: {path}")
    return struct.unpack("<II", raw)


def normalize(args: argparse.Namespace) -> None:
    raw_n, raw_d = header(args.input)
    if (raw_n, raw_d) != (args.source_rows, args.dimension):
        raise ValueError(f"raw header {(raw_n, raw_d)} != expected {(args.source_rows, args.dimension)}")
    expected = 8 + args.rows * args.dimension
    if args.input.stat().st_size != expected:
        raise ValueError(f"raw prefix size {args.input.stat().st_size} != expected {expected}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with args.input.open("rb") as source, temporary.open("wb") as destination:
        source.read(8)
        destination.write(struct.pack("<II", args.rows, args.dimension))
        remaining = args.rows * args.dimension
        while remaining:
            chunk = source.read(min(16 * 1024 * 1024, remaining))
            if not chunk:
                raise ValueError("truncated u8bin payload")
            destination.write(chunk)
            remaining -= len(chunk)
    os.replace(temporary, args.output)
    normalized_n, normalized_d = header(args.output)
    if (normalized_n, normalized_d) != (args.rows, args.dimension):
        raise ValueError("normalized u8bin header mismatch")
    raw_payload = sha256_stream(args.input, 8)
    normalized_payload = sha256_stream(args.output, 8)
    if raw_payload != normalized_payload:
        raise ValueError("normalized payload SHA256 differs from raw prefix payload")
    report = {
        "schema": "dynamic-vamana-u8bin-normalization-v1",
        "raw_header": {"n": raw_n, "d": raw_d},
        "normalized_header": {"n": normalized_n, "d": normalized_d},
        "raw_prefix_sha256": sha256_stream(args.input),
        "raw_prefix_payload_sha256": raw_payload,
        "normalized_u8bin_sha256": sha256_stream(args.output),
        "normalized_payload_sha256": normalized_payload,
        "payload_sha256_equal": True,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


def convert(args: argparse.Namespace) -> None:
    n, d = header(args.input)
    if (n, d) != (args.rows, args.dimension):
        raise ValueError(f"u8bin header {(n, d)} != expected {(args.rows, args.dimension)}")
    expected = 8 + n * d
    if args.input.stat().st_size != expected:
        raise ValueError(f"u8bin size {args.input.stat().st_size} != expected {expected}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with args.input.open("rb") as source, temporary.open("wb") as destination:
        source.read(8)
        destination.write(struct.pack("<II", n, d))
        remaining = n
        while remaining:
            take = min(65_536, remaining)
            raw = source.read(take * d)
            if len(raw) != take * d:
                raise ValueError("truncated u8bin payload during conversion")
            np.frombuffer(raw, dtype=np.uint8).astype("<f4", copy=False).tofile(destination)
            remaining -= take
    os.replace(temporary, args.output)
    if args.output.stat().st_size != 8 + n * d * 4:
        raise ValueError("float32 canonical size mismatch")
    report = {
        "schema": "dynamic-vamana-u8bin-to-fbin-v1",
        "input_u8bin_sha256": sha256_stream(args.input),
        "output_fbin_sha256": sha256_stream(args.output),
        "rows": n,
        "dimension": d,
        "conversion": "uint8-value-preserving-to-float32",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    normalized = subparsers.add_parser("normalize")
    normalized.add_argument("--input", type=Path, required=True)
    normalized.add_argument("--output", type=Path, required=True)
    normalized.add_argument("--source-rows", type=int, required=True)
    normalized.add_argument("--rows", type=int, required=True)
    normalized.add_argument("--dimension", type=int, required=True)
    normalized.add_argument("--report", type=Path, required=True)
    converted = subparsers.add_parser("convert")
    converted.add_argument("--input", type=Path, required=True)
    converted.add_argument("--output", type=Path, required=True)
    converted.add_argument("--rows", type=int, required=True)
    converted.add_argument("--dimension", type=int, required=True)
    converted.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if any(value <= 0 for value in (getattr(args, "rows", 0), getattr(args, "dimension", 0))):
        raise ValueError("rows and dimension must be positive")
    if args.action == "normalize":
        if args.source_rows < args.rows:
            raise ValueError("source rows must cover normalized rows")
        normalize(args)
    else:
        convert(args)


if __name__ == "__main__":
    main()
