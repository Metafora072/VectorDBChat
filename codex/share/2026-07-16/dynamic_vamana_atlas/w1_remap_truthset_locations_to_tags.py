#!/usr/bin/env python3
"""Remap a location-ID truthset to dense external tags without touching distances."""
from __future__ import annotations

import argparse, hashlib, json, os, struct
from pathlib import Path
import numpy as np


def header(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        raw = stream.read(8)
    if len(raw) != 8:
        raise ValueError(f"short header: {path}")
    return struct.unpack("<II", raw)


def block_sha(path: Path, offset: int, length: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(offset)
        remaining = length
        while remaining:
            block = stream.read(min(8 << 20, remaining))
            if not block:
                raise ValueError("short truthset distance block")
            digest.update(block); remaining -= len(block)
    return digest.hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--location-truthset", type=Path, required=True)
    p.add_argument("--active-tags", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--expected-nquery", type=int, required=True)
    p.add_argument("--expected-k", type=int, required=True)
    p.add_argument("--expected-active-count", type=int, required=True)
    a = p.parse_args()
    if a.output.exists() or a.report.exists():
        raise SystemExit("truthset remap output reuse refused")
    nq, k = header(a.location_truthset); nt, td = header(a.active_tags)
    if (nq, k) != (a.expected_nquery, a.expected_k) or (nt, td) != (a.expected_active_count, 1):
        raise SystemExit("unexpected truthset/tag shape")
    if a.location_truthset.stat().st_size != 8 + nq * k * 8 or a.active_tags.stat().st_size != 8 + nt * 4:
        raise SystemExit("truthset/tag size mismatch")
    locations = np.memmap(a.location_truthset, dtype="<u4", mode="r", offset=8, shape=(nq, k))
    distances_offset = 8 + nq * k * 4
    distances = np.memmap(a.location_truthset, dtype="<f4", mode="r", offset=distances_offset, shape=(nq, k))
    tags = np.memmap(a.active_tags, dtype="<u4", mode="r", offset=8, shape=(nt,))
    if int(locations.max()) >= nt:
        raise SystemExit("location ID outside active-vector range")
    if np.any(np.diff(np.sort(np.asarray(locations), axis=1), axis=1) == 0):
        raise SystemExit("duplicate location ID within a truthset row")
    if not np.isfinite(distances).all() or np.any(distances[:, 1:] < distances[:, :-1]):
        raise SystemExit("non-finite or non-monotonic location distances")
    unique_tags = np.unique(tags)
    if unique_tags.size != nt or int(np.count_nonzero(tags == 0)) != 1:
        raise SystemExit("active tags are not globally unique with exactly one tag 0")
    distance_bytes = nq * k * 4
    before = block_sha(a.location_truthset, distances_offset, distance_bytes)
    mapped = np.asarray(tags[locations], dtype="<u4")
    temporary = a.output.with_name(a.output.name + ".tmp")
    try:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("wb") as stream:
            stream.write(struct.pack("<II", nq, k)); mapped.tofile(stream); np.asarray(distances, dtype="<f4").tofile(stream)
        after = block_sha(temporary, distances_offset, distance_bytes)
        if before != after:
            raise ValueError("distance block changed during remap")
        os.replace(temporary, a.output)
    finally:
        temporary.unlink(missing_ok=True)
    report = {"schema": "dynamic-vamana-location-to-tag-truthset-remap-v1", "status": "pass",
              "nquery": nq, "k": k, "active_count": nt, "tag_zero_count": 1,
              "all_locations_in_range": True, "row_locations_unique": True,
              "distances_finite": True, "distances_monotonic": True,
              "distance_block_sha256_before": before, "distance_block_sha256_after": after,
              "distance_block_byte_identical": True, "output": str(a.output.resolve())}
    a.report.parent.mkdir(parents=True, exist_ok=True); a.report.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
