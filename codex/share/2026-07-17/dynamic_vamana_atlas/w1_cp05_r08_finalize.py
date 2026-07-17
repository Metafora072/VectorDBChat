#!/usr/bin/env python3
"""Tamper-evident finalizer for CP05 cumulative trajectory R08 outputs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import statistics
from pathlib import Path
from typing import Any


SCHEMA = "dynamic-vamana-w1-cp05-cumulative-trajectory-r08-summary-v1"
RUN = "pilot3_sift10m_w1_cp05_trajectory_r08"
REPLAY_RUN = "pilot3_w1_cp05_trajectory_replay_r08"


def require(value: bool, message: str) -> None:
    if not value: raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""): digest.update(block)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True)
    return {"realpath": str(path), "size_bytes": path.stat().st_size, "sha256": sha256(path)}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text()); require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def module(name: str, filename: str) -> Any:
    path = Path(__file__).with_name(filename)
    if not path.is_file():
        path = Path("/home/ubuntu/pz/VectorDB/chat/codex/share/2026-08-16/dynamic_vamana_atlas") / filename
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot import {filename}")
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


def write_new_text(path: Path, payload: str) -> None:
    require(not path.exists() and not path.is_symlink(), f"final output overwrite refused: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())


def write_new_json(path: Path, value: dict[str, Any]) -> None:
    write_new_text(path, json.dumps(value, indent=2) + "\n")


def validate_identity(expected: dict[str, Any], label: str) -> None:
    path = Path(expected["realpath"]).resolve(strict=True)
    require(path.stat().st_size == int(expected["size_bytes"]) and sha256(path) == expected["sha256"],
            f"bound artifact changed: {label}")


def validate_query_accounting(gate: dict[str, Any], label: str) -> None:
    points = gate.get("points", [])
    require(isinstance(points, list) and points, f"{label} query points absent")
    for point in points:
        require(int(point.get("baseline_target_read_bytes", 0)) >= 4096
                and int(point.get("baseline_target_read_ios", 0)) >= 1
                and int(point.get("query_target_read_bytes_delta", 0)) > 0
                and int(point.get("query_target_read_ios_delta", 0)) > 0
                and point.get("primer_excluded_from_delta") is True,
                f"{label} query primer/accounting boundary invalid")
        primer = point.get("artifacts", {}).get("io_primer")
        require(isinstance(primer, dict), f"{label} primer identity absent")
        validate_identity(primer, f"{label} primer")


def stage_flat(system: str, checkpoint: str, stage: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "dynamic_stage", "system": system, "checkpoint": checkpoint,
        "incremental_replacements": stage["incremental_replacements"],
        "ingest_seconds": stage["phases"]["ingest"]["wall_seconds"],
        "replacements_per_second": stage["replacements_per_second"],
        "fresh_visible_seconds": stage["fresh_visible_seconds"],
        "online_visible_seconds": stage["online_visible_seconds"],
        "end_to_end_rbytes": stage["phases"]["end_to_end"]["rbytes"],
        "end_to_end_wbytes": stage["phases"]["end_to_end"]["wbytes"],
        "apparent_delta_bytes": stage["apparent_persistent_delta_bytes"],
        "allocated_delta_bytes": stage["allocated_persistent_delta_bytes"]}


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    require(not path.exists(), f"summary overwrite refused: {path}")
    with path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, delimiter="\t", fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows); stream.flush(); os.fsync(stream.fileno())


def validate(args: argparse.Namespace) -> dict[str, Any]:
    old = module("w1_cumulative_finalize_r08_import", "w1_cumulative_finalize.py")
    prehelper = module("w1_cp05_r08_preflight_finalize_import", "w1_cp05_r08_preflight.py")
    root = args.root.resolve(strict=True); result = args.result_root.resolve(strict=True)
    formal_root = args.formal_root.resolve(strict=True); replay_result = args.replay_result_root.resolve(strict=True)
    require(result == root / f"results/{RUN}" and formal_root == root / f"formal/{RUN}",
            "R08 finalizer capability path mismatch")
    require(replay_result in (result / "replay", root / f"results/{REPLAY_RUN}"),
            "R08 replay result root mismatch")
    expected_report = Path(__file__).parent.parent / "dynamic_vamana_w1_cp05_cumulative_trajectory_r08_results_0717.md"
    require(args.output_report.resolve(strict=False) == expected_report.resolve(strict=False),
            "R08 report output path mismatch")
    trajectory_path = result / "trajectory_summary.json"; summary_path = result / "summary.tsv"
    for path in (args.output_report, trajectory_path, summary_path):
        require(not path.exists() and not path.is_symlink(), f"final output is not fresh: {path}")

    preflight_path = args.preflight.resolve(strict=True); preflight = load(preflight_path)
    require(preflight.get("schema") == "dynamic-vamana-w1-cp05-cumulative-r08-preflight-v1"
            and preflight.get("status") == "pass", "R08 preflight invalid")
    preservation_path = args.preservation.resolve(strict=True); preservation = load(preservation_path)
    require(preservation.get("schema") == "dynamic-vamana-w1-cp05-cumulative-r08-preservation-v1"
            and preservation.get("status") == "pass" and not preservation.get("mismatches"),
            "R08 preservation invalid")
    smoke_path = args.static_smoke.resolve(strict=True); smoke = load(smoke_path)
    require(smoke.get("schema") == "dynamic-vamana-w1-cp05-r02-static-load-smoke-v1"
            and smoke.get("status") == "pass", "immutable replay-base smoke invalid")
    validate_identity(preflight["static_load_smoke"], "static smoke")
    require(preflight["static_load_smoke"]["sha256"] == sha256(smoke_path), "smoke/preflight SHA mismatch")
    execution_path = result / "execution_manifest.json"; execution = load(execution_path)
    require(execution.get("status") == "running", "execution manifest must be running before finalization")
    anchor = execution.get("preflight") or {"realpath": execution.get("preflight_realpath"),
                                             "sha256": execution.get("preflight_sha256")}
    require(Path(anchor.get("realpath", "")).resolve(strict=True) == preflight_path
            and anchor.get("sha256") == sha256(preflight_path), "execution/preflight anti-tamper anchor mismatch")

    replay: dict[str, Any] = {}; formal: dict[str, Any] = {}; rows: list[dict[str, Any]] = []
    replay_work_root = root / f"formal/{REPLAY_RUN}"
    for system in ("DGAI", "OdinANN"):
        replay_attempt = replay_result / system / "sequential-cp80-08"
        replay_work = replay_work_root / system / "sequential-cp80-08"
        require((replay_attempt / "CUMULATIVE_TRAJECTORY_OK").is_file(), f"{system} replay marker absent")
        replay_cp00_query = old.validate_query_gate(replay_attempt, replay_work, "replay", system, "cp00")
        validate_query_accounting(replay_cp00_query, f"{system} replay CP00")
        rcp01 = replay_attempt / "checkpoints/cp01/cp01_checkpoint_evidence.json"
        _, _, replay_cp01_query = old.validate_checkpoint_chain(
            replay_attempt, replay_work, "replay", system, "cp01", 16, None)
        validate_query_accounting(replay_cp01_query, f"{system} replay CP01")
        rcp05 = replay_attempt / "checkpoints/cp05/cp05_checkpoint_evidence.json"
        _, _, replay_cp05_query = old.validate_checkpoint_chain(
            replay_attempt, replay_work, "replay", system, "cp05", 64, rcp01)
        validate_query_accounting(replay_cp05_query, f"{system} replay CP05")
        old.validate_freeze_chain(replay_attempt, replay_work, "replay", system, rcp05)
        replay[system] = {"status": "pass", "classification": "1M structural replay only",
            "attempt": str(replay_attempt.resolve()), "clone": str(replay_work.resolve()),
            "cp01_checkpoint": identity(rcp01), "cp05_checkpoint": identity(rcp05),
            "freeze_evidence": identity(replay_attempt / "checkpoints/cp05/cp05_freeze_evidence.json")}

        attempt = result / system / "trajectory-cp05-08"; work = formal_root / system / "trajectory-cp05-08"
        require((attempt / "CUMULATIVE_TRAJECTORY_OK").is_file()
                and (work / "IMMUTABLE_TRAJECTORY_CP05_OK").is_file(), f"{system} formal marker absent")
        cp00_query = old.validate_query_gate(attempt, work, "formal", system, "cp00")
        validate_query_accounting(cp00_query, f"{system} formal CP00")
        cp01_path = attempt / "checkpoints/cp01/cp01_checkpoint_evidence.json"
        _, cp01_stage, cp01_query = old.validate_checkpoint_chain(
            attempt, work, "formal", system, "cp01", 80_000, None)
        validate_query_accounting(cp01_query, f"{system} formal CP01")
        cp05_path = attempt / "checkpoints/cp05/cp05_checkpoint_evidence.json"
        _, cp05_stage, cp05_query = old.validate_checkpoint_chain(
            attempt, work, "formal", system, "cp05", 320_000, cp01_path)
        validate_query_accounting(cp05_query, f"{system} formal CP05")
        old.validate_freeze_chain(attempt, work, "formal", system, cp05_path)
        stages = {"cp01": old.collect_stage(cp01_stage, 80_000, system),
                  "cp05": old.collect_stage(cp05_stage, 320_000, system)}
        query_points = [point for checkpoint, gate in (("cp00", cp00_query), ("cp01", cp01_query), ("cp05", cp05_query))
                        for point in old.collect_queries(gate, checkpoint)]
        query_summary = old.aggregate_queries(query_points)
        cp00_space, cp05_space = stages["cp01"]["space_before"], stages["cp05"]["space_after"]
        formal[system] = {"status": "pass", "attempt": str(attempt.resolve()), "clone": str(work.resolve()),
            "stages": stages, "query_points": query_points, "query_summary": query_summary,
            "accepted_cp01": old.historical_dynamic(root, system),
            "cumulative_cp00_to_cp05": {"replacements": 400_000, "primitive_mutations": 800_000,
                "stage_ingest_seconds_sum": sum(v["phases"]["ingest"]["wall_seconds"] for v in stages.values()),
                "end_to_end_read_bytes_sum": sum(v["phases"]["end_to_end"]["rbytes"] for v in stages.values()),
                "end_to_end_write_bytes_sum": sum(v["phases"]["end_to_end"]["wbytes"] for v in stages.values()),
                "cp00_to_cp05_apparent_growth_bytes": cp05_space["apparent_bytes"] - cp00_space["apparent_bytes"],
                "cp00_to_cp05_allocated_growth_bytes": cp05_space["allocated_bytes"] - cp00_space["allocated_bytes"]},
            "freeze_evidence": identity(attempt / "checkpoints/cp05/cp05_freeze_evidence.json"),
            "checkpoint_evidence": {"cp01": identity(cp01_path), "cp05": identity(cp05_path)}}
        for checkpoint, stage in stages.items(): rows.append(stage_flat(system, checkpoint, stage))
        for row in query_summary: rows.append({"kind": "dynamic_query", "system": system, **row})

    disk_path = result / "DiskANN/stale-cp05-08/stale_control.json"; disk = old.require_pass(disk_path)
    require(disk.get("classification") == "stale-static negative control", "DiskANN classification mismatch")
    disk_cp05 = [{"checkpoint": "cp05", "L": l_value,
        "median_recall_at_10": statistics.median(p["recall_at_10"] for p in disk["points"] if p["L"] == l_value)}
        for l_value in (29, 53)]
    prior_disk = load(root / "results/pilot3_sift10m_w1_r07/DiskANN/stale-cp00-07/stale_control.json")
    disk_cp01 = [{"checkpoint": "cp01", "L": l_value,
        "median_recall_at_10": statistics.median(p["recall_at_10"] for p in prior_disk["points"] if p["L"] == l_value),
        "provenance": str((root / "results/pilot3_sift10m_w1_r07/DiskANN/stale-cp00-07").resolve())}
        for l_value in (29, 53)]
    disk_trajectory = old.parse_historical_disk_cp00(root) + disk_cp01 + disk_cp05
    for row in disk_trajectory: rows.append({"kind": "diskann_stale", "system": "DiskANN", **row})

    # Re-run infrastructure verification at finalization, not merely its SHA identity.
    immutable = {}
    for system, entry in preflight["immutable_replay_bases"].items():
        manifest = load(Path(entry["manifest"]["realpath"])); base_dir = Path(manifest["immutable_base"]["realpath"]).parent
        immutable[system] = prehelper.verify_base(base_dir.parent.parent, system)
        require(smoke["systems"][system]["immutable_base_manifest"]["sha256"] == entry["manifest"]["sha256"],
                f"{system} smoke/immutable lineage mismatch")
    summary = {"schema": SCHEMA, "status": "pass",
        "decision_boundary": "CP05 cumulative R08 only; CP10/CP20 remain HOLD",
        "immutable_replay_bases": immutable, "static_load_smoke": smoke,
        "replay": replay, "formal": formal, "diskann_stale_trajectory": disk_trajectory,
        "diskann_cp05": disk, "preflight": identity(preflight_path),
        "preservation": identity(preservation_path), "execution_manifest_before_completion": identity(execution_path)}
    write_new_json(trajectory_path, summary); write_tsv(summary_path, rows)

    lines = ["# Dynamic Vamana W1 CP05 累计 Trajectory R08 实验结果", "", "## 裁决", "",
        "专用 immutable SIFT1M replay bases、四点 static-load smoke、DGAI/OdinANN 16→80 sequential replay 与正式 SIFT10M `CP00→CP01→CP05` 均通过。Recall 仅作观测；CP10/CP20 继续 HOLD。", "",
        "## Immutable replay-base lineage 与 static smoke", "",
        "两个 replay base 均从 accepted R07 content lineage 复制到独立 inode，source content/mode 前后不变；发布后为 root:root、目录 0555、文件 0444，owner write-denial 全覆盖。DGAI L=64/128 与 OdinANN L=29/46 的 36×10 static-load smoke 均满足 active/finite/NVMe/OOM/fatal 门禁。", "",
        "## Incremental update 成本", "",
        "| System | Stage | Replacements | Ingest s | Repl/s | E2E read GiB | E2E write GiB | Apparent Δ GiB | Allocated Δ GiB | Fresh-visible s | Online-visible s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for system in ("DGAI", "OdinANN"):
        for checkpoint in ("cp01", "cp05"):
            stage = formal[system]["stages"][checkpoint]; online = stage["online_visible_seconds"]
            lines.append(f"| {system} | {checkpoint.upper()} | {stage['incremental_replacements']:,} | {stage['phases']['ingest']['wall_seconds']:.3f} | {stage['replacements_per_second']:.3f} | {stage['phases']['end_to_end']['rbytes']/2**30:.3f} | {stage['phases']['end_to_end']['wbytes']/2**30:.3f} | {stage['apparent_persistent_delta_bytes']/2**30:.3f} | {stage['allocated_persistent_delta_bytes']/2**30:.3f} | {stage['fresh_visible_seconds']:.3f} | {online:.3f} |" if online is not None else f"| {system} | {checkpoint.upper()} | {stage['incremental_replacements']:,} | {stage['phases']['ingest']['wall_seconds']:.3f} | {stage['replacements_per_second']:.3f} | {stage['phases']['end_to_end']['rbytes']/2**30:.3f} | {stage['phases']['end_to_end']['wbytes']/2**30:.3f} | {stage['apparent_persistent_delta_bytes']/2**30:.3f} | {stage['allocated_persistent_delta_bytes']/2**30:.3f} | {stage['fresh_visible_seconds']:.3f} | unsupported |")
    lines += ["", "## 固定查询策略", "", "| System | Checkpoint | L | Median Recall@10 | Median QPS | Median P99 us | Median mean I/O |", "|---|---:|---:|---:|---:|---:|---:|"]
    for system in ("DGAI", "OdinANN"):
        for row in formal[system]["query_summary"]:
            lines.append(f"| {system} | {row['checkpoint'].upper()} | {row['L']} | {row['median_recall_at_10']:.6f} | {row['median_qps']:.3f} | {row['median_p99_latency_us']:.3f} | {row['median_mean_ios']:.3f} |")
    lines += ["", "accepted CP01 与本轮 trajectory CP01 并列保留，后者不替代前者。", "",
        "## DiskANN stale-static trajectory", "", "| Checkpoint | L | Median Recall@10 |", "|---|---:|---:|"]
    for row in disk_trajectory: lines.append(f"| {row['checkpoint'].upper()} | {row['L']} | {row['median_recall_at_10']:.6f} |")
    lines += ["", "DiskANN 始终使用冻结 CP00 base；本轮没有 rebuild。", "", "## 证据边界", "",
        f"机器摘要：`{trajectory_path}`；扁平摘要：`{summary_path}`。所有 finalizer 输入均重新验 hash 与 raw evidence；最终 preservation 为 `{preservation_path}`。本轮不授权 CP10、CP20、mixed workload、W2、DEEP 或 GIST。", ""]
    write_new_text(args.output_report, "\n".join(lines))
    return summary


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    for name in ("root", "result-root", "replay-result-root", "formal-root", "preflight",
                 "preservation", "static-smoke", "output-report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    return parser


def main() -> None:
    try: validate(parser().parse_args())
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc: raise SystemExit(str(exc)) from exc


if __name__ == "__main__": main()
