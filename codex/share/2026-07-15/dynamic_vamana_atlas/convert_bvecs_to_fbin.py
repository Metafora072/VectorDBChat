#!/usr/bin/env python3
"""Convert a fixed-width BIGANN .bvecs prefix to DiskANN float .bin format."""

from __future__ import annotations

import argparse
import os
import struct
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--dimension", type=int, default=128)
    parser.add_argument("--chunk-rows", type=int, default=65_536)
    args = parser.parse_args()
    if args.rows <= 0 or args.dimension <= 0 or args.chunk_rows <= 0:
        raise ValueError("rows, dimension, and chunk-rows must be positive")

    record_bytes = 4 + args.dimension
    required = args.rows * record_bytes
    if args.input.stat().st_size < required:
        raise ValueError(
            f"short bvecs source: need at least {required} bytes for {args.rows} rows"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with args.input.open("rb") as source, temporary.open("wb") as destination:
        destination.write(struct.pack("<II", args.rows, args.dimension))
        remaining = args.rows
        while remaining:
            take = min(remaining, args.chunk_rows)
            raw = source.read(take * record_bytes)
            if len(raw) != take * record_bytes:
                raise ValueError("truncated bvecs record")
            records = np.frombuffer(raw, dtype=np.uint8).reshape(take, record_bytes)
            dimensions = np.frombuffer(records[:, :4].copy().tobytes(), dtype="<i4")
            if not np.all(dimensions == args.dimension):
                raise ValueError("bvecs dimension field differs from requested dimension")
            np.asarray(records[:, 4:], dtype="<f4", order="C").tofile(destination)
            remaining -= take
    os.replace(temporary, args.output)


if __name__ == "__main__":
    main()
