#!/usr/bin/env python3
"""Fail-closed preflight binding accepted R12 closure to exact R13 inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, object]:
    path = path.resolve(strict=True)
    info = path.stat()
    return {"realpath": str(path), "size_bytes": info.st_size, "sha256": sha(path),
            "mtime_ns": info.st_mtime_ns, "mode": stat.S_IMODE(info.st_mode),
            "uid": info.st_uid, "gid": info.st_gid, "device": info.st_dev, "inode": info.st_ino}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_live_identity(row: dict[str, object]) -> None:
    live = identity(Path(str(row["realpath"])))
    for key in ("realpath", "size_bytes", "sha256", "mtime_ns", "mode", "uid", "gid", "device", "inode"):
        require(row.get(key) == live[key], f"source identity changed: {live['realpath']}:{key}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--r12-continuation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve(strict=True)
    r10 = root / "results/pilot3_sift10m_w1_cp05_trajectory_r10"
    r12 = root / "results/pilot3_sift10m_w1_cp10_trajectory_r12"
    run = root / "results/pilot3_sift10m_w1_cp20_trajectory_r13"
    formal = root / "formal/pilot3_sift10m_w1_cp20_trajectory_r13"

    execution_path = r12 / "execution_manifest.json"
    continuation_path = args.r12_continuation.resolve(strict=True)
    summary_path = r12 / "summary.json"
    execution = json.loads(execution_path.read_text())
    continuation = json.loads(continuation_path.read_text())
    summary = json.loads(summary_path.read_text())
    require((execution.get("status"), execution.get("phase"), execution.get("exit_code")) ==
            ("stopped_failed", "cp10_DGAI", 1), "R12 terminal execution identity mismatch")
    require(continuation_path == (r12 / "continuation_manifest.json").resolve()
            and continuation.get("status") == "complete" and continuation.get("phase") == "complete",
            "R12 continuation is not the accepted complete closure")
    require(continuation.get("r12_execution", {}).get("sha256") == sha(execution_path),
            "R12 continuation/execution anti-tamper anchor mismatch")
    require(summary.get("schema") == "dynamic-vamana-w1-cp10-r12-summary-v1"
            and summary.get("status") == "pass", "R12 machine summary is not PASS")
    require((r12 / "FORMAL_W1_CP10_R12_COMPLETE").is_file(), "R12 completion marker absent")

    input_doc = json.loads(args.input_manifest.read_text())
    require(input_doc.get("schema") == "dynamic-vamana-w1-cp20-r13-input-v1"
            and input_doc.get("status") == "pass"
            and input_doc.get("master_record_range") == [800_000, 1_600_000]
            and input_doc.get("incremental_replacements") == 800_000
            and input_doc.get("primitive_mutations") == 1_600_000
            and input_doc.get("cp10_prefix_plus_delta_equals_cp20_prefix") is True
            and input_doc.get("cp10_active_plus_delta_equals_cp20_active") is True,
            "R13 derived input manifest mismatch")
    source_rows = input_doc.get("sources")
    require(isinstance(source_rows, dict) and len(source_rows) >= 10, "R13 source identities absent")
    for row in source_rows.values():
        require(isinstance(row, dict), "invalid R13 source identity")
        validate_live_identity(row)

    systems: dict[str, object] = {}
    for system in ("DGAI", "OdinANN"):
        result = r12 / system / "trajectory-cp10-12"
        attempt = root / f"formal/pilot3_sift10m_w1_cp10_trajectory_r12/{system}/trajectory-cp10-12"
        freeze_path = result / "checkpoints/cp10/cp10_freeze_evidence.json"
        stage_path = result / "stages/cp10/stage_evidence.json"
        query_path = result / "queries/cp10/query_gate.json"
        freeze = json.loads(freeze_path.read_text())
        stage = json.loads(stage_path.read_text())
        query = json.loads(query_path.read_text())
        require(freeze.get("schema") == "dynamic-vamana-w1-cp10-freeze-v1"
                and freeze.get("status") == "pass" and freeze.get("system") == system
                and freeze.get("checkpoint") == "cp10" and freeze.get("mode") == "formal",
                f"R12 {system} CP10 freeze verdict mismatch")
        require(Path(str(freeze["attempt_realpath"])).resolve() == attempt.resolve()
                and Path(str(freeze["root_realpath"])).resolve() == (attempt / "index").resolve(),
                f"R12 {system} frozen path mismatch")
        require((result / "CP10_TRAJECTORY_OK").is_file()
                and (attempt / "IMMUTABLE_TRAJECTORY_CP10_OK").is_file(),
                f"R12 {system} completion/freeze markers absent")
        require(stage.get("status") == "pass" and stage.get("checkpoint") == "cp10"
                and (stage.get("delta_start"), stage.get("delta_count")) == (400_000, 400_000),
                f"R12 {system} CP10 stage interval mismatch")
        require(query.get("status") == "pass" and query.get("checkpoint") == "cp10"
                and len(query.get("points", [])) == 6,
                f"R12 {system} CP10 query evidence mismatch")
        systems[system] = {
            "attempt_realpath": str(attempt.resolve()),
            "index_root_realpath": str((attempt / "index").resolve()),
            "freeze_evidence": identity(freeze_path),
            "completion_marker": identity(result / "CP10_TRAJECTORY_OK"),
            "cp10_stage_evidence": identity(stage_path),
            "cp10_query_gate": identity(query_path),
        }

    gt_manifest_path = root / "groundtruth/sift10m/w1_trajectory/cp20/gt_manifest.json"
    gt = root / "groundtruth/sift10m/w1_trajectory/cp20/gt_cp20"
    gt_manifest = json.loads(gt_manifest_path.read_text())
    require(gt_manifest.get("status") == "pass"
            and gt_manifest.get("artifacts", {}).get("gt_cp20", {}).get("sha256") == sha(gt),
            "CP20 GT manifest/hash mismatch")
    active = root / "datasets/sift10m/w1_trajectory/cp20/active_cp20.tags.bin"
    require(input_doc.get("final_active_tags_sha256") == sha(active), "CP20 active-tags binding mismatch")
    disk_base = root / "formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index"
    require(disk_base.is_dir(), "accepted P1R07 DiskANN base absent")
    r10_preflight = r10 / "preflight/execution_preflight.json"
    r10_preflight_copy = run / "preflight/r10_execution_preflight_bound.json"
    require(r10_preflight_copy.is_file() and sha(r10_preflight_copy) == sha(r10_preflight),
            "R13 readable R10 preflight copy differs from accepted source")
    for target in (formal, run / "DGAI", run / "OdinANN", run / "DiskANN"):
        require(not target.exists(), f"R13 fresh target already exists: {target}")

    report = {
        "schema": "dynamic-vamana-w1-cp20-r13-preflight-v1", "status": "pass",
        "run": "pilot3_sift10m_w1_cp20_trajectory_r13",
        "master_record_range": [800_000, 1_600_000], "incremental_replacements": 800_000,
        "r12_execution_manifest": identity(execution_path),
        "r12_continuation_manifest": identity(continuation_path),
        "r12_summary": identity(summary_path),
        "r12_completion_marker": identity(r12 / "FORMAL_W1_CP10_R12_COMPLETE"),
        "r10_execution_preflight_source": identity(r10_preflight),
        "r10_execution_preflight_readable_copy": identity(r10_preflight_copy),
        "input_manifest": identity(args.input_manifest), "systems": systems,
        "cp20_gt_manifest": identity(gt_manifest_path), "cp20_gt": identity(gt),
        "cp20_active_tags": identity(active), "diskann_base_realpath": str(disk_base.resolve()),
        "project_device": os.environ.get("ATLAS_NVME_MAJMIN", "259:10"),
        "post_cp20_action": "STOP_AND_AWAIT_REVIEW",
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"R13 preflight failed: {exc}") from exc
