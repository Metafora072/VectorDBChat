#!/usr/bin/env python3
"""Safely take a prefix from a DiskANN binary truthset.

DiskANN truthsets are laid out as ``header(nq, k), nq*k ids, nq*k distances``.
They are not row-interleaved records, so generic binary-prefix utilities must
never be used for them.
"""

from __future__ import annotations

import argparse
import os
import struct
from pathlib import Path


HEADER = struct.Struct("<II")


def copy_exact(stream_in, stream_out, count: int) -> None:
    remaining = count
    while remaining:
        block = stream_in.read(min(16 * 1024 * 1024, remaining))
        if not block:
            raise ValueError("unexpected end of truthset")
        stream_out.write(block)
        remaining -= len(block)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rows", type=int, required=True)
    args = parser.parse_args()
    if args.rows <= 0:
        raise SystemExit("--rows must be positive")
    with args.input.open("rb") as stream:
        header = stream.read(HEADER.size)
        if len(header) != HEADER.size:
            raise SystemExit("truthset lacks its <nq,k> header")
        query_count, k = HEADER.unpack(header)
        if args.rows > query_count or k == 0:
            raise SystemExit(f"cannot take {args.rows} rows from nq={query_count}, k={k}")
        block_bytes = query_count * k * 4
        expected_size = HEADER.size + 2 * block_bytes
        actual_size = os.fstat(stream.fileno()).st_size
        if actual_size != expected_size:
            raise SystemExit(f"truthset size mismatch: got {actual_size}, expected {expected_size}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("wb") as output:
            output.write(HEADER.pack(args.rows, k))
            copy_exact(stream, output, args.rows * k * 4)  # IDs prefix.
            stream.seek(HEADER.size + block_bytes)
            copy_exact(stream, output, args.rows * k * 4)  # distances prefix.

    expected_output_size = HEADER.size + 2 * args.rows * k * 4
    if args.output.stat().st_size != expected_output_size:
        raise SystemExit("output size mismatch after write")
    with args.output.open("rb") as output:
        out_nq, out_k = HEADER.unpack(output.read(HEADER.size))
    if (out_nq, out_k) != (args.rows, k):
        raise SystemExit("output header verification failed")


if __name__ == "__main__":
    main()
