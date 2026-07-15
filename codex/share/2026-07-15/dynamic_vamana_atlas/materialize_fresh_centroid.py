#!/usr/bin/env python3
"""Materialize FreshDiskANN medoid sidecars to avoid its unstable fallback read."""

from __future__ import annotations

import argparse
import os
import struct
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--index-prefix", type=Path, required=True)
    args = p.parse_args()

    disk_index = Path(str(args.index_prefix) + "_disk.index")
    with disk_index.open("rb") as f:
        nmeta, meta_dim = struct.unpack("<II", f.read(8))
        if (nmeta, meta_dim) != (9, 1):
            raise ValueError(f"unexpected index metadata header: {(nmeta, meta_dim)}")
        metadata = struct.unpack("<9Q", f.read(9 * 8))
    npts, dim, medoid = metadata[:3]

    with args.base.open("rb") as f:
        base_npts, base_dim = struct.unpack("<II", f.read(8))
        if (base_npts, base_dim) != (npts, dim):
            raise ValueError(
                f"base/index mismatch: base={(base_npts, base_dim)}, index={(npts, dim)}"
            )
        f.seek(8 + medoid * dim * 4)
        vector = f.read(dim * 4)
        if len(vector) != dim * 4:
            raise ValueError("truncated medoid vector")

    outputs = [
        (Path(str(disk_index) + "_medoids.bin"), struct.pack("<III", 1, 1, medoid)),
        (Path(str(disk_index) + "_centroids.bin"), struct.pack("<II", 1, dim) + vector),
    ]
    for output, payload in outputs:
        tmp = output.with_suffix(output.suffix + ".tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, output)
    print(f"npts={npts} dim={dim} medoid={medoid}")


if __name__ == "__main__":
    main()
