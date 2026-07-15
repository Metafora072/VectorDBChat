#!/usr/bin/env python3
"""Materialize CP01 vectors and probe vectors after trace validation passes."""
from __future__ import annotations

import argparse, json, os, struct
from pathlib import Path
import numpy as np


def header(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        raw = stream.read(8)
    if len(raw) != 8:
        raise ValueError(f"short header: {path}")
    return struct.unpack("<II", raw)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--work-dir", type=Path, required=True)
    p.add_argument("--authorized", action="store_true")
    a = p.parse_args()
    if not a.authorized:
        raise SystemExit("W1 materialization gate absent")
    full = a.dataset.resolve() / "full_10m.bin"
    work = a.work_dir.resolve()
    for required in (work / "trace_validation.json", work / "active_cp01.tags.bin", work / "visibility_probes.json", full):
        if not required.is_file():
            raise SystemExit(f"missing validated preparation input: {required}")
    validation = json.loads((work / "trace_validation.json").read_text())
    if validation.get("status") not in (None, "pass") and not validation.get("valid", False):
        raise SystemExit("trace validation is not a pass")
    for target in (work / "active_cp01.bin", work / "visibility_probes.bin"):
        if target.exists():
            raise SystemExit(f"refusing materialization overwrite: {target}")
    tag_n, tag_d = header(work / "active_cp01.tags.bin")
    if tag_n != 8_000_000 or tag_d != 1:
        raise SystemExit("invalid CP01 active tags")
    tags = np.memmap(work / "active_cp01.tags.bin", dtype="<u4", mode="r", offset=8, shape=(tag_n,))
    full_n, dim = header(full)
    corpus = np.memmap(full, dtype="<f4", mode="r", offset=8, shape=(full_n, dim))
    if int(tags.max()) >= full_n:
        raise SystemExit("CP01 tag outside full corpus")
    target = work / "active_cp01.bin"
    temporary = target.with_suffix(".bin.tmp")
    with temporary.open("wb") as stream:
        stream.write(struct.pack("<II", tag_n, dim))
        for lo in range(0, tag_n, 16384):
            np.asarray(corpus[tags[lo:lo + 16384]], dtype="<f4").tofile(stream)
    os.replace(temporary, target)
    probes = json.loads((work / "visibility_probes.json").read_text())["probes"]
    probe_tags = np.asarray([row["query_tag"] for row in probes], dtype=np.uint32)
    target = work / "visibility_probes.bin"
    temporary = target.with_suffix(".bin.tmp")
    with temporary.open("wb") as stream:
        stream.write(struct.pack("<II", probe_tags.size, dim))
        np.asarray(corpus[probe_tags], dtype="<f4").tofile(stream)
    os.replace(temporary, target)


if __name__ == "__main__":
    main()
