#!/usr/bin/env python3
"""Materialize the canonical 100-op replace-new smoke checkpoint and trace."""

from __future__ import annotations

import argparse
import csv
import json
import os
import struct
from pathlib import Path

import numpy as np


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--count", type=int, default=100)
    args = p.parse_args()

    with (args.dataset / "smoke_replace_new_trace.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))[: args.count]
    if len(rows) != args.count:
        raise ValueError("short smoke trace")
    deletes = np.asarray([int(row["delete_tag"]) for row in rows], dtype="<u4")
    inserts = np.asarray([int(row["insert_tag"]) for row in rows], dtype="<u4")

    trace_path = args.dataset / "smoke_replace_new_trace.bin"
    tmp = trace_path.with_suffix(".bin.tmp")
    with tmp.open("wb") as f:
        f.write(struct.pack("<i", args.count))
        deletes.tofile(f)
        inserts.tofile(f)
    os.replace(tmp, trace_path)

    with (args.dataset / "same_vector_control.csv").open(newline="") as f:
        control_rows = list(csv.DictReader(f))[: args.count]
    if len(control_rows) != args.count:
        raise ValueError("short same-vector control trace")
    control_deletes = np.asarray(
        [int(row["delete_tag"]) for row in control_rows], dtype="<u4"
    )
    control_inserts = np.asarray(
        [int(row["reinsert_tag"]) for row in control_rows], dtype="<u4"
    )
    control_path = args.dataset / "same_vector_control.bin"
    tmp = control_path.with_suffix(".bin.tmp")
    with tmp.open("wb") as f:
        f.write(struct.pack("<i", args.count))
        control_deletes.tofile(f)
        control_inserts.tofile(f)
    os.replace(tmp, control_path)

    initial = np.fromfile(args.dataset / "active_cp00.ids.u32", dtype="<u4")
    active = np.setdiff1d(initial, deletes, assume_unique=True)
    active = np.union1d(active, inserts).astype("<u4", copy=False)
    if active.size != initial.size or np.unique(active).size != initial.size:
        raise ValueError("smoke active-set cardinality/uniqueness failure")

    manifest = json.loads((args.dataset / "manifest.json").read_text())
    full_path = args.dataset / manifest.get("full_file", "full_1m.bin")
    with full_path.open("rb") as f:
        npts, dim = struct.unpack("<II", f.read(8))
    source = np.memmap(
        full_path, dtype="<f4", mode="r", offset=8, shape=(npts, dim)
    )
    data_path = args.dataset / "active_smoke100.bin"
    if not data_path.exists():
        tmp = data_path.with_suffix(".bin.tmp")
        with tmp.open("wb") as f:
            f.write(struct.pack("<II", active.size, dim))
            for start in range(0, active.size, 8192):
                np.asarray(source[active[start : start + 8192]], dtype="<f4", order="C").tofile(f)
        os.replace(tmp, data_path)

    tags_path = args.dataset / "active_smoke100.tags.bin"
    if not tags_path.exists():
        tmp = tags_path.with_suffix(".bin.tmp")
        with tmp.open("wb") as f:
            f.write(struct.pack("<II", active.size, 1))
            active.tofile(f)
        os.replace(tmp, tags_path)
    active.tofile(args.dataset / "active_smoke100.ids.u32")
    print(f"count={args.count} active={active.size} dim={dim} trace={trace_path}")


if __name__ == "__main__":
    main()
