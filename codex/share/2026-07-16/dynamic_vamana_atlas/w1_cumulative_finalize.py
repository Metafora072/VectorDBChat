#!/usr/bin/env python3
"""Collect CP05 cumulative results into machine summaries and a review report."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import subprocess
from pathlib import Path
from typing import Any


DEVICE = "259:10"
COUNTERS = ("rbytes", "wbytes", "rios", "wios")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, object]:
    return {"realpath": str(path.resolve()), "size_bytes": path.stat().st_size, "sha256": sha256(path)}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def require_pass(path: Path) -> dict[str, Any]:
    value = load(path)
    if value.get("status") != "pass" and value.get("valid") is not True:
        raise ValueError(f"PASS evidence absent: {path}")
    return value


def require_value(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_identity(record: Any, label: str, expected_path: Path | None = None) -> Path:
    """Verify an evidence identity against the current immutable artifact."""
    require_value(isinstance(record, dict), f"{label} identity is not an object")
    require_value(isinstance(record.get("realpath"), str), f"{label} realpath absent")
    require_value(isinstance(record.get("sha256"), str), f"{label} sha256 absent")
    path = Path(record["realpath"]).resolve(strict=True)
    if expected_path is not None:
        require_value(path == expected_path.resolve(strict=True),
                      f"{label} realpath mismatch: {path} != {expected_path}")
    require_value(path.is_file(), f"{label} is not a regular file: {path}")
    require_value(sha256(path) == record["sha256"], f"{label} current SHA256 mismatch")
    if "size_bytes" in record:
        require_value(path.stat().st_size == int(record["size_bytes"]),
                      f"{label} current size mismatch")
    return path


def validate_query_gate(
    result_attempt: Path,
    work_attempt: Path,
    mode: str,
    system: str,
    checkpoint: str,
    expected_points: int = 6,
) -> dict[str, Any]:
    gate_path = result_attempt / f"queries/{checkpoint}/query_gate.json"
    gate = require_pass(gate_path)
    require_value(gate.get("schema") == "dynamic-vamana-w1-query-identity-v2",
                  f"query-gate schema mismatch: {gate_path}")
    require_value(gate.get("mode") == mode and gate.get("system") == system
                  and gate.get("checkpoint") == checkpoint,
                  f"query-gate mode/system/checkpoint mismatch: {gate_path}")
    identities = gate.get("identities", {})
    require_value(Path(identities.get("index_root_realpath", "")).resolve(strict=True)
                  == (work_attempt / "index").resolve(strict=True),
                  f"query-gate index identity mismatch: {gate_path}")
    for name in ("query_binary", "driver", "artifact_manifest", "index_content_manifest",
                 "query", "ground_truth", "active_tags"):
        require_value(name in identities and identities[name] is not None,
                      f"query-gate identity absent: {checkpoint}/{name}")
        verify_identity(identities[name], f"{checkpoint} query {name}")
    state_manifest = result_attempt / f"checkpoints/{checkpoint}/{checkpoint}_state_content_manifest.tsv"
    verify_identity(identities["index_content_manifest"],
                    f"{checkpoint} query state manifest", state_manifest)
    points = gate.get("points")
    require_value(isinstance(points, list) and len(points) == expected_points,
                  f"query-gate point count mismatch: {checkpoint}")
    seen: set[tuple[int, int]] = set()
    for point in points:
        key = (int(point.get("L", -1)), int(point.get("repeat", -1)))
        require_value(key not in seen and key[0] > 0 and key[1] in (1, 2, 3),
                      f"query-gate duplicate/invalid point: {checkpoint}/{key}")
        seen.add(key)
        artifacts = point.get("artifacts", {})
        expected_stem = result_attempt / f"queries/{checkpoint}/{checkpoint}_L{key[0]}_r{key[1]}"
        suffixes = {
            "metrics": ".metrics.json", "validation": ".validation.json",
            "resources": ".resources.json", "log": ".log",
            "result_ids": ".result_ids.bin",
        }
        for name, suffix in suffixes.items():
            verify_identity(artifacts.get(name), f"{checkpoint}/{key} {name}",
                            Path(f"{expected_stem}{suffix}"))
    return gate


def validate_stage_evidence(
    result_attempt: Path,
    work_attempt: Path,
    mode: str,
    system: str,
    checkpoint: str,
    expected_replacements: int,
) -> dict[str, Any]:
    stage_path = result_attempt / f"stages/{checkpoint}/stage_evidence.json"
    stage = require_pass(stage_path)
    require_value(stage.get("schema") == "dynamic-vamana-w1-cumulative-stage-evidence-v1",
                  f"stage-evidence schema mismatch: {stage_path}")
    require_value(stage.get("mode") == mode and stage.get("system") == system
                  and stage.get("checkpoint") == checkpoint,
                  f"stage-evidence mode/system/checkpoint mismatch: {stage_path}")
    require_value(Path(stage.get("attempt_realpath", "")).resolve(strict=True)
                  == work_attempt.resolve(strict=True), f"stage attempt mismatch: {stage_path}")
    require_value(Path(stage.get("index_root_realpath", "")).resolve(strict=True)
                  == (work_attempt / "index").resolve(strict=True), f"stage index mismatch: {stage_path}")
    require_value(int(stage.get("delta_count", -1)) == expected_replacements,
                  f"stage replacement count mismatch: {stage_path}")
    required_phases = {"trace_load", "ingest", "online", "publish", "fresh", "end_to_end"}
    require_value(set(stage.get("phases", {})) == required_phases,
                  f"stage phase set mismatch: {stage_path}")
    for phase_name in required_phases - {"online"}:
        phase = stage["phases"][phase_name]
        require_value(float(phase.get("wall_seconds", -1)) >= 0,
                      f"stage phase wall time absent: {checkpoint}/{phase_name}")
        for counter in COUNTERS:
            require_value(int(phase.get(counter, -1)) >= 0,
                          f"stage phase counter absent: {checkpoint}/{phase_name}/{counter}")
    artifacts = stage.get("artifacts", {})
    required_artifacts = {
        "trace", "delta_manifest", "expected_active", "runtime_active_audit",
        "local_probe_spec", "global_probe_spec", "combined_probe_spec", "fresh_result",
        "fresh_probe", "worker_identity", "stage_resources", "markers", "controller_log",
        "input_capability_canary",
    }
    if system == "OdinANN":
        required_artifacts |= {"online_result", "online_probe"}
    require_value(required_artifacts.issubset(artifacts),
                  f"stage artifact set incomplete: {checkpoint}/{required_artifacts - set(artifacts)}")
    for name in required_artifacts:
        verify_identity(artifacts[name], f"{checkpoint} stage {name}")
    verify_identity(artifacts["stage_resources"], f"{checkpoint} stage resources",
                    result_attempt / f"{checkpoint}_stage_resources.json")
    verify_identity(artifacts["markers"], f"{checkpoint} stage markers",
                    result_attempt / f"stages/{checkpoint}/markers.jsonl")
    return stage


def validate_checkpoint_chain(
    result_attempt: Path,
    work_attempt: Path,
    mode: str,
    system: str,
    checkpoint: str,
    expected_replacements: int,
    previous_path: Path | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    checkpoint_path = result_attempt / f"checkpoints/{checkpoint}/{checkpoint}_checkpoint_evidence.json"
    checkpoint_report = require_pass(checkpoint_path)
    require_value(checkpoint_report.get("schema") == "dynamic-vamana-w1-cumulative-checkpoint-v1",
                  f"checkpoint schema mismatch: {checkpoint_path}")
    require_value(checkpoint_report.get("mode") == mode and checkpoint_report.get("system") == system
                  and checkpoint_report.get("checkpoint") == checkpoint,
                  f"checkpoint mode/system/name mismatch: {checkpoint_path}")
    require_value(Path(checkpoint_report.get("attempt_realpath", "")).resolve(strict=True)
                  == work_attempt.resolve(strict=True), f"checkpoint attempt mismatch: {checkpoint_path}")
    require_value(Path(checkpoint_report.get("index_root_realpath", "")).resolve(strict=True)
                  == (work_attempt / "index").resolve(strict=True), f"checkpoint index mismatch: {checkpoint_path}")
    stage_path = result_attempt / f"stages/{checkpoint}/stage_evidence.json"
    query_path = result_attempt / f"queries/{checkpoint}/query_gate.json"
    verify_identity(checkpoint_report.get("stage_evidence"), f"{checkpoint} checkpoint stage", stage_path)
    verify_identity(checkpoint_report.get("query_gate"), f"{checkpoint} checkpoint query", query_path)
    for key, filename in (
        ("state_content_manifest", f"{checkpoint}_state_content_manifest.tsv"),
        ("state_mode_manifest", f"{checkpoint}_state_mode_manifest.tsv"),
        ("active_audit", f"{checkpoint}_active_audit.json"),
        ("query_summary", f"{checkpoint}_query_summary.tsv"),
    ):
        verify_identity(checkpoint_report.get(key), f"{checkpoint} checkpoint {key}",
                        result_attempt / f"checkpoints/{checkpoint}/{filename}")
    if previous_path is None:
        require_value(checkpoint_report.get("previous_checkpoint_evidence") is None,
                      "CP01 unexpectedly claims previous checkpoint evidence")
    else:
        verify_identity(checkpoint_report.get("previous_checkpoint_evidence"),
                        "CP05 previous checkpoint", previous_path)
        require_value(checkpoint_report.get("same_clone_as_previous") is True
                      and checkpoint_report.get("distinct_worker_from_previous") is True,
                      "CP05 same-clone/distinct-worker verdict absent")
    stage = validate_stage_evidence(result_attempt, work_attempt, mode, system,
                                    checkpoint, expected_replacements)
    query = validate_query_gate(result_attempt, work_attempt, mode, system, checkpoint)
    for name, record in checkpoint_report.get("stage_artifacts", {}).items():
        current = verify_identity(record, f"{checkpoint} checkpoint stage artifact {name}")
        require_value(name in stage["artifacts"] and record["sha256"] == stage["artifacts"][name]["sha256"],
                      f"checkpoint/stage artifact mismatch: {checkpoint}/{name}")
        require_value(current == Path(stage["artifacts"][name]["realpath"]).resolve(strict=True),
                      f"checkpoint/stage artifact path mismatch: {checkpoint}/{name}")
    return checkpoint_report, stage, query


def validate_freeze_chain(
    result_attempt: Path,
    work_attempt: Path,
    mode: str,
    system: str,
    cp05_path: Path,
) -> dict[str, Any]:
    freeze_path = result_attempt / "checkpoints/cp05/cp05_freeze_evidence.json"
    freeze = require_pass(freeze_path)
    require_value(freeze.get("schema") == "dynamic-vamana-w1-cp05-freeze-v1"
                  and freeze.get("mode") == mode and freeze.get("system") == system
                  and freeze.get("checkpoint") == "cp05", "freeze schema/identity mismatch")
    require_value(Path(freeze.get("attempt_realpath", "")).resolve(strict=True)
                  == work_attempt.resolve(strict=True), "freeze attempt mismatch")
    require_value(Path(freeze.get("root_realpath", "")).resolve(strict=True)
                  == (work_attempt / "index").resolve(strict=True), "freeze index mismatch")
    verify_identity(freeze.get("checkpoint_evidence"), "freeze CP05 checkpoint", cp05_path)
    require_value(freeze.get("content_exact_across_freeze") is True,
                  "freeze content exactness verdict absent")
    require_value(int(freeze.get("owner_file_write_denials", -1)) == int(freeze.get("regular_files", -2))
                  and int(freeze.get("owner_directory_create_denials", -1)) == int(freeze.get("directories", -2)),
                  "freeze owner-denial counts incomplete")
    for name, record in freeze.get("evidence", {}).items():
        verify_identity(record, f"freeze {name}")
    verify_identity(freeze.get("evidence", {}).get("immutable_marker"), "freeze immutable marker",
                    work_attempt / "IMMUTABLE_TRAJECTORY_CP05_OK")
    return freeze


def io_row(sample: dict[str, Any], device: str = DEVICE) -> dict[str, int]:
    return next(
        ({key: int(row.get(key, 0)) for key in COUNTERS}
         for row in sample.get("cgroup_io_stat", []) if row.get("device") == device),
        {key: 0 for key in COUNTERS},
    )


def difference(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    result = {key: right[key] - left[key] for key in COUNTERS}
    if any(value < 0 for value in result.values()):
        raise ValueError("cgroup I/O counter decreased")
    return result


def marker_map(path: Path) -> dict[str, int]:
    markers: dict[str, int] = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        name, timestamp = row.get("marker"), row.get("monotonic_ns")
        if not isinstance(name, str) or not isinstance(timestamp, int) or name in markers:
            raise ValueError(f"invalid marker stream: {path}")
        markers[name] = timestamp
    return markers


def phase_io(resources: dict[str, Any], begin: int, end: int) -> dict[str, object]:
    samples = sorted(
        ((int(row["monotonic_ns"]), io_row(row)) for row in resources.get("samples", [])
         if isinstance(row.get("monotonic_ns"), int)),
        key=lambda item: item[0],
    )
    left = next((row for row in reversed(samples) if row[0] <= begin), None)
    right = next((row for row in samples if row[0] >= end), None)
    if left is None or right is None or right[0] <= left[0]:
        raise ValueError("phase lacks bracketing resource samples")
    return {
        "wall_seconds": (end - begin) / 1e9,
        "left_sample_ns": left[0],
        "right_sample_ns": right[0],
        **difference(left[1], right[1]),
    }


def final_space(resources: dict[str, Any]) -> tuple[dict[str, int], dict[str, int]]:
    before = resources.get("space_before")
    after = next(
        (sample.get("index_space") for sample in reversed(resources.get("samples", []))
         if isinstance(sample.get("index_space"), dict)),
        None,
    )
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError("stage resource evidence lacks before/final space")
    fields = ("files", "apparent_bytes", "allocated_bytes")
    return ({field: int(before.get(field, 0)) for field in fields},
            {field: int(after.get(field, 0)) for field in fields})


def collect_stage(stage_evidence: dict[str, Any], replacements: int, system: str) -> dict[str, Any]:
    """Collect statistics only from a validated, hash-anchored stage report."""
    phases = stage_evidence["phases"]
    before = stage_evidence["space"]["before"]
    after = stage_evidence["space"]["after"]
    markers = stage_evidence["marker_timestamps"]
    ingest_seconds = float(phases["ingest"]["wall_seconds"])
    require_value(ingest_seconds > 0, "stage ingest duration is nonpositive")
    fresh_seconds = (int(markers["fresh_process_visibility_verified"])
                     - int(markers["ingest_begin"])) / 1e9
    online_seconds = ((int(markers["online_visibility_verified"])
                       - int(markers["ingest_begin"])) / 1e9
                      if system == "OdinANN" else None)
    require_value(fresh_seconds > 0 and (online_seconds is None or online_seconds > 0),
                  "stage visibility duration is nonpositive")
    result = {
        "status": "pass",
        "checkpoint": stage_evidence["checkpoint"],
        "incremental_replacements": replacements,
        "primitive_mutations": 2 * replacements,
        "replacements_per_second": replacements / ingest_seconds,
        "primitive_mutations_per_second": 2 * replacements / ingest_seconds,
        "fresh_visible_seconds": fresh_seconds,
        "fresh_visible_replacements_per_second": replacements / fresh_seconds,
        "online_visible_seconds": online_seconds,
        "online_visible_replacements_per_second": replacements / online_seconds if online_seconds else None,
        "phases": phases,
        "space_before": before,
        "space_after": after,
        "apparent_persistent_delta_bytes": int(stage_evidence["space"]["apparent_growth_bytes"]),
        "allocated_persistent_delta_bytes": int(stage_evidence["space"]["allocated_growth_bytes"]),
        "peak_process_tree_rss_bytes": int(stage_evidence["resources"]["peak_process_tree_rss_bytes"]),
        "cgroup_memory_peak_bytes": int(stage_evidence["resources"]["cgroup_memory_peak_bytes"]),
        "worker_identity": stage_evidence["worker_identity"],
        "evidence": {
            name: record for name, record in stage_evidence["artifacts"].items()
        },
    }
    for phase_name in ("ingest", "publish", "end_to_end"):
        phase = result["phases"][phase_name]
        phase["read_bytes_per_incremental_replacement"] = phase["rbytes"] / replacements
        phase["write_bytes_per_incremental_replacement"] = phase["wbytes"] / replacements
    return result


def query_resource_reads(path: Path) -> int:
    value = load(path)
    samples = value.get("samples", [])
    if value.get("returncode") != 0 or len(samples) < 2:
        raise ValueError(f"query resource evidence invalid: {path}")
    return io_row(samples[-1])["rbytes"] - io_row(samples[0])["rbytes"]


def collect_queries(gate: dict[str, Any], checkpoint: str) -> list[dict[str, object]]:
    """Read raw metrics only after validate_query_gate verified their current SHA."""
    points: list[dict[str, object]] = []
    for gate_point in gate["points"]:
        l_value = int(gate_point["L"]); repetition = int(gate_point["repeat"])
        metrics_path = Path(gate_point["artifacts"]["metrics"]["realpath"])
        metrics = load(metrics_path)
        if not all(math.isfinite(float(metrics[field])) for field in (
            "qps", "mean_latency_us", "p99_latency_us", "mean_ios", "recall_at_10_percent"
        )):
            raise ValueError(f"non-finite query metric: {metrics_path}")
        resources_path = Path(gate_point["artifacts"]["resources"]["realpath"])
        points.append({
            "checkpoint": checkpoint,
            "L": l_value,
            "Tq": 1,
            "repetition": repetition,
            "qps": float(metrics["qps"]),
            "mean_latency_us": float(metrics["mean_latency_us"]),
            "p99_latency_us": float(metrics["p99_latency_us"]),
            "mean_ios": float(metrics["mean_ios"]),
            "recall_at_10": float(metrics["recall_at_10_percent"]) / 100.0,
            "nvme_read_bytes": int(gate_point["device_read_bytes"]),
            "metrics_sha256": sha256(metrics_path),
            "resources_sha256": sha256(resources_path),
        })
    expected = 6
    if len(points) != expected:
        raise ValueError(f"checkpoint query count {len(points)} != {expected}: {checkpoint}")
    return points


def aggregate_queries(points: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, int], list[dict[str, object]]] = {}
    for point in points:
        groups.setdefault((str(point["checkpoint"]), int(point["L"])), []).append(point)
    rows = []
    for (checkpoint, l_value), group in sorted(groups.items()):
        if len(group) != 3:
            raise ValueError("each checkpoint/L requires three repetitions")
        rows.append({
            "checkpoint": checkpoint,
            "L": l_value,
            "Tq": 1,
            **{f"median_{name}": statistics.median(float(row[name]) for row in group)
               for name in ("qps", "p99_latency_us", "mean_ios", "recall_at_10", "nvme_read_bytes")},
        })
    return rows


def historical_dynamic(root: Path, system: str) -> dict[str, object]:
    if system == "DGAI":
        attempt = root / "results/pilot3_sift10m_w1_r05/DGAI/cp01-05"
        ls = (64, 128)
    else:
        attempt = root / "results/pilot3_sift10m_w1_r06/OdinANN/cp01-06"
        ls = (29, 46)
    canary = load(attempt / "canary.json")
    queries = []
    for l_value in ls:
        metrics = [load(attempt / f"post_cp01_L{l_value}_r{repetition}.metrics.json") for repetition in (1, 2, 3)]
        queries.append({
            "L": l_value,
            "median_recall_at_10": statistics.median(row["recall_at_10_percent"] for row in metrics) / 100.0,
            "median_qps": statistics.median(row["qps"] for row in metrics),
            "median_p99_latency_us": statistics.median(row["p99_latency_us"] for row in metrics),
            "median_mean_ios": statistics.median(row["mean_ios"] for row in metrics),
        })
    phases = canary["phase_device_accounting"]
    return {
        "provenance": str(attempt.resolve()),
        "canary_sha256": sha256(attempt / "canary.json"),
        "replacements_per_second": canary["ingestion_throughput_ops_s"],
        "fresh_visible_seconds": canary["restart_visibility_seconds"],
        "online_visible_seconds": canary["online_visibility_seconds"],
        "end_to_end_write_bytes_per_replacement": phases["end_to_end_device_delta"]["wbytes"] / 80_000,
        "apparent_persistent_growth_bytes": canary["persistent_index_growth_bytes"],
        "allocated_persistent_growth_bytes": None,
        "query": queries,
    }


def parse_historical_disk_cp00(root: Path) -> list[dict[str, object]]:
    base = root / "results/pilot3_sift10m_p2b/refinement/DiskANN/tq1"
    rows = []
    for l_value in (29, 53):
        recalls = []
        for repetition in (1, 2, 3):
            log = (base / f"L{l_value}/r{repetition}/query.log").read_text()
            line = next(line for line in log.splitlines() if line.split()[:1] == [str(l_value)] and len(line.split()) == 9)
            recalls.append(float(line.split()[-1]) / 100.0)
        rows.append({"checkpoint": "cp00", "L": l_value, "median_recall_at_10": statistics.median(recalls),
                     "provenance": str((base / f"L{l_value}").resolve())})
    return rows


def write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, delimiter="\t", fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--device", default="259:10")
    args = parser.parse_args()
    global DEVICE
    DEVICE = args.device
    root = args.root.resolve(); result = args.result_root.resolve()
    if args.report.exists() or (result / "summary.tsv").exists() or (result / "trajectory_summary.json").exists():
        raise SystemExit("final summary/report overwrite refused")
    execution = load(result / "execution_manifest.json")
    if execution.get("status") != "running":
        raise SystemExit("execution manifest is not in running state")
    preservation = require_pass(result / "preflight/preservation_final.json")

    replay: dict[str, object] = {}
    formal: dict[str, object] = {}
    all_summary_rows: list[dict[str, object]] = []
    for system in ("DGAI", "OdinANN"):
        replay_attempt = result / f"replay/{system}/sequential-cp80-01"
        replay_work = root / f"formal/pilot3_w1_cp05_trajectory_replay/{system}/sequential-cp80-01"
        if not (replay_attempt / "CUMULATIVE_TRAJECTORY_OK").is_file():
            raise SystemExit(f"replay completion marker absent: {system}")
        validate_query_gate(replay_attempt, replay_work, "replay", system, "cp00")
        replay_cp01_path = replay_attempt / "checkpoints/cp01/cp01_checkpoint_evidence.json"
        replay_cp01, _, _ = validate_checkpoint_chain(
            replay_attempt, replay_work, "replay", system, "cp01", 16, None
        )
        replay_cp05_path = replay_attempt / "checkpoints/cp05/cp05_checkpoint_evidence.json"
        replay_cp05, _, _ = validate_checkpoint_chain(
            replay_attempt, replay_work, "replay", system, "cp05", 64, replay_cp01_path
        )
        replay_freeze = validate_freeze_chain(
            replay_attempt, replay_work, "replay", system, replay_cp05_path
        )
        replay[system] = {
            "status": "pass",
            "classification": "1M structural replay only; no performance interpretation",
            "cp01_checkpoint": identity(replay_cp01_path),
            "cp05_checkpoint": identity(replay_cp05_path),
            "freeze_evidence": identity(replay_attempt / "checkpoints/cp05/cp05_freeze_evidence.json"),
        }
        formal_attempt = result / f"{system}/trajectory-cp05-01"
        formal_index = root / f"formal/pilot3_sift10m_w1_cp05_trajectory/{system}/trajectory-cp05-01"
        if not (formal_attempt / "CUMULATIVE_TRAJECTORY_OK").is_file() or not (
            formal_index / "IMMUTABLE_TRAJECTORY_CP05_OK"
        ).is_file():
            raise SystemExit(f"formal cumulative/freeze marker absent: {system}")
        cp00_query = validate_query_gate(formal_attempt, formal_index, "formal", system, "cp00")
        cp01_path = formal_attempt / "checkpoints/cp01/cp01_checkpoint_evidence.json"
        cp01_report, cp01_stage, cp01_query = validate_checkpoint_chain(
            formal_attempt, formal_index, "formal", system, "cp01", 80_000, None
        )
        cp05_path = formal_attempt / "checkpoints/cp05/cp05_checkpoint_evidence.json"
        cp05_report, cp05_stage, cp05_query = validate_checkpoint_chain(
            formal_attempt, formal_index, "formal", system, "cp05", 320_000, cp01_path
        )
        freeze_report = validate_freeze_chain(
            formal_attempt, formal_index, "formal", system, cp05_path
        )
        stages = {
            "cp01": collect_stage(cp01_stage, 80_000, system),
            "cp05": collect_stage(cp05_stage, 320_000, system),
        }
        query_gates = {"cp00": cp00_query, "cp01": cp01_query, "cp05": cp05_query}
        query_points = [point for checkpoint, gate in query_gates.items()
                        for point in collect_queries(gate, checkpoint)]
        query_summary = aggregate_queries(query_points)
        cp00_space = stages["cp01"]["space_before"]
        cp05_space = stages["cp05"]["space_after"]
        cumulative = {
            "replacements": 400_000,
            "primitive_mutations": 800_000,
            "stage_ingest_seconds_sum": sum(stage["phases"]["ingest"]["wall_seconds"] for stage in stages.values()),
            "end_to_end_read_bytes_sum": sum(stage["phases"]["end_to_end"]["rbytes"] for stage in stages.values()),
            "end_to_end_write_bytes_sum": sum(stage["phases"]["end_to_end"]["wbytes"] for stage in stages.values()),
            "cp00_to_cp05_apparent_growth_bytes": cp05_space["apparent_bytes"] - cp00_space["apparent_bytes"],
            "cp00_to_cp05_allocated_growth_bytes": cp05_space["allocated_bytes"] - cp00_space["allocated_bytes"],
        }
        formal[system] = {
            "status": "pass", "attempt": str(formal_attempt.resolve()), "clone": str(formal_index.resolve()),
            "stages": stages, "query_points": query_points, "query_summary": query_summary,
            "cumulative_cp00_to_cp05": cumulative, "accepted_cp01": historical_dynamic(root, system),
            "freeze_evidence": identity(formal_attempt / "checkpoints/cp05/cp05_freeze_evidence.json"),
            "checkpoint_evidence": {"cp01": identity(cp01_path), "cp05": identity(cp05_path)},
        }
        for checkpoint, stage in stages.items():
            all_summary_rows.append({"kind": "dynamic_stage", "system": system, **{k: v for k, v in stage.items() if not isinstance(v, dict)}})
        for row in query_summary:
            all_summary_rows.append({"kind": "dynamic_query", "system": system, **row})

    disk = require_pass(result / "DiskANN/stale-cp05-01/stale_control.json")
    disk_cp05 = [
        {"checkpoint": "cp05", "L": l_value,
         "median_recall_at_10": statistics.median(point["recall_at_10"] for point in disk["points"] if point["L"] == l_value)}
        for l_value in (29, 53)
    ]
    prior_disk = load(root / "results/pilot3_sift10m_w1_r07/DiskANN/stale-cp00-07/stale_control.json")
    disk_cp01 = [
        {"checkpoint": "cp01", "L": l_value,
         "median_recall_at_10": statistics.median(point["recall_at_10"] for point in prior_disk["points"] if point["L"] == l_value),
         "provenance": str((root / "results/pilot3_sift10m_w1_r07/DiskANN/stale-cp00-07").resolve())}
        for l_value in (29, 53)
    ]
    disk_trajectory = parse_historical_disk_cp00(root) + disk_cp01 + disk_cp05
    for row in disk_trajectory:
        all_summary_rows.append({"kind": "diskann_stale", "system": "DiskANN", **row})

    summary = {
        "schema": "dynamic-vamana-w1-cp05-cumulative-trajectory-summary-v1",
        "status": "pass",
        "decision_boundary": "CP05 cumulative evidence only; CP10/CP20 remain HOLD",
        "replay": replay,
        "formal": formal,
        "diskann_stale_trajectory": disk_trajectory,
        "diskann_cp05": disk,
        "preservation": preservation,
        "execution_manifest_before_completion": identity(result / "execution_manifest.json"),
    }
    trajectory_path = result / "trajectory_summary.json"
    trajectory_path.write_text(json.dumps(summary, indent=2) + "\n")
    write_tsv(result / "summary.tsv", all_summary_rows)

    lines = [
        "# Dynamic Vamana W1 CP05 累计 Trajectory 实验结果",
        "",
        "## 裁决",
        "",
        "1M sequential-state replay 与正式 SIFT10M `CP00→CP01→CP05` 均通过；以下 Recall 仅作观测，不设事后阈值。CP10/CP20 仍为 HOLD，本轮没有执行其更新，也没有执行 DiskANN rebuild、mixed workload、W2、DEEP 或 GIST。",
        "",
        "## 累计状态机与正确性",
        "",
        "DGAI 与 OdinANN 均只创建一次私有 CP00 clone，由两个独立 worker 依次应用 80K 与 320K delta；CP05 worker 从同一 persisted CP01 realpath fresh-load。两阶段 active-set exact、local/global visibility probes、CP00 base preservation、query identity-v2 与最终 0555/0444 freeze 全部通过。1M replay 使用同一 runner 执行 16→80 records，仅解释结构正确性。",
        "",
        "## Incremental update 成本",
        "",
        "| System | Stage | Replacements | Ingest s | Repl/s | Primitive/s | E2E read GiB | E2E write GiB | Apparent Δ GiB | Allocated Δ GiB | Fresh-visible s | Online-visible s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for system in ("DGAI", "OdinANN"):
        for checkpoint in ("cp01", "cp05"):
            stage = formal[system]["stages"][checkpoint]
            lines.append(
                f"| {system} | {checkpoint.upper()} | {stage['incremental_replacements']:,} | "
                f"{stage['phases']['ingest']['wall_seconds']:.3f} | {stage['replacements_per_second']:.3f} | "
                f"{stage['primitive_mutations_per_second']:.3f} | {stage['phases']['end_to_end']['rbytes']/2**30:.3f} | "
                f"{stage['phases']['end_to_end']['wbytes']/2**30:.3f} | {stage['apparent_persistent_delta_bytes']/2**30:.3f} | "
                f"{stage['allocated_persistent_delta_bytes']/2**30:.3f} | {stage['fresh_visible_seconds']:.3f} | "
                f"{stage['online_visible_seconds']:.3f} |" if stage['online_visible_seconds'] is not None else
                f"| {system} | {checkpoint.upper()} | {stage['incremental_replacements']:,} | "
                f"{stage['phases']['ingest']['wall_seconds']:.3f} | {stage['replacements_per_second']:.3f} | "
                f"{stage['primitive_mutations_per_second']:.3f} | {stage['phases']['end_to_end']['rbytes']/2**30:.3f} | "
                f"{stage['phases']['end_to_end']['wbytes']/2**30:.3f} | {stage['apparent_persistent_delta_bytes']/2**30:.3f} | "
                f"{stage['allocated_persistent_delta_bytes']/2**30:.3f} | {stage['fresh_visible_seconds']:.3f} | unsupported |"
            )
    lines += [
        "",
        "## 固定查询策略",
        "",
        "| System | Checkpoint | L | Median Recall@10 | Median QPS | Median P99 us | Median mean I/O |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for system in ("DGAI", "OdinANN"):
        for row in formal[system]["query_summary"]:
            lines.append(f"| {system} | {row['checkpoint'].upper()} | {row['L']} | {row['median_recall_at_10']:.6f} | {row['median_qps']:.3f} | {row['median_p99_latency_us']:.3f} | {row['median_mean_ios']:.3f} |")
    lines += [
        "",
        "新的 trajectory CP01 replay 不替代 R05 DGAI / R06 OdinANN 的 accepted CP01；两组 provenance 与 query/update 指标均保存在 `trajectory_summary.json`，仅作 reproducibility 观察。历史 allocated growth 未采集，明确记为 unavailable。",
        "",
        "## DiskANN stale-static trajectory",
        "",
        "| Checkpoint | L | Median Recall@10 |",
        "|---|---:|---:|",
    ]
    for row in disk_trajectory:
        lines.append(f"| {row['checkpoint'].upper()} | {row['L']} | {row['median_recall_at_10']:.6f} |")
    lines += [
        "",
        "DiskANN 始终使用冻结 CP00 index；CP00、CP01、CP05 分别来自 P2B Tq=1 baseline、accepted R07 与本轮 CP05 stale control。它是 stale-static negative control，不参与动态 update throughput 排名。",
        "",
        "## 证据边界",
        "",
        f"机器汇总：`{trajectory_path}`；扁平摘要：`{result/'summary.tsv'}`。CP01 manifest 只是同一 mutable clone 的时点加密摘要，不是可恢复 snapshot。两个 CP05 clone 已冻结，未来 CP10 只能从其新建 mutable clone，不能解冻或续写本 attempt。",
        "",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
