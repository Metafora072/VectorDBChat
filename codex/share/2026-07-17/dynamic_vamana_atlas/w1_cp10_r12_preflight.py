#!/usr/bin/env python3
"""Fail-closed preflight binding accepted R10+R11 closure to R12 inputs."""
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


def validate_live_identity(row: dict[str, object]) -> dict[str, object]:
    live = identity(Path(str(row["realpath"])))
    for key in ("realpath", "size_bytes", "sha256", "mtime_ns", "mode", "uid", "gid", "device", "inode"):
        require(row.get(key) == live[key], f"source identity changed: {live['realpath']}:{key}")
    return live


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--closure", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    r10 = root / "results/pilot3_sift10m_w1_cp05_trajectory_r10"
    r11 = root / "results/pilot3_sift10m_w1_cp05_diskann_closure_r11"
    run = root / "results/pilot3_sift10m_w1_cp10_trajectory_r12"
    formal = root / "formal/pilot3_sift10m_w1_cp10_trajectory_r12"

    closure = json.loads(args.closure.read_text())
    require(closure.get("schema") == "dynamic-vamana-w1-cp05-r10-r11-composed-closure-v1"
            and closure.get("status") == "pass" and closure.get("not_a_single_execution_attempt") is True,
            "accepted R10+R11 composed closure mismatch")
    execution = json.loads((r10 / "execution_manifest.json").read_text())
    require(execution.get("status") == "stopped_failed"
            and execution.get("phase") == "diskann_cp05_stale_control"
            and execution.get("exit_code") == 1, "R10 terminal identity mismatch")
    require(closure["R10_dynamic"]["execution_manifest"]["sha256"] == sha(r10 / "execution_manifest.json"),
            "closure/R10 manifest hash mismatch")
    r11_terminal = json.loads((r11 / "execution_manifest.json").read_text())
    require(r11_terminal.get("status") == "complete" and r11_terminal.get("phase") == "complete",
            "R11 terminal manifest is not complete")
    r11_anchor = closure["R11_DiskANN"].get("execution_manifest_before_completion")
    require(isinstance(r11_anchor, dict) and len(str(r11_anchor.get("sha256", ""))) == 64,
            "closure/R11 pre-completion manifest anchor absent")

    input_doc = json.loads(args.input_manifest.read_text())
    require(input_doc.get("schema") == "dynamic-vamana-w1-cp10-r12-input-v1"
            and input_doc.get("status") == "pass"
            and input_doc.get("master_record_range") == [400_000, 800_000]
            and input_doc.get("incremental_replacements") == 400_000
            and input_doc.get("cp05_prefix_plus_delta_equals_cp10_prefix") is True
            and input_doc.get("cp05_active_plus_delta_equals_cp10_active") is True,
            "R12 derived input manifest mismatch")
    source_rows = input_doc.get("sources")
    require(isinstance(source_rows, dict) and len(source_rows) >= 10, "R12 source identities absent")
    for row in source_rows.values():
        require(isinstance(row, dict), "invalid R12 source identity")
        validate_live_identity(row)

    systems: dict[str, object] = {}
    for system in ("DGAI", "OdinANN"):
        result = r10 / system / "trajectory-cp05-10"
        attempt = root / f"formal/pilot3_sift10m_w1_cp05_trajectory_r10/{system}/trajectory-cp05-10"
        freeze_path = result / "checkpoints/cp05/cp05_freeze_evidence.json"
        freeze = json.loads(freeze_path.read_text())
        require(freeze.get("schema") == "dynamic-vamana-w1-cp05-freeze-v1"
                and freeze.get("status") == "pass" and freeze.get("system") == system
                and freeze.get("checkpoint") == "cp05" and freeze.get("mode") == "formal",
                f"R10 {system} freeze verdict mismatch")
        require(Path(freeze["attempt_realpath"]).resolve() == attempt.resolve()
                and Path(freeze["root_realpath"]).resolve() == (attempt / "index").resolve(),
                f"R10 {system} freeze paths mismatch")
        require((result / "CUMULATIVE_TRAJECTORY_OK").is_file()
                and (attempt / "IMMUTABLE_TRAJECTORY_CP05_OK").is_file(),
                f"R10 {system} completion markers absent")
        stage_path = result / "stages/cp05/stage_evidence.json"
        query_path = result / "queries/cp05/query_gate.json"
        stage = json.loads(stage_path.read_text()); query = json.loads(query_path.read_text())
        require(stage.get("status") == "pass" and stage.get("checkpoint") == "cp05"
                and stage.get("delta_count") == 320_000, f"R10 {system} CP05 stage evidence mismatch")
        require(query.get("status") == "pass" and query.get("checkpoint") == "cp05"
                and len(query.get("points", [])) == 6, f"R10 {system} CP05 query evidence mismatch")
        systems[system] = {"attempt_realpath": str(attempt.resolve()), "index_root_realpath": str((attempt / 'index').resolve()),
                           "freeze_evidence": identity(freeze_path), "completion_marker": identity(result / "CUMULATIVE_TRAJECTORY_OK"),
                           "cp05_stage_evidence": identity(stage_path), "cp05_query_gate": identity(query_path)}

    gt_manifest_path = root / "groundtruth/sift10m/w1_trajectory/cp10/gt_manifest.json"
    gt_manifest = json.loads(gt_manifest_path.read_text())
    gt = root / "groundtruth/sift10m/w1_trajectory/cp10/gt_cp10"
    require(gt_manifest.get("status") == "pass"
            and gt_manifest.get("artifacts", {}).get("gt_cp10", {}).get("sha256") == sha(gt),
            "CP10 GT manifest/hash mismatch")
    active = root / "datasets/sift10m/w1_trajectory/cp10/active_cp10.tags.bin"
    require(input_doc.get("final_active_tags_sha256") == sha(active), "CP10 active-tags binding mismatch")
    disk_base = root / "formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index"
    require(disk_base.is_dir(), "accepted P1R07 DiskANN base absent")
    for target in (formal, run / "DGAI", run / "OdinANN", run / "DiskANN"):
        require(not target.exists(), f"R12 fresh target already exists: {target}")

    report = {"schema": "dynamic-vamana-w1-cp10-r12-preflight-v1", "status": "pass",
              "run": "pilot3_sift10m_w1_cp10_trajectory_r12", "cp20": "HOLD",
              "master_record_range": [400_000, 800_000], "incremental_replacements": 400_000,
              "closure_manifest": identity(args.closure), "r10_execution_manifest": identity(r10 / "execution_manifest.json"),
              "r10_execution_preflight": identity(r10 / "preflight/execution_preflight.json"),
              "r11_execution_manifest": identity(r11 / "execution_manifest.json"),
              "input_manifest": identity(args.input_manifest), "systems": systems,
              "cp10_gt_manifest": identity(gt_manifest_path), "cp10_gt": identity(gt),
              "cp10_active_tags": identity(active), "diskann_base_realpath": str(disk_base.resolve()),
              "project_device": os.environ.get("ATLAS_NVME_MAJMIN", "259:10")}
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"R12 preflight failed: {exc}") from exc
