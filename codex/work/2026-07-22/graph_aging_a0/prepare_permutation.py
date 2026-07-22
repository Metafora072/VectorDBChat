#!/usr/bin/env python3
import argparse
import struct
from pathlib import Path

import numpy as np


def read_header(path: Path):
    with path.open("rb") as f:
        return struct.unpack("<II", f.read(8))


def write_bin(path: Path, array: np.ndarray, n: int, dim: int, dtype: np.dtype):
    with path.open("wb") as f:
        f.write(struct.pack("<II", n, dim))
        for start in range(0, n, 8192):
            np.asarray(array[start : start + 8192], dtype=dtype).tofile(f)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output-data", required=True, type=Path)
    p.add_argument("--output-tags", required=True, type=Path)
    p.add_argument("--output-initial-tags", type=Path)
    p.add_argument("--n", required=True, type=int)
    p.add_argument("--seed", required=True, type=int)
    p.add_argument("--initial-n", type=int, default=0)
    args = p.parse_args()

    source_n, dim = read_header(args.input)
    if args.n > source_n:
        raise ValueError(f"requested {args.n} vectors, source has {source_n}")
    src = np.memmap(args.input, mode="r", dtype=np.float32, offset=8, shape=(source_n, dim))
    order = np.random.default_rng(args.seed).permutation(args.n).astype(np.uint32)
    args.output_data.parent.mkdir(parents=True, exist_ok=True)
    args.output_tags.parent.mkdir(parents=True, exist_ok=True)
    with args.output_data.open("wb") as f:
        f.write(struct.pack("<II", args.n, dim))
        for start in range(0, args.n, 8192):
            np.asarray(src[order[start : start + 8192]], dtype=np.float32).tofile(f)
    with args.output_tags.open("wb") as f:
        f.write(struct.pack("<II", args.n, 1))
        order.tofile(f)
    if args.output_initial_tags:
        initial_n = args.initial_n or args.n // 2
        with args.output_initial_tags.open("wb") as f:
            f.write(struct.pack("<II", initial_n, 1))
            order[:initial_n].tofile(f)


if __name__ == "__main__":
    main()
