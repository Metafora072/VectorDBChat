#!/usr/bin/env python3
"""Create paired chronological and globally shuffled PipeANN .bin orders."""

import argparse
import json
import struct
from pathlib import Path

import numpy as np


def metadata(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        return struct.unpack("<ii", handle.read(8))


def write_bin(path: Path, source: np.memmap, order: np.ndarray, dim: int, chunk: int) -> None:
    with path.open("wb") as handle:
        handle.write(struct.pack("<ii", len(order), dim))
        for begin in range(0, len(order), chunk):
            np.asarray(source[order[begin : begin + chunk]], dtype=np.float32).tofile(handle)


def write_tags(path: Path, order: np.ndarray) -> None:
    with path.open("wb") as handle:
        handle.write(struct.pack("<ii", len(order), 1))
        np.asarray(order, dtype=np.uint32).tofile(handle)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--npoints", required=True, type=int)
    parser.add_argument("--seeds", default="11")
    parser.add_argument("--chunk", default=50_000, type=int)
    args = parser.parse_args()

    file_n, dim = metadata(args.input)
    if args.npoints > file_n or args.npoints % 4:
        raise ValueError("npoints must fit the input and divide into four equal cohorts")
    source = np.memmap(args.input, dtype=np.float32, mode="r", offset=8, shape=(file_n, dim))
    args.output_root.mkdir(parents=True, exist_ok=True)
    cohort_size = args.npoints // 4
    manifest = {"input": str(args.input), "npoints": args.npoints, "dim": dim, "cohort_size": cohort_size, "seeds": []}

    for seed in [int(value) for value in args.seeds.split(",") if value]:
        rng = np.random.default_rng(seed)
        chronological_parts = []
        for cohort_id in range(4):
            part = np.arange(cohort_id * cohort_size, (cohort_id + 1) * cohort_size, dtype=np.uint32)
            rng.shuffle(part)
            chronological_parts.append(part)
        chronological = np.concatenate(chronological_parts)
        shuffled = np.arange(args.npoints, dtype=np.uint32)
        np.random.default_rng(seed).shuffle(shuffled)

        for label, order in (("time", chronological), ("shuffle", shuffled)):
            prefix = args.output_root / f"{label}_seed{seed}"
            write_bin(prefix.with_suffix(".bin"), source, order, dim, args.chunk)
            write_tags(prefix.with_suffix(".tags.bin"), order)
            write_tags(prefix.with_suffix(".initial.tags.bin"), order[:cohort_size])
        manifest["seeds"].append(seed)

    (args.output_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
