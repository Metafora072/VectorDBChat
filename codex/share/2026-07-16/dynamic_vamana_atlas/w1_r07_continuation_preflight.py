#!/usr/bin/env python3
"""Fail-closed R07 preflight for a DiskANN-only loader-safe continuation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from w1_process_identity import ancestor_chain, load_policy, scan

GT_SHA = "4703d2d8a12c1c045c60de56819ccb058e91bc28e0f1883d18573f9917b32c28"
DISK_BINARY_SHA = "631fc53b4514fdac8325a7d789792ff6d19fb007e5442410898ec4a9505d4c3e"
TCMALLOC_SHA = "9035515aa26ebfaa2cf390291378e0ccba66175ba8291b92aa32e92f97a8b904"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_manifest(root: Path) -> dict:
    digest = hashlib.sha256()
    count = total = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        digest.update(f"{relative}\t{size}\t{sha(path)}\n".encode())
        count += 1
        total += size
    return {"realpath": str(root.resolve()), "manifest_sha256": digest.hexdigest(),
            "file_count": count, "total_bytes": total}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--artifact-manifest", type=Path, required=True)
    parser.add_argument("--process-tests", type=Path, required=True)
    parser.add_argument("--odin-freeze", type=Path, required=True)
    parser.add_argument("--odin-freeze-tsv", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, required=True)
    parser.add_argument("--loader-tests", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    result = root / "results/pilot3_sift10m_w1_r07"
    formal = root / "formal/pilot3_sift10m_w1_r07"
    expected_files = {path.resolve().relative_to(result).as_posix() for path in
                      (args.process_tests, args.odin_freeze, args.odin_freeze_tsv, args.runtime_manifest, args.loader_tests)}
    actual_files = {path.relative_to(result).as_posix() for path in result.rglob("*") if path.is_file() or path.is_symlink()}
    if args.output.exists() or formal.exists() or actual_files != expected_files:
        raise SystemExit(f"R07 freshness/whitelist failed: actual={sorted(actual_files)} expected={sorted(expected_files)}")
    process_tests = json.loads(args.process_tests.read_text())
    odin_freeze = json.loads(args.odin_freeze.read_text())
    runtime = json.loads(args.runtime_manifest.read_text())
    loader_tests = json.loads(args.loader_tests.read_text())
    if not all(item.get("status") == "pass" for item in (process_tests, odin_freeze, runtime, loader_tests)):
        raise SystemExit("R07 prerequisite test/freeze failed")
    if odin_freeze.get("source_run") != "pilot3_sift10m_w1_r06" or odin_freeze.get("attempt") != "OdinANN/cp01-06":
        raise SystemExit("R06 Odin freeze source mismatch")
    if odin_freeze["evidence_manifest"]["sha256"] != sha(args.odin_freeze_tsv):
        raise SystemExit("R06 Odin evidence manifest mismatch")
    r06 = root / "results/pilot3_sift10m_w1_r06"
    r06_execution = json.loads((r06 / "execution_manifest.json").read_text())
    if (r06_execution.get("status"), r06_execution.get("stopped_phase"), r06_execution.get("exit_code")) != ("stopped_failed", "diskann_stale_static_control", 127):
        raise SystemExit("R06 is not the accepted DiskANN loader stop")
    if not (r06 / "OdinANN/cp01-06/FORMAL_W1_CANARY_OK").is_file():
        raise SystemExit("R06 Odin success marker absent")
    r06_disk = r06 / "DiskANN/stale-cp00-06"
    disk_files = {path.name for path in r06_disk.iterdir() if path.is_file()}
    if disk_files != {"cp00_index_manifest.tsv", "L29_r1.log", "L29_r1.resources.json"}:
        raise SystemExit(f"R06 DiskANN failure boundary changed: {sorted(disk_files)}")
    failed_resource = json.loads((r06_disk / "L29_r1.resources.json").read_text())
    failed_log = (r06_disk / "L29_r1.log").read_text(errors="replace")
    if (failed_resource.get("returncode") != 127 or failed_resource.get("peak_process_tree_rss_kb") != 0
            or failed_resource.get("peak_process_tree_io_bytes") != {"read_bytes": 0, "write_bytes": 0}
            or "libtcmalloc.so.9.9.5" not in failed_log or "cannot open shared object file" not in failed_log
            or any(r06_disk.glob("*_idx_uint32.bin")) or (r06_disk / "stale_control.json").exists()
            or (r06_disk / "DISKANN_STALE_CONTROL_OK").exists()):
        raise SystemExit("R06 DiskANN contains valid query evidence or changed failure semantics")
    r05_freeze = json.loads((r06 / "preflight/r05_dgai_freeze.json").read_text())
    r05_tsv = r06 / "preflight/r05_dgai_evidence_manifest.tsv"
    if r05_freeze.get("status") != "pass" or r05_freeze["evidence_manifest"]["sha256"] != sha(r05_tsv):
        raise SystemExit("accepted R05 DGAI freeze invalid")
    preservation = json.loads((r06 / "preflight/preservation_after_stop.json").read_text())
    if preservation.get("status") != "pass" or preservation.get("r02_gt_sha256") != GT_SHA:
        raise SystemExit("R06 preservation evidence invalid")
    prior_preflight = json.loads((r06 / "preflight/execution_preflight.json").read_text())
    cp01 = root / "datasets/sift10m/w1_cp01"
    current_cp01 = {}
    actual_cp01_names = {path.relative_to(cp01).as_posix() for path in cp01.rglob("*") if path.is_file()}
    if actual_cp01_names != set(prior_preflight["cp01_artifacts"]):
        raise SystemExit("CP01 artifact set changed")
    for name, expected in prior_preflight["cp01_artifacts"].items():
        path = cp01 / name
        stat = path.stat()
        row = {"size_bytes": stat.st_size, "sha256": sha(path), "mtime_ns": stat.st_mtime_ns}
        if row != expected:
            raise SystemExit(f"CP01 artifact changed: {name}")
        current_cp01[name] = row
    gt = root / "groundtruth/sift10m/w1_r02/gt_cp01"
    if sha(gt) != GT_SHA or gt.stat().st_mtime_ns != prior_preflight["r02_gt_mtime_ns"]:
        raise SystemExit("R02 GT changed")
    artifact = json.loads(args.artifact_manifest.read_text())
    binary = root / "build/DiskANN/apps/search_disk_index"
    query = root / "datasets/sift10m/query.bin"
    base = root / "formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index"
    base_check = tree_manifest(base)
    if (sha(binary) != DISK_BINARY_SHA or DISK_BINARY_SHA != artifact["systems"]["DiskANN"]["binary_sha256"]["search_disk_index"]
            or sha(query) != artifact["formal_inputs"]["query"]["sha256"]
            or base_check["manifest_sha256"] != artifact["systems"]["DiskANN"]["formal_base"]["manifest_sha256"]):
        raise SystemExit("DiskANN binary/query/base identity mismatch")
    tcmalloc = next((row for row in runtime["dependencies"] if row["name"] == "libtcmalloc.so.9.9.5"), None)
    if (runtime.get("not_found_dependencies") != [] or runtime["binary"]["sha256"] != DISK_BINARY_SHA
            or tcmalloc is None or tcmalloc.get("sha256") != TCMALLOC_SHA):
        raise SystemExit("DiskANN runtime dependency identity invalid")
    cgroups = loader_tests.get("cgroup", [])
    if (loader_tests.get("uid"), loader_tests.get("gid")) != (1000, 1000):
        raise SystemExit("loader tests did not run as ubuntu")
    if not any("dv-w1-r07-loader-tests.scope" in row for row in cgroups):
        raise SystemExit("loader tests did not run in the formal scope")
    if (loader_tests.get("affinity", {}).get("Cpus_allowed_list") != "0-23"
            or loader_tests.get("numa", {}).get("membind_node") != 0
            or loader_tests.get("positive_loader", {}).get("passed") is not True
            or loader_tests.get("positive_loader", {}).get("all_direct_dependencies_exact") is not True
            or loader_tests.get("negative_loader", {}).get("passed") is not True
            or loader_tests.get("negative_loader", {}).get("peak_process_tree_io_bytes") != {"read_bytes": 0, "write_bytes": 0}
            or loader_tests.get("query_smoke", {}).get("passed") is not True
            or loader_tests.get("immutable_base", {}).get("exact") is not True
            or loader_tests.get("scratch_removed_after_report") is not True):
        raise SystemExit("formal loader regression evidence invalid")
    device = subprocess.run(["findmnt", "-rn", "-T", str(root), "-o", "MAJ:MIN"], check=True,
                            text=True, capture_output=True).stdout.splitlines()[0]
    free = shutil.disk_usage(root).free
    if device != os.environ.get("ATLAS_NVME_MAJMIN", "259:10") or free < 150_000_000_000:
        raise SystemExit("R07 project NVMe/free-space gate failed")
    if os.environ.get("W1_GLOBAL_LOCK_HELD") != "1":
        raise SystemExit("R07 global lock marker absent")
    allowed_session = os.environ.get("W1_ALLOWED_SESSION", "")
    sessions = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}"], text=True,
                              capture_output=True).stdout.splitlines()
    stale_sessions = [name for name in sessions if "w1" in name.lower() and name != allowed_session]
    lineage = ancestor_chain()
    identity = scan(load_policy(root, args.artifact_manifest.resolve(), Path(__file__).resolve().parent), set(lineage))
    if stale_sessions or identity["status"] != "pass":
        raise SystemExit(f"R07 stale execution state: sessions={stale_sessions}, identity={identity}")
    if (result / "DiskANN").exists() or formal.exists():
        raise SystemExit("R07 formal experiment target already exists")
    controller_pid = int(os.environ.get("W1_CONTROLLER_PID", os.getppid()))
    if controller_pid not in lineage:
        raise SystemExit("R07 controller is not in preflight ancestry")
    lock_fd = int(os.environ.get("W1_GLOBAL_LOCK_FD", "9"))
    try:
        lock_inode = os.stat(f"/proc/{controller_pid}/fd/{lock_fd}").st_ino
    except (FileNotFoundError, PermissionError):
        raise SystemExit("R07 global-lock descriptor unavailable")
    report = {
        "schema": "dynamic-vamana-w1-r07-continuation-preflight-v1", "status": "pass",
        "run": "pilot3_sift10m_w1_r07", "attempt": "DiskANN/stale-cp00-07",
        "r05_dgai_source": {"run": "pilot3_sift10m_w1_r05", "attempt": "DGAI/cp01-05",
                            "reexecuted": False, "freeze_sha256": sha(r06 / "preflight/r05_dgai_freeze.json")},
        "r06_odinann_source": {"run": "pilot3_sift10m_w1_r06", "attempt": "OdinANN/cp01-06",
                               "reexecuted": False, "freeze_sha256": sha(args.odin_freeze)},
        "r06": {"execution_sha256": sha(r06 / "execution_manifest.json"), "status": "stopped_failed",
                 "stopped_phase": "diskann_stale_static_control", "exit_code": 127,
                 "diskann_entered_main": False, "diskann_valid_query_points": 0},
        "r02_gt_reused": True, "r02_gt_sha256": GT_SHA, "r02_gt_mtime_ns": gt.stat().st_mtime_ns,
        "cp01_reused": True, "cp01_artifacts": current_cp01,
        "diskann": {"binary_sha256": sha(binary), "query_sha256": sha(query), "base": base_check},
        "runtime_manifest": {"realpath": str(args.runtime_manifest.resolve()), "sha256": sha(args.runtime_manifest),
                             "not_found_dependencies": []},
        "loader_tests": {"realpath": str(args.loader_tests.resolve()), "sha256": sha(args.loader_tests)},
        "artifact_manifest_sha256": sha(args.artifact_manifest),
        "experiment_device": device, "free_bytes": free, "global_lock_held": True,
        "controller_identity": {"pid": controller_pid, "tmux_session": allowed_session,
                                "global_lock_fd": lock_fd, "global_lock_inode": lock_inode},
        "process_identity_scan": identity, "other_w1_sessions": stale_sessions,
        "new_targets_absent": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
