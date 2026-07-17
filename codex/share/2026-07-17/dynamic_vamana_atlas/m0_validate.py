#!/usr/bin/env python3
"""Validate one Write Attribution M0 run and emit its machine summary."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def device_row(sample: dict, device: str) -> dict[str, int]:
    for row in sample.get("cgroup_io_stat", []):
        if row.get("device") == device:
            return {key: int(value) for key, value in row.items() if key != "device"}
    return {}


def marker_times(path: Path) -> dict[str, int]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    result: dict[str, int] = {}
    for row in rows:
        name = row["marker"]
        if name in result:
            raise ValueError(f"duplicate marker: {name}")
        result[name] = int(row["monotonic_ns"])
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", choices=("DGAI", "OdinANN"), required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--build-manifest", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--markers", type=Path, required=True)
    parser.add_argument("--active-audit", type=Path, required=True)
    parser.add_argument("--fresh-probe", type=Path, required=True)
    parser.add_argument("--online-probe", type=Path)
    parser.add_argument("--base-before", type=Path, required=True)
    parser.add_argument("--base-after", type=Path, required=True)
    parser.add_argument("--mode-before", type=Path, required=True)
    parser.add_argument("--mode-after", type=Path, required=True)
    parser.add_argument("--device", default="259:10")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    inputs, build, profile, resources = map(load, (args.input_manifest, args.build_manifest, args.profile, args.resources))
    active, fresh = load(args.active_audit), load(args.fresh_probe)
    online = load(args.online_probe) if args.online_probe else None
    times = marker_times(args.markers)
    required = {"clone_ready", "index_loaded", "ingest_begin", "ingest_end", "publish_begin", "publish_end"}
    if not required.issubset(times):
        raise SystemExit(f"missing required markers: {sorted(required-set(times))}")
    if not (times["clone_ready"] < times["index_loaded"] < times["ingest_begin"] < times["ingest_end"]
            < times["publish_begin"] < times["publish_end"]):
        raise SystemExit("marker ordering mismatch")

    buckets = profile.get("buckets", [])
    update_buckets = [row for row in buckets if row.get("phase") not in ("load", "visibility", "other")]
    total_update = sum(int(row["requested_bytes"]) for row in update_buckets)
    clear_components = {"graph", "vector", "graph_vector_combined", "delete_tombstone", "metadata"}
    clear_phases = {"insert_neighbor_repair", "delete", "metadata", "publish_save"}
    attributed = sum(int(row["requested_bytes"]) for row in update_buckets
                     if row.get("phase") in clear_phases and row.get("component") in clear_components)
    coverage = attributed / total_update if total_update else 0.0
    phase_totals: dict[str, int] = {}
    component_totals: dict[str, int] = {}
    for row in buckets:
        phase_totals[row["phase"]] = phase_totals.get(row["phase"], 0) + int(row["requested_bytes"])
        component_totals[row["component"]] = component_totals.get(row["component"], 0) + int(row["requested_bytes"])

    samples = resources.get("samples", [])
    if len(samples) < 2:
        raise SystemExit("resource sampler has no cgroup interval")
    before, after = device_row(samples[0], args.device), device_row(samples[-1], args.device)
    device_delta = {key: after.get(key, 0) - before.get(key, 0) for key in set(before) | set(after)}
    memory_events = resources.get("cgroup_memory_events_final", {})
    roles = profile.get("logical_rmw_roles", [])
    role_bytes = sum(int(row["requested_bytes"]) for row in roles)
    input_ok = (inputs.get("status") == "pass" and inputs.get("size") == args.size
                and inputs.get("master_record_range") == [800_000, 800_000 + args.size]
                and inputs.get("active_count") == 8_000_000)
    build_row = build["systems"][args.system]
    build_ok = build.get("status") == "pass" and build_row.get("binary_is_independent") is True
    frozen_unchanged = (args.base_before.read_bytes() == args.base_after.read_bytes()
                        and args.mode_before.read_bytes() == args.mode_after.read_bytes())
    correctness = (active.get("valid") is True and active.get("expected_exact_match") is True
                   and fresh.get("valid") is True and (args.system != "OdinANN" or online is not None and online.get("valid") is True))
    device_write = int(device_delta.get("wbytes", 0))
    direction_ok = total_update > 0 and device_write > 0
    no_failure = (resources.get("returncode") == 0 and int(memory_events.get("oom", 0)) == 0
                  and int(memory_events.get("oom_kill", 0)) == 0)
    profile_paths_ok = all(str(row["path"]).startswith(profile["index_root"] + "/") for row in buckets)
    role_ok = role_bytes > 0 and any(row.get("role") == "neighbor_repair" for row in roles)
    passed = all((input_ok, build_ok, frozen_unchanged, correctness, coverage >= 0.90, direction_ok,
                  no_failure, profile_paths_ok, role_ok))

    wall = {
        "load_seconds": (times["index_loaded"] - times["clone_ready"]) / 1e9,
        "ingest_seconds": (times["ingest_end"] - times["ingest_begin"]) / 1e9,
        "publish_seconds": (times["publish_end"] - times["publish_begin"]) / 1e9,
        "end_to_end_seconds": (times["publish_end"] - times["ingest_begin"]) / 1e9,
    }
    if args.system == "OdinANN":
        wall["online_visibility_probe_seconds"] = (
            times["online_visibility_verified"] - times["online_visibility_probe_begin"]) / 1e9

    report = {
        "schema": "dynamic-vamana-write-attribution-m0-run-v1", "status": "pass" if passed else "fail",
        "system": args.system, "size": args.size, "trace_range": [800_000, 800_000 + args.size],
        "instrumented_binary_sha256": build_row["instrumented_sha256"],
        "canonical_binary_sha256": build_row["canonical_sha256"], "wall_time": wall,
        "application_writes": {"total_update_window_bytes": total_update, "attributed_bytes": attributed,
                               "coverage": coverage, "phase_totals": phase_totals,
                               "component_totals": component_totals, "buckets": buckets,
                               "logical_rmw_roles": roles, "logical_rmw_role_bytes": role_bytes},
        "device_delta": device_delta, "peak_rss_kb": resources.get("peak_process_tree_rss_kb"),
        "memory_events": memory_events,
        "correctness": {"active_set_exact": active.get("valid"), "fresh_visibility_query_smoke": fresh.get("valid"),
                        "online_visibility": online.get("valid") if online else "unsupported_by_current_DGAI_path",
                        "frozen_source_unchanged": frozen_unchanged},
        "gates": {"input_exact": input_ok, "independent_binary": build_ok, "correctness": correctness,
                  "coverage_ge_90pct": coverage >= 0.90, "positive_directional_device_write": direction_ok,
                  "no_oom_fatal_index_failure": no_failure, "profile_paths_private_clone_only": profile_paths_ok,
                  "neighbor_role_observed": role_ok},
        "evidence_sha256": {"input_manifest": sha256(args.input_manifest), "profile": sha256(args.profile),
                            "resources": sha256(args.resources), "markers": sha256(args.markers),
                            "active_audit": sha256(args.active_audit), "fresh_probe": sha256(args.fresh_probe)},
    }
    if args.online_probe:
        report["evidence_sha256"]["online_probe"] = sha256(args.online_probe)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if not passed:
        raise SystemExit("M0 run gate failed")


if __name__ == "__main__":
    main()
