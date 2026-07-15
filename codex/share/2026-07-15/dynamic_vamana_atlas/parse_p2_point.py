#!/usr/bin/env python3
"""Normalize one P2 native-driver query log plus its external timing envelope."""

from __future__ import annotations

import argparse
import json
import math
import re
import hashlib
from pathlib import Path


FATAL = re.compile(
    r"bad file descriptor|\bfailed\b|i/o error|io_uring.*failed|fatal|abort|"
    r"assert(?:ion)? failure|segmentation fault|core dumped",
    re.I,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def metric_row(system: str, log: Path) -> dict[str, float]:
    lines = log.read_text(errors="replace").splitlines()
    header = next((i for i, line in enumerate(lines) if "Recall@10" in line), None)
    if header is None:
        raise ValueError("missing Recall@10 header")
    for line in lines[header + 1 :]:
        f = line.split()
        if not f or not f[0].isdigit():
            continue
        if system == "DiskANN" and len(f) >= 9:
            return {"L": float(f[0]), "driver_qps": float(f[2]), "mean_latency_us": float(f[3]),
                    "p999_latency_us": float(f[4]), "mean_ios": float(f[5]), "mean_io_us": float(f[6]),
                    "recall_at_10": float(f[8]) / 100.0}
        if system == "DGAI" and len(f) >= 10:
            return {"L": float(f[0]), "driver_qps": float(f[2]), "mean_latency_us": float(f[3]),
                    "p99_latency_us": float(f[4]), "mean_ios": float(f[6]), "mean_io_us": float(f[8]),
                    "recall_at_10": float(f[9]) / 100.0}
        if system == "OdinANN" and len(f) >= 8:
            return {"L": float(f[0]), "driver_qps": float(f[2]), "mean_latency_us": float(f[3]),
                    "p99_latency_us": float(f[4]), "mean_ios": float(f[6]), "recall_at_10": float(f[7]) / 100.0}
    raise ValueError(f"no parseable {system} metric row")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--system", required=True, choices=["DiskANN", "DGAI", "OdinANN"])
    p.add_argument("--query-threads", type=int, required=True)
    p.add_argument("--L", type=int, required=True)
    p.add_argument("--repeat", type=int, required=True)
    p.add_argument("--log", type=Path, required=True)
    p.add_argument("--timing", type=Path, required=True)
    p.add_argument("--resources", type=Path, required=True)
    p.add_argument("--query-file", type=Path)
    p.add_argument("--gt-file", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    timing = json.loads(args.timing.read_text())
    resources = json.loads(args.resources.read_text())
    row = metric_row(args.system, args.log)
    samples = resources.get("samples", [])
    first = samples[0] if samples else {}
    last = samples[-1] if samples else {}
    device_read_bytes_delta = sum(
        max(0, int(b.get("rbytes", 0)) - int(a.get("rbytes", 0)))
        for a, b in zip(first.get("cgroup_io_stat", []), last.get("cgroup_io_stat", []))
        if a.get("device") == b.get("device"))
    events = resources.get("cgroup_memory_events_final", {})
    reasons: list[str] = []
    if timing["returncode"] != 0:
        reasons.append(f"driver_returncode={timing['returncode']}")
    if FATAL.search(args.log.read_text(errors="replace")):
        reasons.append("fatal_log_marker")
    if not math.isfinite(row["recall_at_10"]) or not 0.0 <= row["recall_at_10"] <= 1.0:
        reasons.append("invalid_recall")
    if int(events.get("oom", 0)) or int(events.get("oom_kill", 0)):
        reasons.append("cgroup_oom")
    if device_read_bytes_delta <= 0:
        reasons.append("no_nvme_read_bytes")
    identity = {}
    for label, path in (("query", args.query_file), ("groundtruth", args.gt_file)):
        if path is None or not path.is_file():
            reasons.append(f"missing_{label}_identity")
        else:
            identity[label] = {"path": str(path.resolve()), "sha256": sha256(path)}
    row.update({
        "schema": "dynamic-vamana-p2-point-v1",
        "system": args.system,
        "query_threads": args.query_threads,
        "L": args.L,
        "repeat": args.repeat,
        "query_count": timing["query_count"],
        "process_wall_seconds": timing["process_wall_seconds"],
        "index_load_seconds": timing["index_load_seconds"],
        "warmup_seconds": timing["warmup_seconds"],
        "timed_search_envelope_seconds": timing["timed_search_envelope_seconds"],
        "external_qps": timing["externally_computed_qps"],
        "driver_reported_qps": timing["driver_reported_qps"],
        "peak_process_tree_rss_kb": resources.get("peak_process_tree_rss_kb"),
        "cgroup_memory_peak": max((s.get("cgroup_memory_peak") or 0 for s in samples), default=0),
        "cgroup_memory_events": events,
        "device_read_bytes_delta": device_read_bytes_delta,
        "returncode": timing["returncode"],
        "validation_level": "aggregate-only validation" if args.system != "DiskANN" else "active-id validation",
        "valid": not reasons,
        "invalid_reason": ";".join(reasons) if reasons else None,
        "input_identity": identity,
    })
    args.output.write_text(json.dumps(row, indent=2) + "\n")


if __name__ == "__main__":
    main()
