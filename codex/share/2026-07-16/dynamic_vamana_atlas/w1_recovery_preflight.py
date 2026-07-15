#!/usr/bin/env python3
"""Fail-closed, read-only audit before the authorized W1 R02 recovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


def sha(path: Path) -> str:
    out = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            out.update(block)
    return out.hexdigest()


def tree_manifest(root: Path) -> dict:
    aggregate = hashlib.sha256()
    count = total = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        aggregate.update(f"{rel}\t{size}\t{sha(path)}\n".encode())
        count += 1
        total += size
    return {"realpath": str(root.resolve()), "manifest_sha256": aggregate.hexdigest(),
            "file_count": count, "total_bytes": total}


def ancestors() -> set[int]:
    found: set[int] = set()
    pid = os.getpid()
    while pid > 1:
        found.add(pid)
        try:
            pid = int(Path(f"/proc/{pid}/stat").read_text().split()[3])
        except (FileNotFoundError, ValueError, IndexError):
            break
    return found


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--artifact-manifest", type=Path, required=True)
    p.add_argument("--parent-execution", type=Path, required=True)
    p.add_argument("--cp01-reuse", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--runtime-canary-passed", action="store_true")
    a = p.parse_args()
    root = a.root.resolve()
    run = "pilot3_sift10m_w1_r02"
    targets = {
        "result": root / f"results/{run}",
        "formal": root / f"formal/{run}",
        "groundtruth": root / "groundtruth/sift10m/w1_r02",
    }
    if a.output.exists() or any(path.exists() for path in targets.values()):
        raise SystemExit(f"R02 output reuse refused: {targets}")
    if a.output.parent.parent.resolve() != targets["result"]:
        raise SystemExit("preflight output must be inside the fresh R02 result root")

    parent = json.loads(a.parent_execution.read_text())
    actual_parent_phase = parent.get("stopped_phase")
    if parent.get("status") != "stopped_failed" or actual_parent_phase not in ("gt_validation", "gt_cp01_validation"):
        raise SystemExit("parent is not the accepted GT-validation fail-closed stop")
    old_system_targets = [root / f"results/pilot3_sift10m_w1/{s}" for s in ("DGAI", "OdinANN", "DiskANN")]
    old_system_targets += [root / f"formal/pilot3_sift10m_w1/{s}" for s in ("DGAI", "OdinANN")]
    if any(path.exists() for path in old_system_targets):
        raise SystemExit("parent execution contains a system attempt or clone")
    parent_artifact = parent.get("artifact_manifest", {})
    artifact_sha = sha(a.artifact_manifest)
    if (artifact_sha != parent_artifact.get("sha256")
            or str(a.artifact_manifest.resolve()) != str(Path(parent_artifact.get("realpath", "")).resolve())):
        raise SystemExit("recovery artifact manifest differs from the parent frozen manifest")

    cp01 = json.loads(a.cp01_reuse.read_text())
    if not (cp01.get("status") == "pass" and cp01.get("read_only") is True
            and cp01.get("full_vector_tag_mapping_exact") is True
            and cp01.get("tag_zero_active") is True and cp01.get("active_cardinality") == 8_000_000):
        raise SystemExit("CP01 reuse audit did not satisfy the recovery gate")

    preserved_gt = root / "groundtruth/sift10m/w1"
    preserved_cp01 = root / "datasets/sift10m/w1_cp01"
    for path in (preserved_gt, preserved_cp01):
        if not path.is_dir():
            raise SystemExit(f"missing preserved parent artifact: {path}")
    for name in ("gt_cp01", "gt_cp01.log"):
        if not (preserved_gt / name).is_file():
            raise SystemExit(f"missing preserved failed GT evidence: {name}")
    parent_resource = root / "results/pilot3_sift10m_w1/preparation/gt_cp01_resources.json"
    parent_controller_log = root / "results/pilot3_sift10m_w1/formal_controller.log"
    if not parent_resource.is_file() or not parent_controller_log.is_file():
        raise SystemExit("missing parent GT resource/controller failure evidence")

    artifact = json.loads(a.artifact_manifest.read_text())
    bases = {
        "DGAI": root / "formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index",
        "OdinANN": root / "formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index",
        "DiskANN": root / "formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index",
    }
    base_checks = {}
    for system, path in bases.items():
        if not (path / "IMMUTABLE_BASE_OK").is_file():
            raise SystemExit(f"missing immutable marker for {system}")
        check = tree_manifest(path)
        expected = artifact["systems"][system]["formal_base"]
        if str(path.resolve()) != str(Path(expected["realpath"]).resolve()) or check["manifest_sha256"] != expected["manifest_sha256"]:
            raise SystemExit(f"frozen base mismatch: {system}")
        base_checks[system] = check

    inputs = {
        "full_corpus": root / "datasets/sift10m/full_10m.bin",
        "query": root / "datasets/sift10m/query.bin",
        "active_cp00_vectors": root / "datasets/sift10m/active_cp00.bin",
        "active_cp00_tags": root / "datasets/sift10m/active_cp00.tags.bin",
        "gt_cp00": root / "groundtruth/sift10m/pilot3_sift10m_p1r07/gt_cp00",
        "source_trace": root / "datasets/sift10m/replace_new_trace.csv",
        "compute_groundtruth": root / "build/DiskANN/apps/utils/compute_groundtruth",
        "diskann_query": root / "build/DiskANN/apps/search_disk_index",
    }
    input_checks = {}
    for name, path in inputs.items():
        if not path.is_file():
            raise SystemExit(f"missing frozen input: {name}")
        input_checks[name] = {"realpath": str(path.resolve()), "size_bytes": path.stat().st_size, "sha256": sha(path)}
    for name in ("full_corpus", "query", "active_cp00_vectors", "active_cp00_tags", "gt_cp00", "source_trace", "compute_groundtruth"):
        if input_checks[name]["sha256"] != artifact["formal_inputs"][name]["sha256"]:
            raise SystemExit(f"frozen input mismatch: {name}")
    if input_checks["diskann_query"]["sha256"] != artifact["systems"]["DiskANN"]["binary_sha256"]["search_disk_index"]:
        raise SystemExit("DiskANN query binary mismatch")
    binaries = {}
    artifact_verification = {}
    verifier = a.artifact_manifest.parent / "w1_verify_artifacts.py"
    if not verifier.is_file():
        raise SystemExit("missing frozen artifact verifier")
    for system in ("DGAI", "OdinANN"):
        binaries[system] = {}
        for name, raw in artifact["systems"][system]["canonical_install"].items():
            path = Path(raw).resolve(); actual = sha(path)
            if actual != artifact["systems"][system]["binary_sha256"][name]:
                raise SystemExit(f"canonical binary mismatch: {system}/{name}")
            binaries[system][name] = {"realpath": str(path), "sha256": actual}
        verified = subprocess.run(["python3", str(verifier), "--manifest", str(a.artifact_manifest), "--system", system,
                                   "--driver", binaries[system]["w1_canary"]["realpath"],
                                   "--query-binary", binaries[system]["search_disk_index"]["realpath"]],
                                  check=True, text=True, capture_output=True)
        artifact_verification[system] = json.loads(verified.stdout)

    device = subprocess.run(["findmnt", "-rn", "-T", str(root), "-o", "MAJ:MIN"], check=True, text=True, capture_output=True).stdout.splitlines()[0]
    if device != os.environ.get("ATLAS_NVME_MAJMIN", "259:10"):
        raise SystemExit(f"wrong experiment device: {device}")
    free = shutil.disk_usage(root).free
    if free < 150_000_000_000 or not a.runtime_canary_passed:
        raise SystemExit("capacity or runtime canary gate failed")
    if os.environ.get("W1_GLOBAL_LOCK_HELD") != "1":
        raise SystemExit("global lock marker absent")

    allowed = os.environ.get("W1_ALLOWED_SESSION", "")
    sessions = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}"], text=True, capture_output=True).stdout.splitlines()
    stale_sessions = [name for name in sessions if "w1" in name.lower() and name != allowed]
    scopes = subprocess.run(["systemctl", "list-units", "--type=scope", "--state=running", "--no-legend", "--plain"], text=True, capture_output=True).stdout.splitlines()
    stale_scopes = [line.strip() for line in scopes if "dv-w1" in line.lower()]
    lineage = ancestors(); pattern = re.compile(r"w1_canary|w1_run_system_canary|w1_diskann_stale_control|w1_gt_recovery_worker")
    stale_processes = []
    rows = subprocess.run(["ps", "-eo", "pid=,args="], check=True, text=True, capture_output=True).stdout.splitlines()
    for row in rows:
        fields = row.strip().split(maxsplit=1)
        if len(fields) == 2 and int(fields[0]) not in lineage and pattern.search(fields[1]):
            stale_processes.append(row.strip())
    if stale_sessions or stale_scopes or stale_processes:
        raise SystemExit(f"existing W1 state: sessions={stale_sessions}, scopes={stale_scopes}, processes={stale_processes}")

    report = {
        "schema": "dynamic-vamana-w1-r02-recovery-preflight-v1", "status": "pass", "read_only": True,
        "recovery_parent": "pilot3_sift10m_w1", "parent_stop_stage": "gt_validation",
        "parent_actual_stopped_phase": actual_parent_phase,
        "parent_execution": {"realpath": str(a.parent_execution.resolve()), "sha256": sha(a.parent_execution)},
        "parent_gt_resource": {"realpath": str(parent_resource.resolve()), "sha256": sha(parent_resource)},
        "parent_controller_log": {"realpath": str(parent_controller_log.resolve()), "sha256": sha(parent_controller_log)},
        "cp01_reused": True, "cp01_reuse": {"realpath": str(a.cp01_reuse.resolve()), "sha256": sha(a.cp01_reuse)},
        "preserved_failed_gt": tree_manifest(preserved_gt), "preserved_cp01": tree_manifest(preserved_cp01),
        "preserved_cp01_artifacts": cp01["artifacts"],
        "new_targets_absent_before_preflight": {name: str(path) for name, path in targets.items()},
        "old_system_attempts_absent": True, "experiment_device": device, "free_bytes": free,
        "runtime_canary": {"systemd_scope": True, "numa_binding": True, "cgroup_accounting": True},
        "formal_bases": base_checks, "formal_inputs": input_checks, "frozen_binaries": binaries,
        "artifact_manifest_parent_anchor_sha256": artifact_sha, "artifact_verification": artifact_verification,
        "stale_execution_checks": {"allowed_session": allowed, "other_w1_sessions": stale_sessions,
                                   "running_w1_scopes": stale_scopes, "running_w1_workers": stale_processes},
    }
    a.output.parent.mkdir(parents=True, exist_ok=False)
    a.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
