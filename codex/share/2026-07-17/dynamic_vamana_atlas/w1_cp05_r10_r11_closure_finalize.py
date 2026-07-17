#!/usr/bin/env python3
"""Finalize the composed R10 dynamic + R11 DiskANN stale-control closure."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import statistics
from pathlib import Path
from typing import Any


SCHEMA = "dynamic-vamana-w1-cp05-r10-r11-composed-closure-v1"
R10_RUN = "pilot3_sift10m_w1_cp05_trajectory_r10"
R11_RUN = "pilot3_sift10m_w1_cp05_diskann_closure_r11"


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True)
    return {"realpath": str(path), "size_bytes": path.stat().st_size, "sha256": sha256(path)}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text()); require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def module(name: str, filename: str) -> Any:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot import {filename}")
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


def write_new(path: Path, payload: str) -> None:
    require(not path.exists() and not path.is_symlink(), f"closure output overwrite refused: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(payload); stream.flush(); os.fsync(stream.fileno())


def validate_bound(record: dict[str, Any], label: str) -> dict[str, Any]:
    path = Path(record["realpath"]).resolve(strict=True)
    live = identity(path)
    require(live["size_bytes"] == record["size_bytes"] and live["sha256"] == record["sha256"],
            f"bound R10 artifact changed: {label}")
    return live


def validate(args: argparse.Namespace) -> dict[str, Any]:
    r10final = module("w1_r10_finalize_for_r11", "w1_cp05_r10_finalize.py")
    old = r10final.module("w1_cumulative_finalize_for_r11", "w1_cumulative_finalize.py")
    root = args.root.resolve(strict=True)
    r10_result = args.r10_result.resolve(strict=True)
    r10_formal = args.r10_formal.resolve(strict=True)
    r11_result = args.r11_result.resolve(strict=True)
    require(r10_result == root / f"results/{R10_RUN}" and r10_formal == root / f"formal/{R10_RUN}",
            "R10 closure capability mismatch")
    require(r11_result == root / f"results/{R11_RUN}", "R11 closure capability mismatch")
    expected_report = Path(__file__).parent.parent / "dynamic_vamana_w1_cp05_cumulative_trajectory_r10_r11_closure_results_0717.md"
    require(args.output_report.resolve(strict=False) == expected_report.resolve(strict=False),
            "composed closure report path mismatch")
    closure_path = args.closure_manifest.resolve(strict=False)
    require(closure_path == r11_result / "closure_manifest.json", "closure manifest path mismatch")
    require(not closure_path.exists() and not args.output_report.exists(), "closure outputs are not fresh")

    r11_preflight_path = args.r11_preflight.resolve(strict=True); r11_preflight = load(r11_preflight_path)
    require(r11_preflight.get("schema") == "dynamic-vamana-w1-cp05-diskann-closure-r11-preflight-v1"
            and r11_preflight.get("status") == "pass", "R11 preflight invalid")
    r11_execution_path = r11_result / "execution_manifest.json"; r11_execution = load(r11_execution_path)
    require(r11_execution.get("schema") == "dynamic-vamana-w1-cp05-diskann-closure-r11-execution-v1"
            and r11_execution.get("status") == "running", "R11 execution must be running before finalization")
    require(r11_execution.get("preflight_realpath") == str(r11_preflight_path)
            and r11_execution.get("preflight_sha256") == sha256(r11_preflight_path),
            "R11 execution/preflight anti-tamper anchor mismatch")
    r10_execution_path = r10_result / "execution_manifest.json"; r10_execution = load(r10_execution_path)
    require((r10_execution.get("status"), r10_execution.get("stopped_phase"), r10_execution.get("exit_code"))
            == ("stopped_failed", "diskann_cp05_stale_control", 1), "R10 terminal boundary changed")
    require(r11_execution.get("r10_execution_sha256") == sha256(r10_execution_path),
            "R11/R10 execution anchor mismatch")
    r10_stop_path = r10_result / "preflight/preservation_after_stop.json"; r10_stop = load(r10_stop_path)
    r10_post_path = args.r10_post_preservation.resolve(strict=True); r10_post = load(r10_post_path)
    for label, report in (("stop", r10_stop), ("post-R11", r10_post)):
        require(report.get("schema") == "dynamic-vamana-w1-cp05-cumulative-r10-preservation-v1"
                and report.get("status") == "pass" and not report.get("mismatches"),
                f"R10 {label} preservation invalid")

    for category in ("completion_markers", "stage_evidence", "formal_query_validations", "freeze_evidence"):
        for name, record in r11_preflight["r10"][category].items():
            validate_bound(record, f"{category}/{name}")

    formal: dict[str, Any] = {}
    for system in ("DGAI", "OdinANN"):
        attempt = r10_result / f"{system}/trajectory-cp05-10"
        work = r10_formal / f"{system}/trajectory-cp05-10"
        cp00_query = old.validate_query_gate(attempt, work, "formal", system, "cp00")
        r10final.validate_query_accounting(cp00_query, f"{system} formal CP00")
        cp01_path = attempt / "checkpoints/cp01/cp01_checkpoint_evidence.json"
        _, cp01_stage, cp01_query = old.validate_checkpoint_chain(
            attempt, work, "formal", system, "cp01", 80_000, None)
        r10final.validate_query_accounting(cp01_query, f"{system} formal CP01")
        cp05_path = attempt / "checkpoints/cp05/cp05_checkpoint_evidence.json"
        _, cp05_stage, cp05_query = old.validate_checkpoint_chain(
            attempt, work, "formal", system, "cp05", 320_000, cp01_path)
        r10final.validate_query_accounting(cp05_query, f"{system} formal CP05")
        old.validate_freeze_chain(attempt, work, "formal", system, cp05_path)
        stages = {"cp01": old.collect_stage(cp01_stage, 80_000, system),
                  "cp05": old.collect_stage(cp05_stage, 320_000, system)}
        query_points = [point for checkpoint, gate in (("cp00", cp00_query), ("cp01", cp01_query),
                                                        ("cp05", cp05_query))
                        for point in old.collect_queries(gate, checkpoint)]
        formal[system] = {"status": "pass", "run": R10_RUN, "attempt": "trajectory-cp05-10",
            "completion_marker": identity(attempt / "CUMULATIVE_TRAJECTORY_OK"),
            "stages": stages, "query_summary": old.aggregate_queries(query_points),
            "checkpoint_evidence": {"cp01": identity(cp01_path), "cp05": identity(cp05_path)},
            "frozen_clone_revalidated": True}

    disk_path = r11_result / "DiskANN/stale-cp05-11/stale_control.json"
    disk = load(disk_path)
    require(disk.get("schema") == "dynamic-vamana-w1-diskann-cp05-stale-r11-v1"
            and disk.get("status") == "pass"
            and disk.get("classification") == "stale-static negative control"
            and disk.get("cp00_base_content_preserved") is True
            and disk.get("cp00_base_mode_preserved") is True,
            "R11 DiskANN stale result invalid")
    require((r11_result / "DiskANN/stale-cp05-11/DISKANN_STALE_CP05_OK").is_file(),
            "R11 DiskANN completion marker absent")
    require(len(disk.get("points", [])) == 6
            and {(point["L"], point["repetition"]) for point in disk["points"]}
            == {(l_value, repetition) for l_value in (29, 53) for repetition in (1, 2, 3)},
            "R11 DiskANN point cardinality mismatch")
    disk_cp05 = [{"checkpoint": "cp05", "L": l_value,
        "median_recall_at_10": statistics.median(
            point["recall_at_10"] for point in disk["points"] if point["L"] == l_value)}
        for l_value in (29, 53)]
    prior = load(root / "results/pilot3_sift10m_w1_r07/DiskANN/stale-cp00-07/stale_control.json")
    disk_cp01 = [{"checkpoint": "cp01", "L": l_value,
        "median_recall_at_10": statistics.median(
            point["recall_at_10"] for point in prior["points"] if point["L"] == l_value),
        "provenance": str((root / "results/pilot3_sift10m_w1_r07/DiskANN/stale-cp00-07").resolve())}
        for l_value in (29, 53)]
    disk_trajectory = old.parse_historical_disk_cp00(root) + disk_cp01 + disk_cp05

    closure = {"schema": SCHEMA, "status": "pass", "classification": "composed closure",
        "not_a_single_execution_attempt": True,
        "composition": "R10 accepted dynamic systems + R11 DiskANN stale-static negative control",
        "decision_boundary": "CP05 closure only; CP10/CP20 remain HOLD",
        "R10_dynamic": {"run": R10_RUN, "terminal_status": "stopped_failed",
            "accepted_scope": "DGAI/OdinANN replay and formal CP00->CP01->CP05",
            "execution_manifest": identity(r10_execution_path), "stop_preservation": identity(r10_stop_path),
            "post_R11_preservation": identity(r10_post_path), "formal": formal,
            "modified_by_R11": False},
        "R11_DiskANN": {"run": R11_RUN, "attempt": "stale-cp05-11",
            "execution_manifest_before_completion": identity(r11_execution_path),
            "preflight": identity(r11_preflight_path), "stale_control": identity(disk_path),
            "result": disk},
        "diskann_stale_trajectory": disk_trajectory,
        "held_checkpoints": ["CP10", "CP20"]}
    write_new(closure_path, json.dumps(closure, indent=2) + "\n")

    lines = ["# Dynamic Vamana W1 CP05 R10 + R11 Composed Closure", "", "## 裁决", "",
        "本closure由两个不可混同的run组成：R10提供已接受的DGAI/OdinANN replay与formal `CP00→CP01→CP05`；R11仅提供DiskANN冻结CP00 index对CP05 GT的stale-static negative control。R10仍保持`stopped_failed`，没有被伪装为单次完整成功。", "",
        "## Dynamic update成本（R10）", "", "| System | Stage | Replacements | Ingest s | Repl/s | E2E read GiB | E2E write GiB | Peak RSS GiB |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for system in ("DGAI", "OdinANN"):
        for checkpoint in ("cp01", "cp05"):
            stage = formal[system]["stages"][checkpoint]
            lines.append(f"| {system} | {checkpoint.upper()} | {stage['incremental_replacements']:,} | {stage['phases']['ingest']['wall_seconds']:.3f} | {stage['replacements_per_second']:.3f} | {stage['phases']['end_to_end']['rbytes']/2**30:.3f} | {stage['phases']['end_to_end']['wbytes']/2**30:.3f} | {stage['peak_process_tree_rss_bytes']/2**30:.3f} |")
    lines += ["", "## Dynamic query（R10）", "", "| System | Checkpoint | L | Median Recall@10 | Median QPS | Median P99 us | Median mean I/O |", "|---|---:|---:|---:|---:|---:|---:|"]
    for system in ("DGAI", "OdinANN"):
        for row in formal[system]["query_summary"]:
            lines.append(f"| {system} | {row['checkpoint'].upper()} | {row['L']} | {row['median_recall_at_10']:.6f} | {row['median_qps']:.3f} | {row['median_p99_latency_us']:.3f} | {row['median_mean_ios']:.3f} |")
    lines += ["", "## DiskANN stale-static trajectory（R11 closure）", "", "| Checkpoint | L | Median Recall@10 |", "|---|---:|---:|"]
    for row in disk_trajectory:
        lines.append(f"| {row['checkpoint'].upper()} | {row['L']} | {row['median_recall_at_10']:.6f} |")
    lines += ["", "R11使用accepted P1R07 DiskANN base，`L={29,53}`、`Tq=1`、每点3次；结果形状、sentinel、top-10唯一性、NVMe read、OOM/fatal和base content/mode preservation均通过。stale结果允许包含CP05已删除ID，不与动态更新吞吐量排名。", "",
        "## 证据边界", "", f"机器可读closure：`{closure_path}`。R10 stop与post-R11 preservation均PASS；R10 dynamic evidence与frozen clones已重新验证且未被R11修改。CP10/CP20继续HOLD。", ""]
    write_new(args.output_report, "\n".join(lines))
    return closure


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    for name in ("root", "r10-result", "r10-formal", "r11-result", "r11-preflight",
                 "r10-post-preservation", "closure-manifest", "output-report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    return parser


def main() -> None:
    try:
        validate(parser().parse_args())
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
