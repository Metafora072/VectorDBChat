#!/usr/bin/env python3
"""Run exactly one preregistered Z0B endpoint and its compact audits.

Do not invoke this directly.  ``run_endpoints.py`` holds the campaign lock and
sets both acknowledgements.  Every output is exclusive and every exception is
terminal for the attempt.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from endpoint_common import (
    ATLAS,
    BUILD,
    DATASET,
    M0_PROFILER,
    REGISTERED_PEAK_BYTES,
    RUN_ROOT,
    SHARE,
    allocated_bytes,
    atomic_json,
    load_json,
    locked_tool,
    schedule,
    sha256,
    timestamp_pair,
    tool_command,
)


FULL_ACK = "I_ACKNOWLEDGE_ONE_FROZEN_Z0B_FULL_TRACE"
OLD = Path("/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas")
LIBS = ":".join([
    str(BUILD / "trace"),
    str(M0_PROFILER.parent),
    str(ATLAS / "build/gperftools-install/lib"),
    str(ATLAS / "build/openblas-install/lib"),
    str(ATLAS / "build/jemalloc-install/lib"),
])


def run_logged(command: list[str], log: Path, environment: dict[str, str] | None = None) -> None:
    with log.open("ab", buffering=0) as handle:
        subprocess.run(command, check=True, env=environment, stdout=handle, stderr=subprocess.STDOUT)


def marker(result: Path, name: str, stage: str) -> None:
    (result / name).touch(exist_ok=False)
    atomic_json(result / "stage_status.json", {
        "schema": "zns-ann-z0b-stage-status-v1",
        "status": "pass",
        "stage": stage,
        "timestamps": timestamp_pair(),
    })


def space_checkpoint(result: Path, stage: str) -> None:
    used = allocated_bytes(RUN_ROOT)
    stat = os.statvfs(RUN_ROOT)
    free = stat.f_bavail * stat.f_frsize
    row = {
        "schema": "zns-ann-z0b-space-checkpoint-v1",
        "stage": stage,
        "timestamps": timestamp_pair(),
        "campaign_allocated_bytes": used,
        "registered_peak_bytes": REGISTERED_PEAK_BYTES,
        "nvme_free_bytes": free,
        "within_registered_peak": used <= REGISTERED_PEAK_BYTES,
    }
    with (result / "space_checkpoints.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    if used > REGISTERED_PEAK_BYTES:
        raise RuntimeError(f"campaign exceeded registered 129 GiB peak at {stage}: {used}")


def validate_capture(result: Path, expected_capacity: int) -> None:
    required = [
        "raw_trace.bin", "trace_meta.json", "trace_ledger.json", "ordered_lifecycle.jsonl",
        "markers.jsonl", "app_write_profile_v5.json", "write_lifecycle.json",
    ]
    for name in required:
        path = result / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"capture evidence absent: {path}")
    meta = load_json(result / "trace_meta.json")
    if not (
        meta.get("status") == "complete"
        and int(meta.get("capacity", -1)) == expected_capacity
        and int(meta.get("dropped_events", -1)) == 0
        and int(meta.get("lifecycle_dropped_events", -1)) == 0
        and int(meta.get("identity_errors", -1)) == 0
    ):
        raise RuntimeError("trace meta drop/capacity/identity closure failed")
    ledger = load_json(result / "trace_ledger.json")
    if ledger.get("status") != "complete":
        raise RuntimeError("trace ledger is incomplete")
    profile = load_json(result / "app_write_profile_v5.json")
    profile_totals = profile.get("ledger_totals", {})
    profile_requests = sum(int(row.get("request_count", 0)) for row in profile_totals.values())
    profile_bytes = sum(int(row.get("requested_bytes", 0)) for row in profile_totals.values())
    if not (
        profile.get("schema") == "dynamic-vamana-write-attribution-m0-v5"
        and profile_requests == int(ledger.get("accepted_requests", -1))
        and profile_bytes == int(ledger.get("requested_bytes", -1))
    ):
        raise RuntimeError("M0 profiler versus Z0B tracer ledger closure failed")


def placements() -> list[tuple[str, int, str]]:
    return [
        ("canonical", 0, "canonical"),
        ("role", 0, "role"),
        ("random", 2026071901, "random-2026071901"),
        ("random", 2026071902, "random-2026071902"),
        ("random", 2026071903, "random-2026071903"),
        ("oracle", 0, "oracle"),
    ]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} PREREGISTERED_LABEL")
    if os.environ.get("Z0B_GLOBAL_LOCK_HELD") != "1" or os.environ.get("Z0B_FULL_TRACE_AUTHORIZED") != FULL_ACK:
        raise SystemExit("global lock/full-trace authorization absent")
    if os.geteuid() != 0:
        raise SystemExit("formal endpoint runner must execute as root")

    labels = {str(row["label"]): row for row in schedule()}
    label = sys.argv[1]
    if label not in labels:
        raise SystemExit(f"label is not preregistered: {label}")
    row = labels[label]
    system = str(row["system"])
    size = int(row["input_size"])
    capacity = int(row["trace_capacity"])
    work = RUN_ROOT / "work" / label
    result = RUN_ROOT / "results" / label
    index = work / "index"
    prefix = index / "index"
    input_root = Path(str(row["input_root"]))
    if not (RUN_ROOT / "PREPARED_OK").is_file() or not (work / "PREPARED_OK").is_file() or not index.is_dir():
        raise SystemExit(f"attempt is not prepared: {label}")
    if (result / "RUN_STARTED").exists() or (result / "FAILED.json").exists():
        raise SystemExit(f"attempt reuse/retry is forbidden: {label}")

    gate = subprocess.run([
        sys.executable, str(SHARE / "prelaunch_gate.py"), "--mode", "run", "--require-launch-ready"
    ])
    if gate.returncode:
        raise SystemExit(gate.returncode)

    (result / "RUN_STARTED").touch(exist_ok=False)
    atomic_json(result / "run_status.json", {
        "schema": "zns-ann-z0b-run-status-v1",
        "status": "running",
        "stage": "capture",
        "timestamps": timestamp_pair(),
        "label": label,
        "system": system,
        "input_size": size,
        "run_uuid": row["run_uuid"],
        "frozen_build": str(BUILD),
    }, exclusive=True)

    try:
        space_checkpoint(result, "before_capture")
        binary = BUILD / "systems" / system / "w1_canary"
        tracer = BUILD / "trace/libz0btrace.so"
        raw = result / "raw_trace.bin"
        meta = result / "trace_meta.json"
        ledger = result / "trace_ledger.json"
        lifecycle = result / "ordered_lifecycle.jsonl"
        markers = result / "markers.jsonl"
        profile = result / "app_write_profile_v5.json"
        logical = result / "neighbor_repair_logical.json"
        write_lifecycle = result / "write_lifecycle.json"
        online = result / "online.bin"
        runtime = [
            "PATH=/usr/bin:/bin", "LANG=C", "LC_ALL=C", "HOME=/home/ubuntu",
            "OPENBLAS_NUM_THREADS=8", "OMP_NUM_THREADS=8", f"LD_LIBRARY_PATH={LIBS}",
            f"LD_PRELOAD={tracer}:{M0_PROFILER}", "ATLAS_Z0A_MODE=full-trace",
            f"ATLAS_Z0A_TRACE_OUTPUT={raw}", f"ATLAS_Z0A_META_OUTPUT={meta}",
            f"ATLAS_Z0A_LEDGER_OUTPUT={ledger}", f"ATLAS_Z0A_LIFECYCLE_OUTPUT={lifecycle}",
            f"ATLAS_Z0A_INDEX_ROOT={index}", f"ATLAS_Z0A_SYSTEM={system}",
            f"ATLAS_Z0A_RUN_ID={row['run_uuid']}", f"ATLAS_Z0A_OBJECT_MAP={result / 'object_registry.tsv'}",
            f"ATLAS_Z0A_TRACE_CAPACITY={capacity}", f"ATLAS_W1_MARKERS={markers}",
            f"ATLAS_M0_INDEX_ROOT={index}", f"ATLAS_M0_PROFILE_OUTPUT={profile}",
            f"ATLAS_M2_LOGICAL_OUTPUT={logical}", f"ATLAS_M3_LIFECYCLE_OUTPUT={write_lifecycle}",
        ]
        driver = [str(binary), "run", str(DATASET), str(prefix), str(input_root / "trace.bin")]
        if system == "OdinANN":
            driver.extend([str(input_root / "probes.bin"), str(online)])
        unit = f"dv-z0b-r05-{label}"
        command = [
            "systemd-run", "--wait", "--collect", "--pipe", "--unit", unit, "--uid", "ubuntu",
            "--property=Type=exec", "--property=AllowedCPUs=0-23", "--property=CPUAccounting=yes",
            "--property=MemoryAccounting=yes", "--property=IOAccounting=yes", "--property=MemoryMax=40G",
            "--property=LimitCORE=0", "--property=RuntimeMaxSec=10800",
            "/usr/bin/time", "-v", "-o", str(result / "time.txt"), "env", "-i", *runtime,
            "/usr/bin/numactl", "--physcpubind=0-23", "--membind=0", *driver,
        ]
        started = time.monotonic_ns()
        run_logged(command, result / "controller.log")
        ended = time.monotonic_ns()
        atomic_json(result / "capture_timing.json", {
            "schema": "zns-ann-z0b-capture-timing-v1",
            "timestamps": timestamp_pair(),
            "monotonic_elapsed_seconds": (ended - started) / 1e9,
            "operational_timing_only_not_replay_input": True,
        }, exclusive=True)
        validate_capture(result, capacity)
        run_logged([
            sys.executable, str(OLD / "w1_dump_active_tags.py"),
            "--tags", str(prefix) + "_disk.index.tags",
            "--expected", str(input_root / "expected_active.tags.bin"),
            "--expected-count", "8000000", "--output", str(result / "active_audit.json"),
        ], result / "controller.log")
        probe_environment = {
            "PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "HOME": "/home/ubuntu",
            "LD_LIBRARY_PATH": LIBS, "OPENBLAS_NUM_THREADS": "8", "OMP_NUM_THREADS": "8",
        }
        run_logged([
            "/usr/bin/numactl", "--physcpubind=0-23", "--membind=0", str(binary), "probe",
            str(prefix), str(input_root / "probes.bin"), str(result / "fresh.bin"),
        ], result / "controller.log", probe_environment)
        run_logged([
            sys.executable, str(OLD / "w1_visibility_probe.py"),
            "--probes", str(input_root / "probes.json"), "--result-tags", str(result / "fresh.bin"),
            "--active-tags", str(input_root / "expected_active.tags.bin"),
            "--output", str(result / "fresh_probe.json"),
        ], result / "controller.log")
        semantic = [load_json(result / "active_audit.json"), load_json(result / "fresh_probe.json")]
        if system == "OdinANN":
            run_logged([
                sys.executable, str(OLD / "w1_visibility_probe.py"),
                "--probes", str(input_root / "probes.json"), "--result-tags", str(online),
                "--active-tags", str(input_root / "expected_active.tags.bin"),
                "--output", str(result / "online_probe.json"),
            ], result / "controller.log")
            semantic.append(load_json(result / "online_probe.json"))
        if not all(document.get("valid") is True for document in semantic):
            raise RuntimeError("active-set/fresh/online semantic closure failed")
        marker(result, "CAPTURE_OK", "capture_complete")
        space_checkpoint(result, "capture_complete")

        normalizer = locked_tool("stream_normalize")
        run_logged(tool_command(normalizer) + [
            "--raw", str(raw), "--lifecycle", str(lifecycle),
            "--output", str(result / "normalized.bin"),
            "--summary", str(result / "normalization_summary.json"),
            "--accepted-profile", str(ledger),
        ], result / "controller.log")
        norm_summary = load_json(result / "normalization_summary.json")
        if norm_summary.get("status") != "pass" or norm_summary.get("temporal_fields_emitted") is not False:
            raise RuntimeError("sequence-only normalization failed")
        marker(result, "NORMALIZED_OK", "normalized")
        space_checkpoint(result, "normalized")

        compact_lifecycle = locked_tool("compact_lifecycle")
        run_logged(tool_command(compact_lifecycle) + [
            "--ordered-lifecycle", str(lifecycle),
            "--output", str(result / "lifecycle.bin"),
            "--summary", str(result / "lifecycle_summary.json"),
        ], result / "controller.log")
        life_summary = load_json(result / "lifecycle_summary.json")
        if life_summary.get("status") != "pass":
            raise RuntimeError("compact lifecycle closure failed")

        compactor = locked_tool("compact_extent_manifest")
        (result / "compact_tmp").mkdir(mode=0o700)
        run_logged(tool_command(compactor) + [
            "close", "--initial-map", str(result / "initial_extents.bin"),
            "--initial-summary", str(result / "initial_extents_summary.json"),
            "--normalized", str(result / "normalized.bin"),
            "--lifecycle", str(lifecycle), "--trace-meta", str(meta),
            "--final-root", str(index), "--output", str(result / "final_extents.bin"),
            "--summary", str(result / "closure.json"), "--temp-dir", str(result / "compact_tmp"),
        ], result / "controller.log")
        closure = load_json(result / "closure.json")
        if closure.get("status") != "pass":
            raise RuntimeError("endpoint extent/hash/size closure failed")
        marker(result, "CLOSURE_OK", "endpoint_closed")
        space_checkpoint(result, "endpoint_closed")

        converter = locked_tool("initial_replay_view")
        run_logged(tool_command(converter) + [
            "--authoritative", str(result / "initial_extents.bin"),
            "--initial-json", str(result / "initial_extents_summary.json"),
            "--output", str(result / "initial_replay_view.bin"),
            "--summary", str(result / "initial_replay_view.json"),
        ], result / "controller.log")
        view = load_json(result / "initial_replay_view.json")
        if view.get("status") != "pass":
            raise RuntimeError("initial authoritative-to-replay-view closure failed")

        replay = locked_tool("native_replay")
        reference = locked_tool("native_reference")
        compare = locked_tool("compare_native_results")
        replay_dir = result / "replay"
        reference_dir = result / "reference"
        comparison_dir = result / "comparison"
        replay_dir.mkdir(mode=0o700)
        reference_dir.mkdir(mode=0o700)
        comparison_dir.mkdir(mode=0o700)
        common = [
            "--initial", str(result / "initial_replay_view.bin"),
            "--normalized", str(result / "normalized.bin"),
            "--lifecycle", str(result / "lifecycle.bin"),
        ]
        replay_outputs: dict[str, object] = {}
        for blocks in (65536, 262144):
            for spares in (2, 8):
                for placement, seed, placement_id in placements():
                    for cleaner in ("greedy", "oracle"):
                        config = f"z{blocks}-h{spares}-{placement_id}-{cleaner}"
                        parameters = [
                            *common, "--capacity-blocks", str(blocks), "--host-spares", str(spares),
                            "--placement", placement, "--random-seed", str(seed), "--cleaner", cleaner,
                        ]
                        replay_output = replay_dir / f"{config}.json"
                        reference_output = reference_dir / f"{config}.json"
                        comparison_output = comparison_dir / f"{config}.json"
                        run_logged(tool_command(replay) + parameters + ["--output", str(replay_output)], result / "controller.log")
                        run_logged(tool_command(reference) + parameters + ["--output", str(reference_output)], result / "controller.log")
                        run_logged(tool_command(compare) + [
                            "--main", str(replay_output), "--reference", str(reference_output),
                            "--output", str(comparison_output),
                        ], result / "controller.log")
                        comparison = load_json(comparison_output)
                        if comparison.get("status") != "pass" or comparison.get("primary_equals_reference") is not True:
                            raise RuntimeError(f"native replay/reference mismatch: {config}")
                        replay_outputs[config] = {
                            "main_sha256": sha256(replay_output),
                            "reference_sha256": sha256(reference_output),
                            "comparison_sha256": sha256(comparison_output),
                        }
        if len(replay_outputs) != 48:
            raise RuntimeError("replay matrix is not exactly 48 configurations")
        atomic_json(result / "matrix_crosscheck.json", {
            "schema": "zns-ann-z0b-matrix-crosscheck-v1",
            "status": "pass",
            "sequence_only": True,
            "temporal_fields_used": False,
            "configuration_count": 48,
            "exact_replay_reference_match": True,
            "results": replay_outputs,
        }, exclusive=True)
        marker(result, "REPLAY_OK", "native_replay")
        marker(result, "REFERENCE_OK", "independent_reference")
        space_checkpoint(result, "native_matrix_complete")

        marker(result, "Z0B_RUN_OK", "complete")
        atomic_json(result / "final_status.json", {
            "schema": "zns-ann-z0b-run-final-v1",
            "status": "pass",
            "timestamps": timestamp_pair(),
            "label": label,
            "system": system,
            "input_size": size,
            "frozen_runtime_sha256": {
                "binary": sha256(binary),
                "tracer": sha256(tracer),
            },
            "configuration_count": 48,
        }, exclusive=True)
    except BaseException as exc:
        atomic_json(result / "FAILED.json", {
            "schema": "zns-ann-z0b-run-failure-v1",
            "status": "failed",
            "timestamps": timestamp_pair(),
            "label": label,
            "error": repr(exc),
            "retry_permitted": False,
            "attempt_reuse_permitted": False,
        }, exclusive=True)
        raise


if __name__ == "__main__":
    main()
