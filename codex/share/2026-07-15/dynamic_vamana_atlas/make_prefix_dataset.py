#!/usr/bin/env python3
"""Materialize a small prefix dataset/query pair for pre-smoke sanity checks."""

from __future__ import annotations

import argparse
import os
import struct
from pathlib import Path


def copy_prefix(source: Path, output: Path, rows: int) -> None:
    with source.open("rb") as src:
        raw = src.read(8)
        if len(raw) != 8:
            raise ValueError(f"short header: {source}")
        npts, dim = struct.unpack("<II", raw)
        if rows > npts:
            raise ValueError(f"requested {rows} rows from {npts}: {source}")
        remaining = rows * dim * 4
        tmp = output.with_suffix(output.suffix + ".tmp")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("wb") as dst:
            dst.write(struct.pack("<II", rows, dim))
            while remaining:
                chunk = src.read(min(16 * 1024 * 1024, remaining))
                if not chunk:
                    raise ValueError(f"truncated payload: {source}")
                dst.write(chunk)
                remaining -= len(chunk)
        os.replace(tmp, output)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--query", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--base-rows", type=int, default=10_000)
    p.add_argument("--query-rows", type=int, default=100)
    args = p.parse_args()
    copy_prefix(args.base, args.output / "base.bin", args.base_rows)
    copy_prefix(args.query, args.output / "query.bin", args.query_rows)
    with (args.output / "tags.bin").open("wb") as f:
        f.write(struct.pack("<II", args.base_rows, 1))
        for tag in range(args.base_rows):
            f.write(struct.pack("<I", tag))


if __name__ == "__main__":
    main()
