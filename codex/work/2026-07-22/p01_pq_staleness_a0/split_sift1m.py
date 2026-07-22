#!/usr/bin/env python3
"""Split a DiskANN .bin matrix without loading the payload into RAM."""

from __future__ import annotations

import argparse
import os
import struct


HEADER = struct.Struct("<II")


def copy_exact(src, dst, nbytes: int, block_bytes: int = 16 * 1024 * 1024) -> None:
    remaining = nbytes
    while remaining:
        chunk = src.read(min(block_bytes, remaining))
        if not chunk:
            raise EOFError(f"source ended with {remaining} bytes still expected")
        dst.write(chunk)
        remaining -= len(chunk)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("build_output")
    parser.add_argument("insert_output")
    parser.add_argument("--build-count", type=int, default=700_000)
    args = parser.parse_args()

    with open(args.source, "rb") as src:
        header = src.read(HEADER.size)
        if len(header) != HEADER.size:
            raise ValueError("truncated source header")
        npts, ndim = HEADER.unpack(header)
        if not 0 < args.build_count < npts:
            raise ValueError("build count must be strictly between 0 and npts")
        expected_size = HEADER.size + npts * ndim * 4
        actual_size = os.fstat(src.fileno()).st_size
        if actual_size != expected_size:
            raise ValueError(f"source size {actual_size} != expected {expected_size}")

        insert_count = npts - args.build_count
        with open(args.build_output, "wb") as build:
            build.write(HEADER.pack(args.build_count, ndim))
            copy_exact(src, build, args.build_count * ndim * 4)
        with open(args.insert_output, "wb") as insert:
            insert.write(HEADER.pack(insert_count, ndim))
            copy_exact(src, insert, insert_count * ndim * 4)

        if src.read(1):
            raise ValueError("unexpected trailing byte after exact split")

    for path, count in ((args.build_output, args.build_count), (args.insert_output, insert_count)):
        with open(path, "rb") as result:
            got_count, got_dim = HEADER.unpack(result.read(HEADER.size))
        got_size = os.path.getsize(path)
        want_size = HEADER.size + count * ndim * 4
        if (got_count, got_dim, got_size) != (count, ndim, want_size):
            raise ValueError(f"bad split {path}: {(got_count, got_dim, got_size)}")

    print(f"source={npts}x{ndim} build={args.build_count} insert={insert_count}")


if __name__ == "__main__":
    main()
