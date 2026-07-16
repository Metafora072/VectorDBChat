#!/usr/bin/env python3
"""Validate and record the exact runtime environment inside a DiskANN scope."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-scope", required=True)
    parser.add_argument("--expected-cpus", default="0-23")
    parser.add_argument("--expected-numa", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("runtime environment overwrite refused")
    manifest = json.loads(args.manifest.read_text())
    binary = args.binary.resolve()
    runtime = manifest.get("runtime_library_path")
    if manifest.get("status") != "pass" or os.environ.get("LD_LIBRARY_PATH") != runtime:
        raise SystemExit("runtime environment differs from frozen manifest")
    if (os.getuid(), os.getgid(), os.geteuid(), os.getegid()) != (1000, 1000, 1000, 1000):
        raise SystemExit("runtime environment must execute as ubuntu")
    if sha(binary) != manifest["binary"]["sha256"]:
        raise SystemExit("runtime binary identity mismatch")
    directories = [str(Path(path).resolve(strict=True)) for path in runtime.split(":")]
    if directories != manifest["runtime_library_directories"]:
        raise SystemExit("runtime directory ordering/identity mismatch")
    status = Path("/proc/self/status").read_text().splitlines()
    selected = {key: value.strip() for line in status if ":" in line
                for key, value in [line.split(":", 1)] if key in {"Cpus_allowed_list", "Mems_allowed_list"}}
    numa = subprocess.run(["numactl", "--show"], text=True, capture_output=True, check=False)
    cgroup = Path("/proc/self/cgroup").read_text().splitlines()
    if not any(args.expected_scope in row for row in cgroup):
        raise SystemExit("runtime process is not in the expected systemd scope")
    if selected.get("Cpus_allowed_list") != args.expected_cpus:
        raise SystemExit("runtime CPU affinity mismatch")
    if numa.returncode != 0 or not any(line.strip() == f"membind: {args.expected_numa}" for line in numa.stdout.splitlines()):
        raise SystemExit("runtime NUMA binding mismatch")
    report = {
        "schema": "dynamic-vamana-w1-diskann-runtime-environment-v1",
        "status": "pass",
        "ld_library_path": runtime,
        "runtime_library_directories": directories,
        "runtime_manifest": {"realpath": str(args.manifest.resolve()), "sha256": sha(args.manifest)},
        "binary": {"realpath": str(binary), "sha256": sha(binary)},
        "uid": os.getuid(), "gid": os.getgid(), "euid": os.geteuid(), "egid": os.getegid(),
        "cgroup": cgroup, "expected_scope": args.expected_scope,
        "affinity": selected,
        "numa_command": ["numactl", "--show"], "numa_returncode": numa.returncode,
        "numa_stdout": numa.stdout, "numa_stderr": numa.stderr, "membind_node": args.expected_numa,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
