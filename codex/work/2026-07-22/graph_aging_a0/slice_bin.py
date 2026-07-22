#!/usr/bin/env python3
import argparse
import struct
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--n", required=True, type=int)
    p.add_argument("--item-bytes", required=True, type=int)
    args = p.parse_args()
    with args.input.open("rb") as src:
        total, dim = struct.unpack("<II", src.read(8))
        if args.n > total:
            raise ValueError(f"requested {args.n}, source has {total}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("wb") as dst:
            dst.write(struct.pack("<II", args.n, dim))
            remaining = args.n * dim * args.item_bytes
            while remaining:
                block = src.read(min(remaining, 8 << 20))
                if not block:
                    raise EOFError("short input")
                dst.write(block)
                remaining -= len(block)


if __name__ == "__main__":
    main()
