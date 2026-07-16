#!/usr/bin/env python3
"""Fail-closed preflight for data-only W1 trajectory preparation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from w1_process_identity import ancestor_chain, load_policy, scan

R07_REPORT_SHA = "87f9fa6377b5aa831dba2c4c9af748146f949f08b5bd31c11711419bddd234e4"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def device(path: Path) -> str:
    return subprocess.run(["findmnt", "-rn", "-T", str(path), "-o", "MAJ:MIN"], check=True,
                          text=True, capture_output=True).stdout.splitlines()[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--artifact-manifest", type=Path, required=True)
    parser.add_argument("--process-tests", type=Path, required=True)
    parser.add_argument("--sanity", type=Path, required=True)
    parser.add_argument("--audited-report", type=Path, required=True)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(); result = root / "results/pilot3_sift10m_w1_trajectory_prep"
    trajectory = root / "datasets/sift10m/w1_trajectory"; gt = root / "groundtruth/sift10m/w1_trajectory"
    if args.output.exists() or trajectory.exists() or gt.exists():
        raise SystemExit("trajectory preparation target freshness failed")
    actual = {p.resolve().relative_to(result).as_posix() for p in result.rglob("*") if p.is_file() or p.is_symlink()}
    expected = {path.resolve().relative_to(result).as_posix() for path in (args.process_tests, args.sanity, args.execution)}
    if actual != expected:
        raise SystemExit(f"preflight result whitelist mismatch: {actual} != {expected}")
    process_tests = json.loads(args.process_tests.read_text())
    sanity = json.loads(args.sanity.read_text())
    if process_tests.get("status") != "pass" or sanity.get("status") != "pass" or sanity.get("scratch_removed_after_report") is not True:
        raise SystemExit("process identity/trajectory sanity fixtures failed")
    attempt = json.loads(args.execution.read_text())
    if (attempt.get("status") != "preflighting" or attempt.get("controller_pid") != int(os.environ.get("W1_CONTROLLER_PID", "0"))
            or attempt.get("launcher_realpath") != str(args.launcher.resolve())
            or attempt.get("launcher_sha256") != sha(args.launcher)):
        raise SystemExit("trajectory attempt/controller/launcher identity invalid")
    r07 = root / "results/pilot3_sift10m_w1_r07"
    execution = json.loads((r07 / "execution_manifest.json").read_text())
    if execution.get("status") != "complete" or not (r07 / "FORMAL_W1_COMPLETE").is_file():
        raise SystemExit("accepted R07 completion evidence absent")
    original_report = Path("/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-16/dynamic_vamana_w1_composed_one_percent_canary_r07_results_0716.md")
    if sha(original_report) != R07_REPORT_SHA or not args.audited_report.is_file():
        raise SystemExit("R07 original/audited report identity invalid")
    cp01 = root / "datasets/sift10m/w1_cp01"
    prior = json.loads((r07 / "preflight/execution_preflight.json").read_text())
    current = {}
    if {p.name for p in cp01.iterdir() if p.is_file()} != set(prior["cp01_artifacts"]):
        raise SystemExit("CP01 artifact set changed")
    for name, expected_identity in prior["cp01_artifacts"].items():
        path = cp01 / name; st = path.stat()
        identity = {"size_bytes": st.st_size, "sha256": sha(path), "mtime_ns": st.st_mtime_ns}
        if identity != expected_identity: raise SystemExit(f"frozen CP01 changed: {name}")
        current[name] = identity
    artifact = json.loads(args.artifact_manifest.read_text()); formal = artifact["formal_inputs"]
    identities = {"full_corpus": root / "datasets/sift10m/full_10m.bin",
                  "query": root / "datasets/sift10m/query.bin",
                  "active_cp00_tags": root / "datasets/sift10m/active_cp00.tags.bin",
                  "compute_groundtruth": root / "build/DiskANN/apps/utils/compute_groundtruth",
                  "openblas": root / "build/openblas-install/lib/libopenblas.so"}
    expected_hash = {"full_corpus": formal["full_corpus"]["sha256"], "query": formal["query"]["sha256"],
                     "active_cp00_tags": formal["active_cp00_tags"]["sha256"],
                     "compute_groundtruth": formal["compute_groundtruth"]["sha256"]}
    frozen = {}
    for name, path in identities.items():
        if name in expected_hash and sha(path) != expected_hash[name]: raise SystemExit(f"formal input identity changed: {name}")
        frozen[name] = {"realpath": str(path.resolve()), "size_bytes": path.stat().st_size, "sha256": sha(path), "mtime_ns": path.stat().st_mtime_ns}
    expected_device = os.environ.get("ATLAS_NVME_MAJMIN", "259:10")
    checked_paths = [root, root / "datasets/sift10m", root / "groundtruth/sift10m", root / "results", root / "tmp"]
    if any(device(path) != expected_device for path in checked_paths): raise SystemExit("trajectory path is not on project NVMe")
    free = shutil.disk_usage(root).free
    if free < 100 * 1024**3: raise SystemExit("trajectory 100 GiB free-space guard failed")
    memory_available = next(int(line.split()[1]) * 1024 for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:"))
    if memory_available < 32 * 1024**3: raise SystemExit("trajectory 32 GiB available-memory guard failed")
    expected_tmp = str((root / "tmp/w1_trajectory_prep").resolve())
    if os.environ.get("TMPDIR") != expected_tmp: raise SystemExit("trajectory TMPDIR is not on project NVMe")
    if os.environ.get("W1_GLOBAL_LOCK_HELD") != "1": raise SystemExit("global lock marker absent")
    allowed_session = os.environ.get("W1_ALLOWED_SESSION", "")
    sessions = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}"], text=True, capture_output=True).stdout.splitlines()
    stale_sessions = [name for name in sessions if "w1" in name.lower() and name != allowed_session]
    lineage = ancestor_chain(); identity = scan(load_policy(root, args.artifact_manifest.resolve(), Path(__file__).resolve().parent), set(lineage))
    if stale_sessions or identity["status"] != "pass": raise SystemExit(f"stale W1 state: {stale_sessions} {identity}")
    launcher_text = args.launcher.read_text()
    forbidden_calls = ["w1_run_system_canary.sh", "w1_dgai_1pct_canary.sh", "w1_odin_1pct_canary.sh", "w1_diskann_stale_control.sh", "w1_clone_base.sh"]
    if any(token in launcher_text for token in forbidden_calls): raise SystemExit("trajectory launcher contains forbidden index execution call")
    report = {"schema": "dynamic-vamana-w1-trajectory-preflight-v1", "status": "pass",
              "r07_execution_sha256": sha(r07 / "execution_manifest.json"), "r07_report_sha256": sha(original_report),
              "audited_report_sha256": sha(args.audited_report), "cp01_artifacts": current,
              "trajectory_sanity_sha256": sha(args.sanity),
              "execution_attempt_initial_sha256": sha(args.execution),
              "formal_inputs": frozen, "artifact_manifest_sha256": sha(args.artifact_manifest),
              "experiment_device": expected_device, "free_bytes": free, "memory_available_bytes": memory_available,
              "tmpdir": expected_tmp, "global_lock_held": True, "controller_lineage": lineage,
              "process_identity_scan": identity, "other_w1_sessions": stale_sessions,
              "new_targets_absent": True, "dynamic_index_execution_forbidden": True}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__": main()
