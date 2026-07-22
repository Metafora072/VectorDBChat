#!/usr/bin/env python3
import argparse
import struct
from pathlib import Path


def header(path: Path):
    with path.open("rb") as f:
        return struct.unpack("<II", f.read(8))


def copy_vectors(src_path: Path, dst, n: int, dim: int, item_bytes: int):
    with src_path.open("rb") as src:
        src.seek(8)
        remaining = n * dim * item_bytes
        while remaining:
            block = src.read(min(remaining, 16 << 20))
            if not block:
                raise EOFError(f"short input: {src_path}")
            dst.write(block)
            remaining -= len(block)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True, type=Path)
    p.add_argument("--base-n", required=True, type=int)
    p.add_argument("--extra", required=True, type=Path)
    p.add_argument("--extra-n", required=True, type=int)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--item-bytes", type=int, default=4)
    args = p.parse_args()
    base_total, base_dim = header(args.base)
    extra_total, extra_dim = header(args.extra)
    if base_dim != extra_dim:
        raise ValueError("dimension mismatch")
    if args.base_n > base_total or args.extra_n > extra_total:
        raise ValueError("requested prefix exceeds source")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as dst:
        dst.write(struct.pack("<II", args.base_n + args.extra_n, base_dim))
        copy_vectors(args.base, dst, args.base_n, base_dim, args.item_bytes)
        copy_vectors(args.extra, dst, args.extra_n, base_dim, args.item_bytes)


if __name__ == "__main__":
    main()
