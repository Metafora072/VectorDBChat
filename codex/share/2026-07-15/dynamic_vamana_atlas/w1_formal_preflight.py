#!/usr/bin/env python3
"""Read-only SIFT10M W1 preflight; it never creates CP01 data or clones an index."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def directory_manifest_digest(root: Path) -> tuple[str, int, int]:
    aggregate = hashlib.sha256()
    count = total = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        line = f"{rel}\t{size}\t{digest(path)}\n".encode()
        aggregate.update(line)
        count += 1
        total += size
    return aggregate.hexdigest(), count, total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--artifact-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-canary-passed", action="store_true")
    parser.add_argument("--execution", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads(args.artifact_manifest.read_text())

    bases = {
        "DGAI": root / "formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index",
        "OdinANN": root / "formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index",
        "DiskANN": root / "formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index",
    }
    cp01 = root / "datasets/sift10m/w1_cp01"
    formal_root = root / "formal/pilot3_sift10m_w1"
    formal_result = root / "results/pilot3_sift10m_w1"
    inputs = {
        "full_corpus": root / "datasets/sift10m/full_10m.bin",
        "query": root / "datasets/sift10m/query.bin",
        "active_cp00_vectors": root / "datasets/sift10m/active_cp00.bin",
        "active_cp00_tags": root / "datasets/sift10m/active_cp00.tags.bin",
        "gt_cp00": root / "groundtruth/sift10m/pilot3_sift10m_p1r07/gt_cp00",
        "source_trace": root / "datasets/sift10m/replace_new_trace.csv",
        "compute_groundtruth": root / "build/DiskANN/apps/utils/compute_groundtruth",
        "diskann_query": root / "build/DiskANN/apps/search_disk_index",
        "notification_helper": Path(__file__).resolve().parent / "formal/notify_owner.sh",
    }
    for name, path in {**bases, **inputs}.items():
        if not path.exists():
            raise SystemExit(f"missing preflight input {name}: {path}")
    gt_cp01 = root / "groundtruth/sift10m/w1"
    for target in (cp01, gt_cp01, formal_root):
        if target.exists():
            raise SystemExit(f"formal output target already exists: {target}")
    if args.execution:
        forbidden_results = [formal_result / system for system in ("DGAI", "OdinANN", "DiskANN")]
        if any(path.exists() for path in forbidden_results):
            raise SystemExit("formal attempt/stale-control result already exists")
        allowed_session = os.environ.get("W1_ALLOWED_SESSION", "")
        sessions = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}"], text=True, capture_output=True).stdout.splitlines()
        stale_sessions = [name for name in sessions if "w1" in name.lower() and name != allowed_session]
        scopes = subprocess.run(["systemctl", "list-units", "--type=scope", "--state=running", "--no-legend", "--plain"], text=True, capture_output=True).stdout.splitlines()
        stale_scopes = [line for line in scopes if "dv-w1" in line.lower()]
        ancestors: set[int] = set()
        pid = os.getpid()
        while pid > 1:
            ancestors.add(pid)
            try:
                pid = int(Path(f"/proc/{pid}/stat").read_text().split()[3])
            except (FileNotFoundError, ValueError, IndexError):
                break
        process_rows = subprocess.run(["ps", "-eo", "pid=,args="], check=True, text=True, capture_output=True).stdout.splitlines()
        pattern = re.compile(r"w1_canary|w1_run_system_canary|w1_diskann_stale_control")
        stale_processes = []
        for row in process_rows:
            fields = row.strip().split(maxsplit=1)
            if len(fields) == 2 and int(fields[0]) not in ancestors and pattern.search(fields[1]):
                stale_processes.append(row.strip())
        if stale_sessions or stale_scopes or stale_processes:
            raise SystemExit(f"existing W1 execution state: sessions={stale_sessions}, scopes={stale_scopes}, processes={stale_processes}")
    else:
        stale_sessions = stale_scopes = stale_processes = []

    device_lines = subprocess.run(
        ["findmnt", "-rn", "-T", str(root), "-o", "MAJ:MIN"],
        check=True, text=True, capture_output=True,
    ).stdout.splitlines()
    device = device_lines[0].strip() if device_lines else ""
    expected_device = os.environ.get("ATLAS_NVME_MAJMIN", "259:10")
    if device != expected_device:
        raise SystemExit(f"wrong experiment device: {device}")
    free = shutil.disk_usage(root).free
    if free < 150_000_000_000:
        raise SystemExit("free-space guard failed")
    if not args.runtime_canary_passed:
        raise SystemExit("systemd/NUMA/cgroup runtime canary did not pass")

    base_checks: dict[str, object] = {}
    for system, path in bases.items():
        expected = manifest["systems"][system]["formal_base"]
        actual_hash, file_count, total_bytes = directory_manifest_digest(path)
        valid = (
            str(path.resolve()) == str(Path(expected["realpath"]).resolve())
            and actual_hash == expected["manifest_sha256"]
            and (path / "IMMUTABLE_BASE_OK").is_file()
        )
        if not valid:
            raise SystemExit(f"{system} frozen F0 base identity mismatch")
        base_checks[system] = {
            "realpath": str(path.resolve()),
            "manifest_sha256": actual_hash,
            "file_count": file_count,
            "total_bytes": total_bytes,
            "valid": True,
        }

    input_checks = {
        name: {
            "realpath": str(path.resolve()),
            "size_bytes": path.stat().st_size,
            "sha256": digest(path),
        }
        for name, path in inputs.items()
        if path.is_file()
    }
    expected_inputs = manifest["formal_inputs"]
    for name in ("full_corpus", "query", "active_cp00_vectors", "active_cp00_tags", "gt_cp00", "source_trace", "compute_groundtruth"):
        if input_checks[name]["sha256"] != expected_inputs[name]["sha256"]:
            raise SystemExit(f"formal input hash mismatch: {name}")
    diskann = manifest["systems"]["DiskANN"]
    if input_checks["diskann_query"]["sha256"] != diskann["binary_sha256"]["search_disk_index"]:
        raise SystemExit("DiskANN query binary identity mismatch")
    frozen_binaries = {}
    for system in ("DGAI", "OdinANN"):
        frozen_binaries[system] = {}
        for name, value in manifest["systems"][system]["canonical_install"].items():
            path = Path(value).resolve()
            actual = digest(path)
            expected = manifest["systems"][system]["binary_sha256"][name]
            if actual != expected:
                raise SystemExit(f"{system} canonical binary hash mismatch: {name}")
            frozen_binaries[system][name] = {"realpath": str(path), "sha256": actual}

    artifact_map = {
        "micro": {
            "trace": "trace.bin",
            "expected_active_tags": "active.tags.bin",
            "probe_queries": "probes.bin",
            "probe_spec": "probes.json",
            "full_corpus": str((root / "datasets/sift1m/full_1m.bin").resolve()),
        },
        "formal": {
            "trace": str((cp01 / "replace_cp01_80k.bin").resolve()),
            "expected_active_tags": str((cp01 / "active_cp01.tags.bin").resolve()),
            "probe_queries": str((cp01 / "visibility_probes.bin").resolve()),
            "probe_spec": str((cp01 / "visibility_probes.json").resolve()),
            "active_vectors": str((cp01 / "active_cp01.bin").resolve()),
            "full_corpus": str(inputs["full_corpus"].resolve()),
            "operation_count": 80_000,
            "probe_positions": 9,
        },
    }
    result = {
        "schema": "dynamic-vamana-w1-formal-preflight-v2",
        "status": "pass",
        "read_only": True,
        "execution_snapshot": args.execution,
        "experiment_device": device,
        "free_bytes": free,
        "global_lock_held": os.environ.get("W1_GLOBAL_LOCK_HELD") == "1",
        "runtime_canary": {"systemd_scope": True, "numa_binding": True, "cgroup_accounting": True},
        "notification": {
            "enabled": os.environ.get("ATLAS_NOTIFY_EMAIL", "1") == "1",
            "helper_realpath": str(inputs["notification_helper"].resolve()),
        },
        "formal_output_targets": {
            "cp01": {"realpath": str(cp01), "exists": cp01.exists()},
            "gt_cp01": {"realpath": str(gt_cp01), "exists": gt_cp01.exists()},
            "attempt_root": {"realpath": str(formal_root), "exists": formal_root.exists()},
            "result_root_before_preflight": {"realpath": str(formal_result), "may_contain_preflight_only": True},
        },
        "artifact_map": artifact_map,
        "formal_bases": base_checks,
        "formal_inputs": input_checks,
        "frozen_binaries": frozen_binaries,
        "stale_execution_checks": {"allowed_session": os.environ.get("W1_ALLOWED_SESSION", ""),
                                    "other_w1_sessions": stale_sessions, "running_w1_scopes": stale_scopes,
                                    "running_w1_workers": stale_processes},
    }
    if not result["global_lock_held"]:
        raise SystemExit("global lock marker absent")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
