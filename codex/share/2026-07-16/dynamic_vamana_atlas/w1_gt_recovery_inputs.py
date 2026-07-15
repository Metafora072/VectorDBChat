#!/usr/bin/env python3
"""Create deterministic synthetic and targeted query inputs for GT recovery."""
from __future__ import annotations

import argparse, os, struct
from pathlib import Path
import numpy as np


def write(path: Path, values: np.ndarray) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(struct.pack("<II", values.shape[0], values.shape[1] if values.ndim == 2 else 1))
        values.tofile(stream)
    os.replace(temporary, path)


def main() -> None:
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="mode", required=True)
    synthetic = sub.add_parser("synthetic"); synthetic.add_argument("--output-dir", type=Path, required=True)
    targeted = sub.add_parser("targeted"); targeted.add_argument("--query", type=Path, required=True); targeted.add_argument("--qid", type=int, required=True); targeted.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.mode == "synthetic":
        a.output_dir.mkdir(parents=True, exist_ok=False)
        base = np.arange(128 * 4, dtype=np.float32).reshape(128, 4) / 16.0
        query = np.asarray(base[[0]], dtype=np.float32)
        tags = np.arange(1000, 1128, dtype=np.uint32); tags[0] = 0
        write(a.output_dir / "base.bin", base); write(a.output_dir / "query.bin", query); write(a.output_dir / "tags.bin", tags)
    else:
        if a.output.exists(): raise SystemExit("targeted query output reuse refused")
        n, d = struct.unpack("<II", a.query.open("rb").read(8))
        if not 0 <= a.qid < n: raise SystemExit("target qid outside query set")
        source = np.memmap(a.query, dtype="<f4", mode="r", offset=8, shape=(n, d))
        a.output.parent.mkdir(parents=True, exist_ok=True); write(a.output, np.asarray(source[[a.qid]], dtype=np.float32))


if __name__ == "__main__": main()
