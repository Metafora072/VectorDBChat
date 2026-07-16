#!/usr/bin/env python3
"""Run loader positive/negative regressions and a one-query DiskANN smoke."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

from w1_diskann_runtime_manifest import parse_ldd


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, env=env, text=True, capture_output=True, check=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--query", type=Path, required=True)
    parser.add_argument("--gt", type=Path, required=True)
    parser.add_argument("--old-tools", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.scratch.exists():
        raise SystemExit("loader test freshness guard failed")
    if os.getuid() != 1000 or os.getgid() != 1000:
        raise SystemExit("loader tests must run as ubuntu")
    numa = run(["numactl", "--show"])
    if numa.returncode != 0 or not any(line.strip() == "membind: 0" for line in numa.stdout.splitlines()):
        raise SystemExit(f"loader tests are not bound to NUMA node 0: {numa.stdout} {numa.stderr}")
    manifest = json.loads(args.manifest.read_text())
    if manifest.get("status") != "pass" or sha(args.binary) != manifest["binary"]["sha256"]:
        raise SystemExit("runtime manifest/binary invalid")
    runtime = manifest["runtime_library_path"]
    positive_env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "LD_LIBRARY_PATH": runtime,
                    "PYTHONDONTWRITEBYTECODE": "1"}
    negative_env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"}
    args.scratch.mkdir(parents=True)
    before = args.scratch / "base_before.tsv"
    after = args.scratch / "base_after.tsv"
    subprocess.run(["python3", str(args.old_tools / "w1_file_manifest.py"), "--root", str(args.base_dir),
                    "--output", str(before)], check=True, env=positive_env)
    positive = run(["ldd", str(args.binary)], positive_env)
    mappings = parse_ldd(positive.stdout + "\n" + positive.stderr)
    tcmalloc = next(row for row in manifest["dependencies"] if row["name"] == "libtcmalloc.so.9.9.5")
    resolved_direct = {row["name"]: (str(Path(mappings[row["name"]]).resolve()) if mappings.get(row["name"]) else None)
                       for row in manifest["dependencies"]}
    direct_exact = all(resolved_direct[row["name"]] == row["resolved_realpath"]
                       for row in manifest["dependencies"])
    positive_pass = (positive.returncode == 0 and "not found" not in (positive.stdout + positive.stderr)
                     and direct_exact
                     and str(Path(mappings["libtcmalloc.so.9.9.5"]).resolve()) == tcmalloc["resolved_realpath"]
                     and sha(Path(tcmalloc["resolved_realpath"])) == tcmalloc["sha256"])
    negative_resources = args.scratch / "negative.resources.json"
    negative_command = ["python3", str(args.old_tools / "resource_probe.py"),
                        "--output", str(negative_resources), "--interval-ms", "25",
                        "--space-root", str(args.base_dir), "--", str(args.binary)]
    negative = run(negative_command, negative_env)
    negative_text = negative.stdout + "\n" + negative.stderr
    negative_resource = json.loads(negative_resources.read_text()) if negative_resources.is_file() else {}
    negative_io = negative_resource.get("peak_process_tree_io_bytes", {})
    negative_pass = (negative.returncode == 127 and "libtcmalloc.so.9.9.5" in negative_text
                     and "cannot open shared object file" in negative_text
                     and negative_resource.get("returncode") == 127
                     and negative_io.get("read_bytes") == 0 and negative_io.get("write_bytes") == 0)
    query_one = args.scratch / "query_1.bin"
    gt_one = args.scratch / "gt_1.bin"
    subprocess.run(["python3", str(args.old_tools / "make_binary_prefix.py"), "--input", str(args.query),
                    "--output", str(query_one), "--rows", "1"], check=True, env=positive_env)
    subprocess.run(["python3", str(args.old_tools / "slice_truthset.py"), "--input", str(args.gt),
                    "--output", str(gt_one), "--rows", "1"], check=True, env=positive_env)
    prefix = args.base_dir / "index"
    smoke_stem = args.scratch / "smoke"
    smoke_log = args.scratch / "smoke.log"
    smoke_resources = args.scratch / "smoke.resources.json"
    smoke_command = ["python3", str(args.old_tools / "resource_probe.py"), "--output", str(smoke_resources),
                     "--interval-ms", "25", "--space-root", str(args.base_dir), "--",
                     str(args.old_tools / "w1_diskann_query_worker.sh"), str(args.binary), str(prefix),
                     str(query_one), str(gt_one), str(smoke_stem), "29", str(smoke_log)]
    smoke = run(smoke_command, positive_env)
    result_ids = Path(f"{smoke_stem}_29_idx_uint32.bin")
    smoke_resource = json.loads(smoke_resources.read_text()) if smoke_resources.is_file() else {}
    result_shape = None
    if result_ids.is_file() and result_ids.stat().st_size >= 8:
        result_shape = list(struct.unpack("<II", result_ids.read_bytes()[:8]))
    log_text = smoke_log.read_text(errors="replace") if smoke_log.is_file() else ""
    smoke_pass = (smoke.returncode == 0 and smoke_resource.get("returncode") == 0 and result_shape == [1, 10]
                  and "Opened file" in log_text and "Done searching" in log_text)
    subprocess.run(["python3", str(args.old_tools / "w1_file_manifest.py"), "--root", str(args.base_dir),
                    "--output", str(after)], check=True, env=positive_env)
    base_exact = before.read_bytes() == after.read_bytes()
    status_lines = Path("/proc/self/status").read_text().splitlines()
    affinity = {key: value.strip() for line in status_lines if ":" in line
                for key, value in [line.split(":", 1)] if key in {"Cpus_allowed_list", "Mems_allowed_list"}}
    report = {
        "schema": "dynamic-vamana-w1-r07-diskann-loader-tests-v1",
        "status": "pass" if positive_pass and negative_pass and smoke_pass and base_exact else "fail",
        "uid": os.getuid(), "gid": os.getgid(), "cgroup": Path("/proc/self/cgroup").read_text().splitlines(),
        "affinity": affinity, "numa": {"command": ["numactl", "--show"], "returncode": numa.returncode,
                                         "stdout": numa.stdout, "stderr": numa.stderr, "membind_node": 0},
        "runtime_manifest": {"realpath": str(args.manifest.resolve()), "sha256": sha(args.manifest)},
        "positive_loader": {"command": ["ldd", str(args.binary)], "returncode": positive.returncode,
                            "stdout": positive.stdout, "stderr": positive.stderr,
                            "all_direct_dependencies_exact": direct_exact,
                            "resolved_direct_dependencies": resolved_direct,
                            "tcmalloc_resolved_realpath": mappings.get("libtcmalloc.so.9.9.5"), "passed": positive_pass},
        "negative_loader": {"command": negative_command, "tested_command": [str(args.binary)],
                            "ld_library_path_present": False,
                            "returncode": negative.returncode, "stdout": negative.stdout,
                            "stderr": negative.stderr, "passed": negative_pass,
                            "resource_returncode": negative_resource.get("returncode"),
                            "peak_process_tree_io_bytes": negative_io,
                            "resources_sha256": sha(negative_resources) if negative_resources.is_file() else None,
                            "entered_query_main": False, "created_formal_result": False},
        "query_smoke": {"command": smoke_command, "returncode": smoke.returncode,
                        "resource_returncode": smoke_resource.get("returncode"), "result_shape": result_shape,
                        "result_ids_sha256": sha(result_ids) if result_ids.is_file() else None,
                        "log_sha256": sha(smoke_log) if smoke_log.is_file() else None,
                        "resources_sha256": sha(smoke_resources) if smoke_resources.is_file() else None,
                        "opened_index": "Opened file" in log_text, "done_searching": "Done searching" in log_text,
                        "passed": smoke_pass},
        "immutable_base": {"before_sha256": sha(before), "after_sha256": sha(after), "exact": base_exact},
        "scratch_removed_after_report": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    shutil.rmtree(args.scratch)
    if report["status"] != "pass":
        raise SystemExit("DiskANN loader regressions failed")


if __name__ == "__main__":
    main()
