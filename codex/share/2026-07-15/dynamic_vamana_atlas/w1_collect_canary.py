#!/usr/bin/env python3
"""Fail-closed W1 marker collector with bracketed phase-I/O accounting."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

COMMON = (
    "clone_ready", "index_loaded", "ingest_begin", "ingest_end",
    "publish_begin", "publish_end", "fresh_process_probe_begin",
    "fresh_process_visibility_verified",
)
ODIN = ("online_visibility_probe_begin", "online_visibility_verified")
COUNTERS = ("rbytes", "wbytes", "rios", "wios")


def parse_markers(path: Path, system: str) -> dict[str, tuple[int, dict]]:
    markers: dict[str, tuple[int, dict]] = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        name, stamp = row.get("marker"), row.get("monotonic_ns")
        if not isinstance(name, str) or not isinstance(stamp, int) or name in markers:
            raise ValueError("invalid or duplicate marker")
        markers[name] = (stamp, row)
    required = set(COMMON) | (set(ODIN) if system == "OdinANN" else {"online_visibility_unsupported"})
    if set(markers) != required:
        raise ValueError(f"marker schema mismatch: {set(markers) ^ required}")
    ordered = COMMON[:4] + (ODIN if system == "OdinANN" else ("online_visibility_unsupported",)) + COMMON[4:]
    if [markers[name][0] for name in ordered] != sorted(markers[name][0] for name in ordered):
        raise ValueError("nonmonotonic marker order")
    if system == "DGAI" and markers["online_visibility_unsupported"][1].get("reason") != "requires_final_merge_and_reload":
        raise ValueError("missing DGAI unsupported reason")
    return markers


def snapshots(resources: dict, device: str) -> list[tuple[int, dict]]:
    rows: list[tuple[int, dict]] = []
    for sample in resources.get("samples", []):
        stamp = sample.get("monotonic_ns")
        if not isinstance(stamp, int):
            continue
        for io in sample.get("cgroup_io_stat", []):
            if io.get("device") == device:
                rows.append((stamp, io))
    rows.sort(key=lambda row: row[0])
    if len(rows) < 2:
        raise ValueError("no phase-addressable cgroup I/O samples")
    return rows


def delta(left: dict, right: dict) -> dict[str, int]:
    answer = {key: int(right.get(key, 0)) - int(left.get(key, 0)) for key in COUNTERS}
    if any(value < 0 for value in answer.values()):
        raise ValueError("cgroup I/O counter decreased")
    return answer


def phase(samples: list[tuple[int, dict]], begin: int, end: int, interval_ms: int) -> dict:
    left = next((row for row in reversed(samples) if row[0] <= begin), None)
    right = next((row for row in samples if row[0] >= end), None)
    if left is None or right is None:
        raise ValueError("phase has no bracketing cgroup I/O samples")
    left_ns, left_io = left
    right_ns, right_io = right
    if right_ns <= left_ns:
        raise ValueError("phase boundaries map to the same/nonincreasing sample")
    interval_ns = interval_ms * 1_000_000
    left_skew, right_skew = begin - left_ns, right_ns - end
    meta = {
        "left_sample_ns": left_ns, "begin_marker_ns": begin,
        "end_marker_ns": end, "right_sample_ns": right_ns,
        "left_skew_ns": left_skew, "right_skew_ns": right_skew,
        "sampling_interval_ms": interval_ms,
    }
    if left_skew > 2 * interval_ns or right_skew > 2 * interval_ns:
        raise ValueError(f"phase boundary skew exceeds two sampling periods: {meta}")
    if end - begin < interval_ns:
        return {**meta, "resolution": "not_resolvable_at_sampling_interval"}
    return {**meta, "resolution": "resolved", **delta(left_io, right_io), "wall_seconds": (end - begin) / 1e9}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--system", choices=("DGAI", "OdinANN"), required=True)
    p.add_argument("--markers", type=Path, required=True)
    p.add_argument("--resources", type=Path, required=True)
    p.add_argument("--active-audit", type=Path, required=True)
    p.add_argument("--probe", type=Path, required=True)
    p.add_argument("--logical-payload-bytes", type=int, required=True)
    p.add_argument("--logical-replacements", type=int, default=80000)
    p.add_argument("--index-before-bytes", type=int, required=True)
    p.add_argument("--index-after-bytes", type=int, required=True)
    p.add_argument("--device", default="259:10")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.logical_replacements <= 0 or args.logical_payload_bytes <= 0:
        raise ValueError("logical replacement/payload counts must be positive")

    marker = parse_markers(args.markers, args.system)
    resources = json.loads(args.resources.read_text())
    active = json.loads(args.active_audit.read_text())
    probe = json.loads(args.probe.read_text())
    if resources.get("returncode") != 0 or not active.get("valid") or not probe.get("valid"):
        raise ValueError("failed correctness/resource prerequisite")
    interval_ms = resources.get("sampling_interval_ms")
    if not isinstance(interval_ms, int) or interval_ms <= 0:
        raise ValueError("resources missing sampling_interval_ms")
    io_samples = snapshots(resources, args.device)
    stamp = {name: value[0] for name, value in marker.items()}
    phases = {
        "ingest_device_delta": phase(io_samples, stamp["ingest_begin"], stamp["ingest_end"], interval_ms),
        "publish_device_delta": phase(io_samples, stamp["publish_begin"], stamp["publish_end"], interval_ms),
        "fresh_process_probe_device_delta": phase(io_samples, stamp["fresh_process_probe_begin"], stamp["fresh_process_visibility_verified"], interval_ms),
        "end_to_end_device_delta": phase(io_samples, stamp["ingest_begin"], stamp["fresh_process_visibility_verified"], interval_ms),
    }
    phases["online_probe_device_delta"] = (
        phase(io_samples, stamp["online_visibility_probe_begin"], stamp["online_visibility_verified"], interval_ms)
        if args.system == "OdinANN" else None
    )
    elapsed = lambda name: (stamp[name] - stamp["ingest_begin"]) / 1e9
    report = {
        "schema": "dynamic-vamana-w1-canary-collection-v3",
        "system": args.system, "logical_replacements": args.logical_replacements,
        "markers": stamp, "online_visibility_supported": args.system == "OdinANN",
        "online_visibility_seconds": elapsed("online_visibility_verified") if args.system == "OdinANN" else None,
        "online_visible_throughput_ops_s": args.logical_replacements / elapsed("online_visibility_verified") if args.system == "OdinANN" else None,
        "ingestion_seconds": elapsed("ingest_end"),
        "ingestion_throughput_ops_s": args.logical_replacements / elapsed("ingest_end"),
        "restart_visibility_seconds": elapsed("fresh_process_visibility_verified"),
        "restart_visible_throughput_ops_s": args.logical_replacements / elapsed("fresh_process_visibility_verified"),
        "phase_device_accounting": phases,
        "persistent_index_growth_bytes": args.index_after_bytes - args.index_before_bytes,
        "persistent_growth_per_payload": (args.index_after_bytes - args.index_before_bytes) / args.logical_payload_bytes,
        "active_tag_audit": active, "visibility_probe": probe,
    }
    publish = phases["publish_device_delta"]
    report["publish_write_per_inserted_payload"] = (
        publish["wbytes"] / args.logical_payload_bytes if publish["resolution"] == "resolved" else None
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
