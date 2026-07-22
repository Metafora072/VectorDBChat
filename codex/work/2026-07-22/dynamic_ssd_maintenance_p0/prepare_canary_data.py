#!/usr/bin/env python3
import argparse
import struct
from pathlib import Path

import numpy as np


def write_bin(path: Path, data: np.ndarray, dim: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as out:
        out.write(struct.pack("<II", len(data), dim))
        for start in range(0, len(data), 8192):
            np.asarray(data[start : start + 8192]).tofile(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--delete-count", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=20260722)
    parser.add_argument("--noise-sigma", type=float, default=0.01)
    args = parser.parse_args()

    with args.source.open("rb") as src:
        n, dim = struct.unpack("<II", src.read(8))
    if n != 1_000_000 or dim != 128:
        raise ValueError(f"expected SIFT1M 1000000x128, got {n}x{dim}")

    base = np.memmap(args.source, mode="r", dtype=np.float32, offset=8, shape=(n, dim))
    rng = np.random.default_rng(args.seed)
    deleted = np.sort(rng.choice(n, size=args.delete_count, replace=False).astype(np.uint32))
    keep = np.ones(n, dtype=bool)
    keep[deleted] = False

    noise = rng.normal(0.0, args.noise_sigma, size=(args.delete_count, dim)).astype(np.float32)
    inserted = np.asarray(base[deleted], dtype=np.float32) + noise
    inserted_tags = np.arange(n, n + args.delete_count, dtype=np.uint32)

    out = args.output_dir
    write_bin(out / "delete_tags_100k.bin", deleted, 1)
    write_bin(out / "churn_inserts_100k.bin", inserted, dim)

    active_path = out / "churn_active_1m.bin"
    with active_path.open("wb") as dst:
        dst.write(struct.pack("<II", n, dim))
        kept_ids = np.flatnonzero(keep)
        for start in range(0, len(kept_ids), 8192):
            np.asarray(base[kept_ids[start : start + 8192]], dtype=np.float32).tofile(dst)
        inserted.tofile(dst)

    active_tags = np.concatenate((np.flatnonzero(keep).astype(np.uint32), inserted_tags))
    write_bin(out / "churn_active_1m.tags.bin", active_tags, 1)

    manifest = out / "manifest.txt"
    manifest.write_text(
        f"source={args.source}\nseed={args.seed}\ndelete_count={args.delete_count}\n"
        f"noise_sigma={args.noise_sigma}\nactive_count={len(active_tags)}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
