#!/usr/bin/env python3
"""Copy a row prefix of an atlas binary while preserving its two-u32 header."""

from __future__ import annotations

import argparse
import os
import struct
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--rows", type=int, required=True)
    args = p.parse_args()
    with args.input.open("rb") as src:
        raw = src.read(8)
        if len(raw) != 8:
            raise ValueError("short input header")
        nrows, width = struct.unpack("<II", raw)
        if not 0 < args.rows <= nrows:
            raise ValueError(f"rows must be in [1, {nrows}]")
        payload = args.input.stat().st_size - 8
        if payload <= 0 or payload % (nrows * width):
            raise ValueError("input payload is not a fixed-width row layout")
        row_bytes = payload // nrows
        args.output.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.output.with_suffix(args.output.suffix + ".tmp")
        with tmp.open("wb") as dst:
            dst.write(struct.pack("<II", args.rows, width))
            remaining = args.rows * row_bytes
            while remaining:
                chunk = src.read(min(16 * 1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("truncated input payload")
                dst.write(chunk)
                remaining -= len(chunk)
        os.replace(tmp, args.output)


if __name__ == "__main__":
    main()
