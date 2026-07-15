#!/usr/bin/env python3
"""Validate the DiskANN CP00-vs-CP01 stale-static negative control."""
from __future__ import annotations

import argparse, hashlib, json, math, re, struct
from pathlib import Path


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def io_value(sample: dict, device: str) -> int:
    return next((int(row.get("rbytes", 0)) for row in sample.get("cgroup_io_stat", []) if row.get("device") == device), 0)


def recall(log: str) -> float:
    lines = log.splitlines()
    header = next((i for i, line in enumerate(lines) if "Recall@10" in line), None)
    if header is None:
        raise ValueError("missing Recall@10")
    for line in lines[header + 1:]:
        fields = line.split()
        if fields and fields[0].isdigit():
            value = float(fields[-1]) / 100.0
            if math.isfinite(value) and 0 <= value <= 1:
                return value
    raise ValueError("non-finite/unparseable Recall@10")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--result-dir", type=Path, required=True)
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--base-manifest", type=Path, required=True)
    p.add_argument("--query", type=Path, required=True)
    p.add_argument("--gt", type=Path, required=True)
    p.add_argument("--artifact-manifest", type=Path, required=True)
    p.add_argument("--device", default="259:10")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    frozen = json.loads(a.artifact_manifest.read_text())["systems"]["DiskANN"]
    identities = {name: {"realpath": str(path.resolve()), "sha256": sha(path)} for name, path in {
        "query_binary": a.binary, "cp00_index_manifest": a.base_manifest,
        "query": a.query, "cp01_groundtruth": a.gt}.items()}
    if identities["query_binary"]["sha256"] != frozen["binary_sha256"]["search_disk_index"]:
        raise SystemExit("DiskANN binary hash mismatch")
    if identities["cp00_index_manifest"]["sha256"] != frozen["formal_base"]["manifest_sha256"]:
        raise SystemExit("DiskANN CP00 manifest identity mismatch")
    points = []
    query_n, _ = struct.unpack("<II", a.query.open("rb").read(8))
    for l in (29, 53):
        for repetition in (1, 2, 3):
            stem = a.result_dir / f"L{l}_r{repetition}"
            result = Path(f"{stem}_{l}_idx_uint32.bin")
            n, k = struct.unpack("<II", result.open("rb").read(8))
            if (n, k) != (query_n, 10) or result.stat().st_size != 8 + n * k * 4:
                raise SystemExit(f"invalid stale result shape L={l} r={repetition}")
            log = stem.with_suffix(".log").read_text(errors="replace")
            if re.search(r"fatal|assert(?:ion)?|I/O error|input/output error|out of memory|oom|segmentation fault", log, re.I):
                raise SystemExit(f"fatal/I/O/OOM stale query log L={l} r={repetition}")
            resources = json.loads(stem.with_suffix(".resources.json").read_text())
            events = resources.get("cgroup_memory_events_final", {})
            samples = resources.get("samples", [])
            reads = io_value(samples[-1], a.device) - io_value(samples[0], a.device) if samples else 0
            if resources.get("returncode") != 0 or reads <= 0 or any(int(events.get(x, 0)) for x in ("oom", "oom_kill", "oom_group_kill")):
                raise SystemExit(f"invalid stale resource evidence L={l} r={repetition}")
            points.append({"L": l, "Tq": 1, "repetition": repetition, "recall_at_10": recall(log),
                           "nvme_read_bytes": reads, "result_shape": [n, k],
                           "resources": str(stem.with_suffix('.resources.json').resolve())})
    report = {"schema": "dynamic-vamana-w1-stale-control-v1", "status": "pass",
              "classification": "stale-static negative control", "rank_with_update_throughput": False,
              "deleted_cp01_tags_allowed": True, "identities": identities, "points": points}
    a.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
