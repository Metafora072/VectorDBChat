#!/usr/bin/env python3
"""Fail-closed preflight for the R10 + DiskANN-only R11 composed closure."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "dynamic-vamana-w1-cp05-diskann-closure-r11-preflight-v1"
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
    require(path.is_file(), f"identity target is not a regular file: {path}")
    info = path.stat()
    return {"realpath": str(path), "size_bytes": info.st_size, "sha256": sha256(path),
            "mtime_ns": info.st_mtime_ns, "mode": stat.S_IMODE(info.st_mode),
            "uid": info.st_uid, "gid": info.st_gid, "device": info.st_dev, "inode": info.st_ino}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def verify_identity(record: object, path: Path, label: str) -> dict[str, Any]:
    require(isinstance(record, dict), f"{label} identity absent")
    live = identity(path)
    required = set(live)
    require(required.issubset(record) and all(record[key] == live[key] for key in required),
            f"{label} identity changed")
    return live


def mount_device(path: Path) -> str:
    return subprocess.check_output(
        ["findmnt", "-no", "MAJ:MIN", "-T", str(path.resolve(strict=True))], text=True
    ).strip()


def available_memory() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise ValueError("MemAvailable absent")


def write_new(path: Path, payload: dict[str, Any]) -> None:
    require(not path.exists() and not path.is_symlink(), f"output is not fresh: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with temporary.open("x") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def validate(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve(strict=True)
    r10_result = args.r10_result.resolve(strict=True)
    r10_formal = args.r10_formal.resolve(strict=True)
    r10_replay_formal = args.r10_replay_formal.resolve(strict=True)
    result = args.r11_result.resolve(strict=False)
    output = args.output.resolve(strict=False)
    base = args.base_root.resolve(strict=True)
    query = args.query.resolve(strict=True)
    gt = args.cp05_gt.resolve(strict=True)
    artifact_path = args.artifact_manifest.resolve(strict=True)
    runtime_path = args.runtime_manifest.resolve(strict=True)
    base_content = args.base_content.resolve(strict=True)
    base_mode = args.base_mode.resolve(strict=True)
    r10_revalidation_path = args.r10_preservation_revalidation.resolve(strict=True)

    require(r10_result == root / f"results/{R10_RUN}", "R10 result capability mismatch")
    require(r10_formal == root / f"formal/{R10_RUN}", "R10 formal capability mismatch")
    require(r10_replay_formal == root / "formal/pilot3_w1_cp05_trajectory_replay_r10",
            "R10 replay-formal capability mismatch")
    require(result == root / f"results/{R11_RUN}", "R11 result capability mismatch")
    require(output == result / "preflight/execution_preflight.json", "R11 preflight output mismatch")
    require(base == root / "formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index",
            "R11 must use the accepted P1R07 DiskANN base")
    require(query == root / "datasets/sift10m/query.bin"
            and gt == root / "groundtruth/sift10m/w1_trajectory/cp05/gt_cp05",
            "R11 query/CP05-GT capability mismatch")

    r10_execution_path = r10_result / "execution_manifest.json"
    r10_execution = load(r10_execution_path)
    require((r10_execution.get("schema"), r10_execution.get("status"),
             r10_execution.get("stopped_phase"), r10_execution.get("exit_code"))
            == ("dynamic-vamana-w1-cp05-cumulative-r10-execution-v1", "stopped_failed",
                "diskann_cp05_stale_control", 1), "R10 terminal execution identity mismatch")
    r10_preflight_path = r10_result / "preflight/execution_preflight.json"
    r10_preflight = load(r10_preflight_path)
    require(r10_preflight.get("schema") == "dynamic-vamana-w1-cp05-cumulative-r10-preflight-v1"
            and r10_preflight.get("status") == "pass", "R10 execution preflight is not PASS")
    require(r10_execution.get("preflight_realpath") == str(r10_preflight_path)
            and r10_execution.get("preflight_sha256") == sha256(r10_preflight_path),
            "R10 execution/preflight anti-tamper anchor mismatch")
    r10_preservation_path = r10_result / "preflight/preservation_after_stop.json"
    r10_preservation = load(r10_preservation_path)
    require(r10_preservation.get("schema") == "dynamic-vamana-w1-cp05-cumulative-r10-preservation-v1"
            and r10_preservation.get("status") == "pass"
            and r10_preservation.get("phase") == "diskann_cp05_stale_control"
            and not r10_preservation.get("mismatches"), "R10 stop preservation is not PASS")
    r10_revalidation = load(r10_revalidation_path)
    require(r10_revalidation.get("schema") == "dynamic-vamana-w1-cp05-cumulative-r10-preservation-v1"
            and r10_revalidation.get("status") == "pass"
            and not r10_revalidation.get("mismatches"), "R10 launch-time preservation revalidation failed")

    protected: dict[str, dict[str, Any]] = {
        "R10_execution_manifest": identity(r10_execution_path),
        "R10_execution_preflight": identity(r10_preflight_path),
        "R10_stop_preservation": identity(r10_preservation_path),
    }
    stage_evidence: dict[str, dict[str, Any]] = {}
    completion_markers: dict[str, dict[str, Any]] = {}
    formal_validations: dict[str, dict[str, Any]] = {}
    freeze_evidence: dict[str, dict[str, Any]] = {}
    for system in ("DGAI", "OdinANN"):
        for mode, attempt, work in (
            ("replay", r10_result / f"replay/{system}/sequential-cp80-10",
             r10_replay_formal / f"{system}/sequential-cp80-10"),
            ("formal", r10_result / f"{system}/trajectory-cp05-10",
             r10_formal / f"{system}/trajectory-cp05-10"),
        ):
            marker = attempt / "CUMULATIVE_TRAJECTORY_OK"
            require(marker.is_file(), f"R10 {system} {mode} completion marker absent")
            completion_markers[f"{mode}_{system}"] = identity(marker)
            for checkpoint in ("cp01", "cp05"):
                evidence_path = attempt / f"stages/{checkpoint}/stage_evidence.json"
                evidence = load(evidence_path)
                require(evidence.get("schema") == "dynamic-vamana-w1-cumulative-stage-evidence-v1"
                        and evidence.get("status") == "pass" and evidence.get("system") == system
                        and evidence.get("checkpoint") == checkpoint,
                        f"R10 {system} {mode} {checkpoint} stage evidence invalid")
                stage_evidence[f"{mode}_{system}_{checkpoint}"] = identity(evidence_path)
            freeze_path = attempt / "checkpoints/cp05/cp05_freeze_evidence.json"
            freeze_evidence[f"{mode}_{system}"] = identity(freeze_path)
            require((work / "IMMUTABLE_TRAJECTORY_CP05_OK").is_file(),
                    f"R10 {system} {mode} frozen-clone marker absent")

        validations = sorted((r10_result / f"{system}/trajectory-cp05-10/queries").glob("**/*.validation.json"))
        require(len(validations) == 18, f"R10 {system} formal validation count is not 18")
        for path in validations:
            row = load(path)
            require(row.get("schema") == "dynamic-vamana-query-result-validation-v1"
                    and row.get("query_count") == 10_000 and row.get("k") == 10
                    and row.get("all_result_ids_active") is True
                    and row.get("invalid_or_inactive_ids") == 0,
                    f"R10 formal query validation failed: {path}")
            formal_validations[f"{system}/{path.relative_to(r10_result / f'{system}/trajectory-cp05-10/queries')}"] = identity(path)

    require(len(stage_evidence) == 8 and len(completion_markers) == 4
            and len(formal_validations) == 36 and len(freeze_evidence) == 4,
            "R10 dynamic evidence cardinality mismatch")
    require(not (r10_result / "DiskANN/stale-cp05-10/stale_control.json").exists(),
            "R10 unexpectedly contains an accepted DiskANN stale result")

    lineage = r10_preflight.get("diskann_lineage")
    require(isinstance(lineage, dict) and lineage.get("status") == "pass"
            and lineage.get("base_root_realpath") == str(base), "R10 DiskANN lineage/base mismatch")
    for key, path in (("runtime_manifest", runtime_path), ("base_content_manifest", Path(lineage["base_content_manifest"]["realpath"])),
                      ("base_mode_manifest", Path(lineage["base_mode_manifest"]["realpath"]))):
        verify_identity(lineage[key], path, f"R10 DiskANN {key}")
    verify_identity(r10_preflight["artifact_manifest"], artifact_path, "R10 artifact manifest")
    verify_identity(r10_preflight["protected_artifacts"]["query"], query, "R10 formal query")
    verify_identity(r10_preflight["protected_artifacts"]["cp05_gt"], gt, "R10 CP05 GT")
    require(base_content.read_bytes() == Path(lineage["base_content_manifest"]["realpath"]).read_bytes(),
            "live P1R07 DiskANN base content differs from accepted lineage")
    require(base_mode.read_bytes() == Path(lineage["base_mode_manifest"]["realpath"]).read_bytes(),
            "live P1R07 DiskANN base mode differs from accepted lineage")
    artifact = load(artifact_path)
    require(Path(artifact["systems"]["DiskANN"]["formal_base"]["realpath"]).resolve(strict=True) == base,
            "artifact manifest DiskANN base differs from accepted P1R07 base")

    if result.exists():
        require({entry.name for entry in result.iterdir()} <= {"preflight"}, "R11 result is not fresh")
    require(not args.report.exists() and not args.closure_manifest.exists(), "R11 closure outputs are not fresh")
    require(os.environ.get("W1_GLOBAL_LOCK_HELD") == "1", "global W1 lock marker absent")
    require(mount_device(root) == args.device and mount_device(result.parent) == args.device,
            "R11 result is not on the project NVMe")
    free = shutil.disk_usage(root).free
    memory = available_memory()
    require(free >= 64 * 1024**3 and memory >= 8 * 1024**3, "R11 space/memory guard failed")

    report = {"schema": SCHEMA, "status": "pass", "run": R11_RUN,
        "attempt": "stale-cp05-11", "classification": "DiskANN-only fresh continuation",
        "r10": {"run": R10_RUN, "execution_manifest": protected["R10_execution_manifest"],
            "execution_preflight": protected["R10_execution_preflight"],
            "stop_preservation": protected["R10_stop_preservation"],
            "launch_time_preservation_revalidation": identity(r10_revalidation_path),
            "completion_markers": completion_markers, "stage_evidence": stage_evidence,
            "formal_query_validations": formal_validations, "freeze_evidence": freeze_evidence,
            "dynamic_results_accepted": True, "diskann_result_absent": True},
        "diskann": {"base_root": str(base), "base_content_before": identity(base_content),
            "base_mode_before": identity(base_mode), "lineage": lineage,
            "artifact_manifest": identity(artifact_path), "runtime_manifest": identity(runtime_path),
            "query": identity(query), "cp05_gt": identity(gt), "L": [29, 53], "Tq": 1,
            "repetitions": 3, "stale_result_ids_may_be_inactive_at_cp05": True},
        "fresh_targets": {"result_root": str(result), "report": str(args.report.resolve(strict=False)),
            "closure_manifest": str(args.closure_manifest.resolve(strict=False))},
        "experiment_device": args.device, "free_bytes": free, "memory_available_bytes": memory,
        "held_checkpoints": ["CP10", "CP20"]}
    write_new(output, report)
    return report


def self_test(args: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory(dir=args.scratch) as tmp:
        root = Path(tmp); sample = root / "sample"; sample.write_bytes(b"r11")
        record = identity(sample)
        require(verify_identity(record, sample, "positive") == record, "identity positive failed")
        sample.write_bytes(b"tampered")
        rejected = False
        try:
            verify_identity(record, sample, "negative")
        except ValueError:
            rejected = True
        require(rejected, "identity tamper negative failed")
    write_new(args.output, {"schema": "dynamic-vamana-w1-cp05-diskann-r11-preflight-self-test-v1",
                            "status": "pass", "identity_positive": True, "tamper_negative": True})


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(); sub = top.add_subparsers(dest="command", required=True)
    run = sub.add_parser("validate")
    for name in ("root", "r10-result", "r10-formal", "r10-replay-formal", "r11-result",
                 "artifact-manifest", "runtime-manifest", "base-root", "base-content", "base-mode",
                 "query", "cp05-gt", "r10-preservation-revalidation", "report", "closure-manifest", "output"):
        run.add_argument(f"--{name}", type=Path, required=True)
    run.add_argument("--device", default="259:10")
    test = sub.add_parser("self-test"); test.add_argument("--scratch", type=Path, required=True)
    test.add_argument("--output", type=Path, required=True)
    return top


def main() -> None:
    args = parser().parse_args()
    try:
        self_test(args) if args.command == "self-test" else validate(args)
    except (KeyError, OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
