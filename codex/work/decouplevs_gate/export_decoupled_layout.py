#!/usr/bin/env python3
"""Export one static PipeANN index into page-aligned graph/vector files.

The exporter is deliberately narrow: float vectors, identity id/location mapping,
no attributes, and one 4 KiB metadata page.  It validates identity tags and a
sample of coordinates before producing the reproduction input.
"""

from __future__ import annotations

import argparse
import mmap
import os
import random
import struct
from pathlib import Path


PAGE = 4096
HEADER = struct.Struct("<8s7Q")


def read_meta(mm: mmap.mmap) -> dict[str, int]:
    nr, nc = struct.unpack_from("<2I", mm, 0)
    vals = struct.unpack_from("<9Q", mm, 8)
    if (nr, nc) != (9, 1):
        raise ValueError(f"unsupported metadata shape {(nr, nc)}")
    keys = ("npoints", "dim", "entry", "node_len", "nodes_per_page",
            "npts_shard", "attr_size", "range", "r_ood")
    return dict(zip(keys, vals))


def coupled_node(mm: mmap.mmap, meta: dict[str, int], node_id: int) -> memoryview:
    npp = meta["nodes_per_page"]
    page = 1 + node_id // npp
    within = (node_id % npp) * meta["node_len"]
    start = page * PAGE + within
    return memoryview(mm)[start : start + meta["node_len"]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--tags", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--graph-out", required=True)
    ap.add_argument("--vector-out", required=True)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    index = Path(args.index)
    tags = Path(args.tags)
    base = Path(args.base)
    graph_out = Path(args.graph_out)
    vector_out = Path(args.vector_out)
    graph_out.parent.mkdir(parents=True, exist_ok=True)
    vector_out.parent.mkdir(parents=True, exist_ok=True)

    with index.open("rb") as fi, tags.open("rb") as ft, base.open("rb") as fb:
        im = mmap.mmap(fi.fileno(), 0, access=mmap.ACCESS_READ)
        tm = mmap.mmap(ft.fileno(), 0, access=mmap.ACCESS_READ)
        bm = mmap.mmap(fb.fileno(), 0, access=mmap.ACCESS_READ)
        meta = read_meta(im)
        n, dim, degree = meta["npoints"], meta["dim"], meta["range"]
        if meta["attr_size"] != 0:
            raise ValueError("attributes are not supported")
        if struct.unpack_from("<2I", tm, 0) != (n, 1):
            raise ValueError("tag header mismatch")
        if struct.unpack_from("<2I", bm, 0) != (n, dim):
            raise ValueError("base header mismatch")
        for i in range(n):
            if struct.unpack_from("<I", tm, 8 + 4 * i)[0] != i:
                raise ValueError(f"non-identity tag at {i}")

        rng = random.Random(args.seed)
        samples = {0, n - 1, meta["entry"]}
        samples.update(rng.randrange(n) for _ in range(97))
        coord_bytes = dim * 4
        for node_id in samples:
            node = coupled_node(im, meta, node_id)
            expected = bm[8 + node_id * coord_bytes : 8 + (node_id + 1) * coord_bytes]
            if node[:coord_bytes] != expected:
                raise ValueError(f"coordinate mismatch at id={node_id}")

        graph_rec = 4 + degree * 4
        graph_npp = PAGE // graph_rec
        vector_rec = coord_bytes
        vector_npp = PAGE // vector_rec
        if graph_npp == 0 or vector_npp == 0:
            raise ValueError("record exceeds one page")
        graph_pages = (n + graph_npp - 1) // graph_npp
        vector_pages = (n + vector_npp - 1) // vector_npp

        with graph_out.open("wb+") as go, vector_out.open("wb+") as vo:
            os.posix_fallocate(go.fileno(), 0, (1 + graph_pages) * PAGE)
            os.posix_fallocate(vo.fileno(), 0, (1 + vector_pages) * PAGE)
            gh = bytearray(PAGE)
            vh = bytearray(PAGE)
            HEADER.pack_into(gh, 0, b"DCSRGR01", n, dim, degree, meta["entry"], graph_rec, graph_npp, PAGE)
            HEADER.pack_into(vh, 0, b"DCSRVE01", n, dim, degree, meta["entry"], vector_rec, vector_npp, PAGE)
            os.pwrite(go.fileno(), gh, 0)
            os.pwrite(vo.fileno(), vh, 0)

            for page_id in range(graph_pages):
                page = bytearray(PAGE)
                lo = page_id * graph_npp
                hi = min(n, lo + graph_npp)
                for node_id in range(lo, hi):
                    node = coupled_node(im, meta, node_id)
                    nnbrs = struct.unpack_from("<H", node, coord_bytes)[0]
                    if nnbrs > degree:
                        raise ValueError(f"degree overflow id={node_id}: {nnbrs}>{degree}")
                    dst = (node_id - lo) * graph_rec
                    struct.pack_into("<I", page, dst, nnbrs)
                    page[dst + 4 : dst + 4 + nnbrs * 4] = node[coord_bytes + 4 : coord_bytes + 4 + nnbrs * 4]
                os.pwrite(go.fileno(), page, (1 + page_id) * PAGE)

            for page_id in range(vector_pages):
                page = bytearray(PAGE)
                lo = page_id * vector_npp
                hi = min(n, lo + vector_npp)
                for node_id in range(lo, hi):
                    node = coupled_node(im, meta, node_id)
                    dst = (node_id - lo) * vector_rec
                    page[dst : dst + vector_rec] = node[:vector_rec]
                os.pwrite(vo.fileno(), page, (1 + page_id) * PAGE)

        print({
            "npoints": n,
            "dim": dim,
            "degree": degree,
            "entry": meta["entry"],
            "graph_record_bytes": graph_rec,
            "graph_nodes_per_page": graph_npp,
            "graph_bytes": graph_out.stat().st_size,
            "vector_record_bytes": vector_rec,
            "vector_nodes_per_page": vector_npp,
            "vector_bytes": vector_out.stat().st_size,
            "coordinate_samples_verified": len(samples),
        })


if __name__ == "__main__":
    main()
