#!/usr/bin/env python3
"""Observer-safe W1 worker identity scanner and regression suite."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any


SHELLS = {"/usr/bin/bash", "/usr/bin/dash", "/usr/bin/zsh"}
PYTHON_RE = re.compile(r"^python(?:[0-9]+(?:\.[0-9]+)*)?$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical(value: str | Path) -> str:
    return str(Path(value).resolve(strict=False))


def canonical_script(value: str | Path, cwd: str | None) -> str:
    path = Path(value)
    if not path.is_absolute() and cwd is not None:
        path = Path(cwd) / path
    return canonical(path)


def ancestor_chain(start: int | None = None) -> list[int]:
    chain: list[int] = []
    pid = os.getpid() if start is None else start
    while pid > 0 and pid not in chain:
        chain.append(pid)
        try:
            fields = Path(f"/proc/{pid}/stat").read_text().split()
            parent = int(fields[3])
        except (FileNotFoundError, PermissionError, ValueError, IndexError):
            break
        if parent <= 0 or parent == pid:
            break
        pid = parent
    return chain


def load_policy(root: Path, artifact_manifest: Path, script_root: Path) -> dict[str, Any]:
    artifact = json.loads(artifact_manifest.read_text())
    binaries: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for system in ("DGAI", "OdinANN"):
        for name in ("w1_canary", "search_disk_index"):
            path = canonical(artifact["systems"][system]["canonical_install"][name])
            binaries[path] = f"{system}:{name}"
            hashes[path] = artifact["systems"][system]["binary_sha256"][name]
    diskann = canonical(root / "build/DiskANN/apps/search_disk_index")
    binaries[diskann] = "DiskANN:search_disk_index"
    hashes[diskann] = artifact["systems"]["DiskANN"]["binary_sha256"]["search_disk_index"]
    gt_tool = canonical(artifact["formal_inputs"]["compute_groundtruth"]["realpath"])
    binaries[gt_tool] = "DiskANN:compute_groundtruth"
    hashes[gt_tool] = artifact["formal_inputs"]["compute_groundtruth"]["sha256"]

    old = artifact_manifest.parent
    shell_names = {
        "w1_run_system_canary.sh", "w1_system_worker.sh", "w1_diskann_stale_control.sh",
        "w1_query_worker.sh", "w1_diskann_query_worker.sh", "run_w1_cp01_formal.sh",
        "run_w1_gt_recovery_r02.sh", "run_w1_r03_continuation.sh", "run_w1_r04_continuation.sh", "run_w1_r05_continuation.sh", "run_w1_r06_continuation.sh",
        "w1_gt_recovery_worker.sh", "w1_compute_cp01_gt.sh",
    }
    shell_scripts: dict[str, str] = {}
    for directory in (old, script_root):
        for name in shell_names:
            path = directory / name
            if path.exists() or name == "run_w1_r04_continuation.sh":
                shell_scripts[canonical(path)] = name

    python_names = {
        "resource_probe.py", "timed_query_runner.py", "validate_query_result.py",
        "w1_collect_canary.py", "w1_dump_active_tags.py", "w1_file_manifest.py",
        "w1_preupdate_gate.py", "w1_validate_stale_control.py", "w1_visibility_probe.py",
        "w1_process_identity.py", "w1_r03_continuation_preflight.py",
        "w1_r04_clone_target_tests.py", "w1_r04_execution_manifest.py",
        "w1_r04_assert_reused_inputs.py", "w1_write_r04_stop_report.py",
        "w1_mode_manifest.py", "w1_prepare_mutable_clone.py", "w1_writable_clone_audit.py",
        "w1_r05_mutable_clone_tests.py", "w1_r05_assert_base_immutable.py", "w1_preupdate_identity_gate.py",
        "w1_r06_freeze_r05_dgai.py", "w1_r06_continuation_preflight.py", "w1_r06_execution_manifest.py", "w1_r06_finalize_composed.py",
    }
    python_scripts: dict[str, str] = {}
    for directory in (old, script_root):
        for name in python_names:
            path = directory / name
            if path.exists() or directory == script_root:
                python_scripts[canonical(path)] = name
    return {"binaries": binaries, "binary_hashes": hashes,
            "shell_scripts": shell_scripts, "python_scripts": python_scripts}


def shell_script(argv: list[str]) -> str | None:
    if len(argv) < 2:
        return None
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == "--":
            return argv[index + 1] if index + 1 < len(argv) else None
        if token.startswith("-"):
            # Any command-string mode is deliberately opaque.
            if "c" in token[1:]:
                return None
            index += 1
            continue
        return token
    return None


def python_script(argv: list[str]) -> str | None:
    if len(argv) < 2:
        return None
    index = 1
    options_with_value = {"-W", "-X"}
    while index < len(argv):
        token = argv[index]
        if token in {"-c", "-m", "-"}:
            return None
        if token in options_with_value:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token
    return None


def classify(exe: str, argv: list[str], policy: dict[str, Any], cwd: str | None = None) -> dict[str, Any]:
    resolved_exe = canonical(exe)
    if resolved_exe in policy["binaries"]:
        return {"is_worker": True, "identity_kind": "canonical_binary",
                "identity": policy["binaries"][resolved_exe], "identity_path": resolved_exe}
    if resolved_exe in SHELLS:
        token = shell_script(argv)
        resolved = canonical_script(token, cwd) if token else None
        if resolved in policy["shell_scripts"]:
            return {"is_worker": True, "identity_kind": "canonical_shell_script",
                    "identity": policy["shell_scripts"][resolved], "identity_path": resolved}
    if PYTHON_RE.match(Path(resolved_exe).name):
        token = python_script(argv)
        resolved = canonical_script(token, cwd) if token else None
        if resolved in policy["python_scripts"]:
            return {"is_worker": True, "identity_kind": "canonical_python_script",
                    "identity": policy["python_scripts"][resolved], "identity_path": resolved}
    return {"is_worker": False, "identity_kind": None, "identity": None, "identity_path": None}


def proc_record(pid: int) -> dict[str, Any] | None:
    try:
        exe = os.readlink(f"/proc/{pid}/exe")
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        argv = [part.decode(errors="replace") for part in raw.split(b"\0") if part]
        cgroup = Path(f"/proc/{pid}/cgroup").read_text().splitlines()
        cwd = canonical(os.readlink(f"/proc/{pid}/cwd"))
        ppid = int(Path(f"/proc/{pid}/stat").read_text().split()[3])
    except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, IndexError):
        return None
    return {"pid": pid, "ppid": ppid, "exe": canonical(exe), "argv": argv, "cwd": cwd, "cgroup": cgroup}


def active_scopes() -> list[dict[str, Any]]:
    command = ["systemctl", "list-units", "--type=scope", "--all",
               "--no-legend", "--plain", "dv-w1-*.scope"]
    listing = subprocess.run(command, text=True, capture_output=True, check=False)
    if listing.returncode != 0:
        raise RuntimeError(f"systemd scope query failed: {listing.stderr.strip()}")
    rows: list[dict[str, Any]] = []
    for line in listing.stdout.splitlines():
        if not line.strip():
            continue
        unit = line.split()[0]
        show = subprocess.run(["systemctl", "show", unit, "-p", "ActiveState", "-p", "SubState", "-p", "ControlGroup"],
                              text=True, capture_output=True, check=True)
        properties = dict(row.split("=", 1) for row in show.stdout.splitlines() if "=" in row)
        active_state = properties.get("ActiveState", "unknown")
        sub_state = properties.get("SubState", "unknown")
        control_group = properties.get("ControlGroup", "")
        pids = []
        if control_group:
            procs_path = Path("/sys/fs/cgroup") / control_group.lstrip("/") / "cgroup.procs"
            try:
                pids = [int(value) for value in procs_path.read_text().split()]
            except (FileNotFoundError, PermissionError, ValueError):
                pids = []
        if active_state in {"active", "activating", "deactivating", "reloading"} or pids:
            rows.append({"unit": unit, "active_state": active_state, "sub_state": sub_state,
                         "control_group": control_group, "pids": pids,
                         "processes": [record for pid in pids if (record := proc_record(pid)) is not None]})
    return rows


def scan(policy: dict[str, Any], exclude: set[int]) -> dict[str, Any]:
    scopes = active_scopes()
    workers: list[dict[str, Any]] = []
    scanned = 0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid in exclude:
            continue
        record = proc_record(pid)
        if record is None:
            continue
        scanned += 1
        result = classify(record["exe"], record["argv"], policy, record["cwd"])
        if result["is_worker"]:
            workers.append({**record, **result})
    return {"status": "pass" if not scopes and not workers else "fail",
            "excluded_ancestor_pids": sorted(exclude), "processes_scanned": scanned,
            "active_w1_scopes": scopes, "canonical_w1_workers": workers}


def fixture_record(pid: int, exe: str, argv: list[str], cgroup: list[str], expected: bool,
                   policy: dict[str, Any], excluded: set[int] | None = None, name: str = "",
                   cwd: str = "/tmp") -> dict[str, Any]:
    ignored = excluded is not None and pid in excluded
    actual = False if ignored else bool(classify(exe, argv, policy, cwd)["is_worker"])
    return {"name": name, "pid": pid, "exe": exe, "argv": argv, "cwd": cwd, "cgroup": cgroup,
            "expected_classification": expected, "actual_classification": actual,
            "excluded_as_ancestor": ignored, "passed": actual == expected}


def run_fixtures(policy: dict[str, Any], output: Path) -> dict[str, Any]:
    if output.exists():
        raise SystemExit("process identity test output overwrite refused")
    result_root_absent_before_tests = not output.parent.parent.exists()
    binary_paths = list(policy["binaries"])
    shell_path = next(path for path, name in policy["shell_scripts"].items() if name == "w1_run_system_canary.sh")
    python_path = canonical(Path(__file__))
    cgroup = ["0::/user.slice/observer.scope"]
    fixtures = [
        fixture_record(91001, "/usr/bin/rg", ["rg", "w1_canary|w1_run_system_canary"], cgroup, False, policy, name="rg_observer"),
        fixture_record(91002, "/usr/bin/zsh", ["zsh", "-lc", "ps -eo pid,args | rg w1_canary"], cgroup, False, policy, name="zsh_command_observer"),
        fixture_record(91003, "/usr/bin/python3", ["python3", "/tmp/observer.py", "w1_canary"], cgroup, False, policy, name="python_argument_observer"),
        fixture_record(91004, "/usr/bin/python3", ["python3", "-c", "import time; time.sleep(5)", "w1_run_system_canary"], cgroup, False, policy, name="python_command_observer"),
        fixture_record(91005, "/usr/bin/echo", ["echo", "w1_diskann_stale_control"], cgroup, False, policy, name="echo_observer"),
        fixture_record(91006, "/usr/bin/bwrap", ["bwrap", "--", "codex", "rg", "w1_canary"], cgroup, False, policy, name="codex_bwrap_observer"),
        fixture_record(91007, "/tmp/w1_canary", ["/tmp/w1_canary"], cgroup, False, policy, name="noncanonical_binary"),
        fixture_record(91008, "/usr/bin/bash", ["bash", "/tmp/w1_run_system_canary.sh"], cgroup, False, policy, name="noncanonical_shell_script"),
        fixture_record(91009, binary_paths[0], [binary_paths[0]], cgroup, True, policy, name="canonical_w1_canary"),
        fixture_record(91010, binary_paths[1], [binary_paths[1]], cgroup, True, policy, name="canonical_search_binary"),
        fixture_record(91011, "/usr/bin/bash", ["bash", shell_path, "--system", "DGAI"], cgroup, True, policy, name="canonical_shell_script"),
        fixture_record(91012, "/usr/bin/python3", ["python3", python_path, "scan"], cgroup, True, policy, name="canonical_python_script"),
        fixture_record(91013, "/usr/bin/bash", ["bash", f"./{Path(shell_path).name}"], cgroup, True, policy,
                       name="canonical_relative_shell_script", cwd=str(Path(shell_path).parent)),
        fixture_record(91014, "/usr/bin/python3", ["python3", f"./{Path(python_path).name}", "scan"], cgroup, True, policy,
                       name="canonical_relative_python_script", cwd=str(Path(python_path).parent)),
    ]
    lineage = set(ancestor_chain())
    ancestor_pid = next(iter(lineage))
    fixtures.append(fixture_record(ancestor_pid, "/usr/bin/bash", ["bash", shell_path], cgroup,
                                   False, policy, lineage, "canonical_ancestor_ignored"))
    fixtures.append(fixture_record(91999, "/usr/bin/bash", ["bash", shell_path], cgroup,
                                   True, policy, lineage, "canonical_nonancestor_rejected"))

    before = active_scopes()
    if before:
        raise SystemExit(f"cannot run scope fixture with pre-existing W1 scope: {before}")
    proc = subprocess.Popen(["systemd-run", "--scope", "--collect", "--unit", "dv-w1-stale-fixture", "sleep", "300"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    detected: list[dict[str, Any]] = []
    try:
        for _ in range(50):
            detected = active_scopes()
            if any(row["unit"] == "dv-w1-stale-fixture.scope" for row in detected):
                break
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        fixture_detected = any(row["unit"] == "dv-w1-stale-fixture.scope" for row in detected)
    finally:
        subprocess.run(["systemctl", "stop", "dv-w1-stale-fixture.scope"], check=False,
                       text=True, capture_output=True)
        try:
            proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.communicate(timeout=5)
    after_scan = scan(policy, set(ancestor_chain()))
    scope_test = {"unit": "dv-w1-stale-fixture.scope", "detected_while_active": fixture_detected,
                  "detected_records": detected, "explicitly_stopped": True,
                  "next_scan_status": after_scan["status"], "next_scan": after_scan,
                  "passed": fixture_detected and after_scan["status"] == "pass"}

    hash_checks = []
    for path, expected in policy["binary_hashes"].items():
        actual = sha256(Path(path))
        hash_checks.append({"path": path, "expected_sha256": expected, "actual_sha256": actual,
                            "passed": actual == expected})
    passed = all(row["passed"] for row in fixtures) and scope_test["passed"] and all(row["passed"] for row in hash_checks)
    report = {"schema": "dynamic-vamana-w1-process-identity-tests-v1",
              "status": "pass" if passed else "fail",
              "result_root_absent_before_tests": result_root_absent_before_tests,
              "fixtures": fixtures,
              "scope_fixture": scope_test, "canonical_binary_hash_checks": hash_checks}
    output.parent.mkdir(parents=True, exist_ok=False)
    output.write_text(json.dumps(report, indent=2) + "\n")
    if not passed:
        raise SystemExit("process identity regression tests failed")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    for name in ("scan", "test-fixtures"):
        command = sub.add_parser(name)
        command.add_argument("--root", type=Path, required=True)
        command.add_argument("--artifact-manifest", type=Path, required=True)
        command.add_argument("--output", type=Path)
    args = parser.parse_args()
    policy = load_policy(args.root.resolve(), args.artifact_manifest.resolve(), Path(__file__).resolve().parent)
    if args.mode == "test-fixtures":
        if args.output is None:
            raise SystemExit("test-fixtures requires --output")
        run_fixtures(policy, args.output)
        return
    report = {"schema": "dynamic-vamana-w1-process-identity-scan-v1", **scan(policy, set(ancestor_chain()))}
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise SystemExit("process identity scan output overwrite refused")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end="")
    if report["status"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
