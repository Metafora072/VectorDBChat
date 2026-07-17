#!/usr/bin/env python3
"""Fail-closed preflight for CP05 cumulative trajectory R06 recovery."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "dynamic-vamana-w1-cp05-cumulative-r06-preflight-v1"
R03_RUN = "pilot3_sift10m_w1_cp05_trajectory_r03"
R05_RUN = "pilot3_sift10m_w1_cp05_trajectory_r05"
R06_RUN = "pilot3_sift10m_w1_cp05_trajectory_r06"
R06_REPLAY_RUN = "pilot3_w1_cp05_trajectory_replay_r06"
STATIC_SMOKE_SHA256 = "5c9f2189a5c37c29d052c3593bc5cdd4f635b050cb6bbbf60a857b49b7be09c3"
R02_TOOL_ROOT = Path(
    "/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-16/dynamic_vamana_atlas"
)


def require(value: bool, message: str) -> None:
    if not value: raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""): digest.update(block)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True); info = path.stat()
    return {"realpath": str(path), "size_bytes": info.st_size, "sha256": sha256(path),
            "mtime_ns": info.st_mtime_ns, "mode": stat.S_IMODE(info.st_mode),
            "uid": info.st_uid, "gid": info.st_gid, "device": info.st_dev, "inode": info.st_ino}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def write_new(path: Path, value: dict[str, Any]) -> None:
    require(not path.exists() and not path.is_symlink(), f"preflight overwrite refused: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())


def tree(root: Path, immutable: bool = False) -> dict[str, dict[str, Any]]:
    root = root.resolve(strict=True); result: dict[str, dict[str, Any]] = {}
    def visit(path: Path, relative: str) -> None:
        info = path.lstat(); mode = stat.S_IMODE(info.st_mode)
        if stat.S_ISDIR(info.st_mode):
            kind = "directory"; require(not immutable or mode == 0o555, f"directory not 0555: {path}")
        elif stat.S_ISREG(info.st_mode):
            kind = "regular"; require(info.st_nlink == 1, f"regular file hard-linked: {path}")
            require(not immutable or mode == 0o444, f"file not 0444: {path}")
        else: raise ValueError(f"unsupported tree object: {path}")
        row: dict[str, Any] = {"type": kind, "mode": mode, "uid": info.st_uid,
            "gid": info.st_gid, "device": info.st_dev, "inode": info.st_ino, "link_count": info.st_nlink}
        if kind == "regular": row.update(size_bytes=info.st_size, sha256=sha256(path))
        result[relative] = row
        if kind == "directory":
            for name in sorted(entry.name for entry in os.scandir(path)):
                visit(path / name, name if relative == "." else f"{relative}/{name}")
    visit(root, "."); return result


def compare_trees(old_root: Path, new_root: Path, label: str) -> dict[str, Any]:
    old, new = tree(old_root, immutable=True), tree(new_root, immutable=True)
    require(set(old) == set(new), f"{label} relative path set mismatch")
    compared = 0
    for relative in old:
        left, right = old[relative], new[relative]
        require(left["type"] == right["type"], f"{label} type mismatch: {relative}")
        require((left["device"], left["inode"]) != (right["device"], right["inode"]),
                f"{label} inode shared: {relative}")
        if left["type"] == "regular":
            require((left["size_bytes"], left["sha256"]) == (right["size_bytes"], right["sha256"]),
                    f"{label} content mismatch: {relative}")
            compared += 1
    return {"status": "pass", "old_root": str(old_root.resolve()), "new_root": str(new_root.resolve()),
            "relative_objects": len(old), "regular_files_byte_identical": compared,
            "all_inodes_independent": True, "immutable_policy": True}


def verify_base(base_root: Path, system: str) -> dict[str, Any]:
    directory = (base_root / system / "cp00").resolve(strict=True)
    manifest_path = directory / "immutable_replay_base_manifest.json"; manifest = load(manifest_path)
    require(manifest.get("status") == "pass" and manifest.get("system") == system,
            f"{system} immutable replay-base manifest invalid")
    require(manifest.get("schema") == "dynamic-vamana-w1-immutable-replay-base-v1",
            f"{system} immutable replay-base schema mismatch")
    immutable_entry = manifest.get("immutable_base", {})
    require(Path(immutable_entry.get("realpath", "")).resolve(strict=True)
            == (directory / "index").resolve(strict=True), f"{system} immutable base path mismatch")
    required = ("base_content.tsv", "base_mode.tsv", "source_content_before.tsv", "source_content_after.tsv",
                "source_mode_before.tsv", "source_mode_after.tsv", "write_denial_audit.json",
                "IMMUTABLE_REPLAY_BASE_OK")
    for name in required: require((directory / name).is_file(), f"{system} base evidence missing: {name}")
    require((directory / "source_content_before.tsv").read_bytes()
            == (directory / "source_content_after.tsv").read_bytes()
            == (directory / "base_content.tsv").read_bytes(), f"{system} replay-base content lineage differs")
    require((directory / "source_mode_before.tsv").read_bytes()
            == (directory / "source_mode_after.tsv").read_bytes(), f"{system} source mode changed")
    expected_content_sha = (immutable_entry.get("content", {}).get("sha256")
                            or manifest.get("content_manifest_sha256"))
    expected_mode_sha = (immutable_entry.get("mode", {}).get("sha256")
                         or manifest.get("mode_manifest_sha256"))
    require(sha256(directory / "base_content.tsv") == expected_content_sha,
            f"{system} base content hash mismatch")
    require(sha256(directory / "base_mode.tsv") == expected_mode_sha,
            f"{system} base mode hash mismatch")
    accepted_r07 = manifest.get("accepted_r07", {})
    accepted_record = accepted_r07.get("base_before", accepted_r07.get("base_content_before", {}))
    accepted = Path(accepted_record.get("realpath", "")).resolve(strict=True)
    require(sha256(accepted) == accepted_record.get("sha256"),
            f"{system} accepted R07 lineage evidence changed")
    require(accepted_r07.get("run") == "pilot3_w1_formal_path_replay_r07"
            and accepted_r07.get("attempt") == "replay-01",
            f"{system} accepted R07 run/attempt mismatch")
    for name, record in accepted_r07.items():
        if not isinstance(record, dict): continue
        path = Path(record.get("realpath", "")).resolve(strict=True)
        require(path.is_file() and path.stat().st_size == int(record.get("size", -1))
                and sha256(path) == record.get("sha256"),
                f"{system} accepted R07 lineage changed: {name}")
    source = manifest.get("source", {})
    special_count = source.get("special_object_count", source.get("special_count"))
    hardlink_count = source.get("regular_hardlink_count", source.get("hardlink_count"))
    require(source.get("open_writable_fd_count") == 0
            and special_count == 0 and hardlink_count == 0,
            f"{system} source safety lineage failed")
    directory_mode = immutable_entry.get("directory_mode", immutable_entry.get("directory_mode_octal"))
    file_mode = immutable_entry.get("file_mode", immutable_entry.get("file_mode_octal"))
    require(immutable_entry.get("owner_uid") == 0 and immutable_entry.get("owner_gid") == 0
            and directory_mode in ("0555", 0o555)
            and file_mode in ("0444", 0o444)
            and immutable_entry.get("inode_independent") is True,
            f"{system} immutable policy verdict absent")
    denial = load(directory / "write_denial_audit.json")
    require(denial.get("status") == "pass", f"{system} owner denial not PASS")
    tree(directory / "index", immutable=True)
    # Invoke the builder's read-only verifier as an independent recomputation
    # of live source content/mode, all R07 lineage identities and base policy.
    builder_path = R02_TOOL_ROOT / "w1_replay_base_recovery.py"
    spec = importlib.util.spec_from_file_location("w1_replay_base_verify_import", builder_path)
    require(spec is not None and spec.loader is not None, "replay-base verifier unavailable")
    builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
    live_verification = builder.verify_final(base_root.parent.parent, system, run_denial=False)
    require(live_verification.get("status") == "pass", f"{system} live replay-base verification failed")
    return {"status": "pass", "manifest": identity(manifest_path), "accepted_r07_manifest": identity(accepted),
            "base_content": identity(directory / "base_content.tsv"),
            "base_mode": identity(directory / "base_mode.tsv"),
            "write_denial": identity(directory / "write_denial_audit.json"),
            "live_verification": live_verification}


def available_memory() -> int:
    line = next(line for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:"))
    return int(line.split()[1]) * 1024


def mount_device(path: Path) -> str:
    while not path.exists(): path = path.parent
    return subprocess.run(["findmnt", "-rn", "-T", str(path), "-o", "MAJ:MIN"], check=True,
                          text=True, capture_output=True).stdout.splitlines()[0]


def active_w1_processes() -> list[dict[str, Any]]:
    # The detached launch path is tmux -> timeout -> controller -> this
    # preflight. Exclude the complete ancestry so the authorized timeout
    # wrapper is not mistaken for a competing W1 process.
    own: set[int] = set()
    pid = os.getpid()
    while pid > 0 and pid not in own:
        own.add(pid)
        try:
            fields = (Path("/proc") / str(pid) / "stat").read_text().split()
            pid = int(fields[3])
        except (OSError, ValueError, IndexError):
            break
    rows = []
    executable_tokens = (
        "run_w1_cp05_cumulative_trajectory_r06.sh",
        "start_w1_cp05_cumulative_r06_tmux.sh",
        "w1_run_cumulative_trajectory_r06.sh",
        "w1_cumulative_stage_worker_r06.sh",
        "w1_run_query_scope.sh",
        "w1_run_diskann_cp05_stale_r06.sh",
    )
    for item in Path("/proc").iterdir():
        if not item.name.isdigit() or int(item.name) in own: continue
        try: command = (item / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError: continue
        if any(token in command for token in executable_tokens):
            rows.append({"pid": int(item.name), "command": command[:4096]})
    return rows


def active_w1_units() -> list[str]:
    completed = subprocess.run(
        ["systemctl", "list-units", "--all", "--plain", "--no-legend",
         "dv-w1-cum-r06-*", "dv-w1-cp05-r06-*"],
        check=True, text=True, capture_output=True,
    )
    return [line.split()[0] for line in completed.stdout.splitlines() if line.split()]


def validate(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve(strict=True); expected_device = args.device
    r03_result = args.r03_result.resolve(strict=True)
    r03_formal = args.r03_formal.resolve(strict=False)
    r03_replay_formal = args.r03_replay_formal.resolve(strict=True)
    delta = args.r03_delta_root.resolve(strict=True)
    replay_inputs = args.r03_replay_input_root.resolve(strict=True)
    r05_result = args.r05_terminal_result.resolve(strict=True)
    r05_replay_formal = args.r05_terminal_replay_formal.resolve(strict=True)
    base_root = args.replay_base_root.resolve(strict=True); smoke_path = args.static_smoke.resolve(strict=True)
    smoke_revalidation_path = args.static_smoke_revalidation.resolve(strict=True)
    query_tests_path = args.query_scope_tests.resolve(strict=True)
    canary_tests_path = args.input_canary_tests.resolve(strict=True)
    primer_tests_path = args.stage_io_primer_tests.resolve(strict=True)
    result = args.r06_result_root.resolve(strict=False); formal = args.r06_formal_root.resolve(strict=False)
    replay_formal = args.r06_replay_formal_root.resolve(strict=False)
    output = args.output.resolve(strict=False)
    require(r03_result == root / f"results/{R03_RUN}", "R03 terminal result path mismatch")
    require(r03_formal == root / f"formal/{R03_RUN}"
            and r03_replay_formal == root / "formal/pilot3_w1_cp05_trajectory_replay_r03",
            "R03 terminal formal capability path mismatch")
    require(r05_result == root / f"results/{R05_RUN}"
            and r05_replay_formal == root / "formal/pilot3_w1_cp05_trajectory_replay_r05",
            "R05 terminal capability path mismatch")
    require(result == root / f"results/{R06_RUN}" and formal == root / f"formal/{R06_RUN}"
            and replay_formal == root / f"formal/{R06_REPLAY_RUN}", "R06 capability path mismatch")
    require(output == result / "preflight/execution_preflight.json", "R06 preflight output path mismatch")
    require(delta == root / "datasets/sift10m/w1_trajectory/execution_deltas_r03",
            "R06 must reuse the accepted R03 delta root")
    require(replay_inputs == r03_result / "replay/inputs",
            "R06 must reuse the accepted R03 replay-input root")

    r03_execution_path = r03_result / "execution_manifest.json"; r03_execution = load(r03_execution_path)
    require((r03_execution.get("schema"), r03_execution.get("status"),
             r03_execution.get("stopped_phase"), r03_execution.get("exit_code"))
            == ("dynamic-vamana-w1-cp05-cumulative-r03-execution-v1",
                "stopped_failed", "replay_DGAI", 1), "R03 terminal identity mismatch")
    require(r03_execution.get("attempts", {}).get("DGAI_replay") == "sequential-cp80-03",
            "R03 replay attempt identity mismatch")
    r03_preservation_path = r03_result / "preflight/preservation_after_stop.json"
    r03_preservation = load(r03_preservation_path)
    require(r03_preservation.get("schema") == "dynamic-vamana-w1-cp05-cumulative-r03-preservation-v1"
            and r03_preservation.get("status") == "pass" and not r03_preservation.get("mismatches"),
            "R03 stop-time preservation is not PASS")
    r03_query_gate_path = r03_result / "replay/DGAI/sequential-cp80-03/queries/cp00/query_gate.json"
    r03_query_gate = load(r03_query_gate_path)
    require(r03_query_gate.get("schema") == "dynamic-vamana-w1-query-identity-v2"
            and r03_query_gate.get("status") == "pass"
            and r03_query_gate.get("checkpoint") == "cp00",
            "R03 DGAI CP00 query gate is not PASS")
    forbidden = (list(r03_result.glob("**/STAGE_WORKER_OK"))
                 + list(r03_result.glob("**/stage_evidence.json"))
                 + list(r03_result.glob("**/*checkpoint_evidence.json"))
                 + list(r03_result.glob("**/CUMULATIVE_TRAJECTORY_OK")))
    require(not forbidden and not (r03_result / "replay/OdinANN").exists()
            and not (r03_result / "DGAI").exists()
            and not (r03_result / "OdinANN").exists()
            and not (r03_result / "DiskANN").exists(),
            "R03 advanced beyond the accepted pre-update boundary")
    require((r03_replay_formal / "DGAI/sequential-cp80-03/clone_manifest.json").is_file(),
            "R03 terminal clone evidence absent")
    require(not r03_formal.exists(), "R03 formal state unexpectedly exists")

    r05_execution_path = r05_result / "execution_manifest.json"; r05_execution = load(r05_execution_path)
    require((r05_execution.get("schema"), r05_execution.get("status"),
             r05_execution.get("stopped_phase"), r05_execution.get("exit_code"))
            == ("dynamic-vamana-w1-cp05-cumulative-r05-execution-v1",
                "stopped_failed", "replay_DGAI", 1), "R05 terminal identity mismatch")
    require(r05_execution.get("attempts", {}).get("DGAI_replay") == "sequential-cp80-05",
            "R05 replay attempt identity mismatch")
    r05_preservation_path = r05_result / "preflight/preservation_after_stop.json"
    r05_preservation = load(r05_preservation_path)
    require(r05_preservation.get("schema") == "dynamic-vamana-w1-cp05-cumulative-r05-preservation-v1"
            and r05_preservation.get("status") == "pass" and not r05_preservation.get("mismatches"),
            "R05 stop-time preservation is not PASS")
    r05_query_gate_path = r05_result / "replay/DGAI/sequential-cp80-05/queries/cp00/query_gate.json"
    r05_query_gate = load(r05_query_gate_path)
    require(r05_query_gate.get("schema") == "dynamic-vamana-w1-query-identity-v2"
            and r05_query_gate.get("status") == "pass" and r05_query_gate.get("checkpoint") == "cp00",
            "R05 DGAI CP00 query gate is not PASS")
    r05_canary_path = (r05_result / "replay/DGAI/sequential-cp80-05/stages/cp01"
                       / "input_canary/canary.json")
    r05_canary = load(r05_canary_path)
    require(r05_canary.get("schema") == "dynamic-vamana-w1-r04-input-canary-v1"
            and r05_canary.get("status") == "pass" and r05_canary.get("uid") == 1000
            and r05_canary.get("allowed_readable") is True
            and r05_canary.get("denied")
            and all(row.get("open_refused") is True for row in r05_canary.get("denied", [])),
            "R05 stage-local input canary is not PASS")
    r05_stage = r05_result / "replay/DGAI/sequential-cp80-05/stages/cp01"
    r05_worker_path = r05_stage / "worker_identity.json"
    r05_worker = load(r05_worker_path)
    require(r05_worker.get("schema") == "dynamic-vamana-w1-cumulative-stage-worker-identity-v1"
            and r05_worker.get("status") == "pass" and r05_worker.get("stage") == "cp01"
            and r05_worker.get("incremental_replacements") == 16
            and r05_worker.get("primitive_mutations") == 32,
            "R05 completed update worker identity is invalid")
    for name in ("STAGE_WORKER_OK", "markers.jsonl", "active_audit.json", "fresh_probe.json"):
        require((r05_stage / name).is_file(), f"R05 completed update evidence absent: {name}")
    r05_forbidden = (list(r05_result.glob("**/stage_evidence.json"))
                     + list(r05_result.glob("**/*checkpoint_evidence.json"))
                     + list(r05_result.glob("**/CUMULATIVE_TRAJECTORY_OK"))
                     + list(r05_result.glob("**/legacy_canary.json")))
    require(not r05_forbidden and not (r05_result / "replay/OdinANN").exists()
            and not (r05_result / "DGAI").exists() and not (r05_result / "OdinANN").exists()
            and not (r05_result / "DiskANN").exists()
            and not (root / f"formal/{R05_RUN}").exists(),
            "R05 advanced beyond the accepted post-update/pre-accounting boundary")
    require((r05_replay_formal / "DGAI/sequential-cp80-05/clone_manifest.json").is_file(),
            "R05 terminal clone evidence absent")

    delta_tree = tree(delta, immutable=True)
    replay_tree = tree(replay_inputs, immutable=True)
    bases = {system: verify_base(base_root, system) for system in ("DGAI", "OdinANN")}
    smoke = load(smoke_path)
    require(sha256(smoke_path) == STATIC_SMOKE_SHA256, "frozen static-smoke SHA-256 mismatch")
    require(smoke_revalidation_path.read_bytes() == smoke_path.read_bytes(),
            "frozen static-smoke full read-only revalidation differs")
    require(smoke.get("schema") == "dynamic-vamana-w1-cp05-r02-static-load-smoke-v1"
            and smoke.get("status") == "pass" and smoke.get("expected_shape") == [36, 10],
            "frozen static load smoke not PASS")
    for system in ("DGAI", "OdinANN"):
        require(smoke.get("systems", {}).get(system, {}).get("status") == "pass", f"{system} smoke absent")
        require(smoke["systems"][system]["immutable_base_manifest"]["sha256"]
                == bases[system]["manifest"]["sha256"], f"{system} smoke/base lineage mismatch")

    query_tests = load(query_tests_path)
    r03_query_tests_path = r03_result / "preflight/query_scope_tests.json"
    require(query_tests_path.read_bytes() == r03_query_tests_path.read_bytes(),
            "R03 shared query-launcher evidence was not reused byte-for-byte")
    require(query_tests.get("schema") == "dynamic-vamana-w1-r03-query-scope-primer-tests-v1"
            and query_tests.get("status") == "pass"
            and query_tests.get("DGAI_L64_positive", {}).get("status") == "pass"
            and query_tests.get("OdinANN_L29_positive", {}).get("status") == "pass"
            and query_tests.get("missing_primer_negative", {}).get("strict_parser_rejected") is True,
            "R03 shared query-launcher integration tests not PASS")
    for field, filename in (("shared_launcher", "w1_run_query_scope.sh"),
                            ("primer_helper", "w1_query_io_primer.py")):
        record = query_tests.get(field, {}); tool = Path(__file__).with_name(filename).resolve(strict=True)
        require(record.get("realpath") == str(tool) and record.get("size_bytes") == tool.stat().st_size
                and record.get("sha256") == sha256(tool), f"R03 {field} identity mismatch")

    canary_tests = load(canary_tests_path)
    require(canary_tests.get("schema") == "dynamic-vamana-w1-r04-minimal-input-canary-tests-v1"
            and canary_tests.get("status") == "pass"
            and canary_tests.get("denied_readable_rejected") is True
            and canary_tests.get("update_worker_not_started") is True,
            "R06 minimal input-canary tests not PASS")
    canary_helper = Path(__file__).with_name("w1_input_canary.py").resolve(strict=True)
    helper_record = canary_tests.get("helper", {})
    require(helper_record.get("realpath") == str(canary_helper)
            and helper_record.get("size_bytes") == canary_helper.stat().st_size
            and helper_record.get("sha256") == sha256(canary_helper),
            "R06 input-canary helper identity mismatch")

    primer_tests = load(primer_tests_path)
    require(primer_tests.get("schema") == "dynamic-vamana-w1-r06-stage-io-primer-tests-v1"
            and primer_tests.get("status") == "pass"
            and primer_tests.get("same_systemd_scope") is True
            and primer_tests.get("primer_before_resource_probe") is True
            and primer_tests.get("first_and_final_sample_include_target_device") is True
            and primer_tests.get("primer_bytes") == 4096
            and primer_tests.get("primer_excluded_from_stage_deltas") is True,
            "R06 same-scope stage-I/O primer test is not PASS")
    stage_primer = Path(__file__).with_name("w1_stage_io_primer.py").resolve(strict=True)
    primer_helper = primer_tests.get("helper", {})
    require(primer_helper.get("realpath") == str(stage_primer)
            and primer_helper.get("size_bytes") == stage_primer.stat().st_size
            and primer_helper.get("sha256") == sha256(stage_primer),
            "R06 stage-I/O primer helper identity mismatch")

    r03_preflight_path = r03_result / "preflight/execution_preflight.json"; prior = load(r03_preflight_path)
    require(prior.get("schema") == "dynamic-vamana-w1-cp05-cumulative-r03-preflight-v1"
            and prior.get("status") == "pass", "R03 accepted preflight absent")
    protected: dict[str, Any] = {}
    for name, expected in prior.get("protected_artifacts", {}).items():
        current = identity(Path(expected["realpath"]))
        require(current == expected, f"protected trajectory/GT/base/binary artifact changed: {name}")
        protected[name] = current
    artifact = load(args.artifact_manifest)
    require(artifact.get("systems", {}).get("DGAI", {}).get("io_engine") == "aio",
            "DGAI canonical aio identity absent")
    require(artifact.get("systems", {}).get("OdinANN", {}).get("io_engine") == "uring",
            "OdinANN canonical io_uring identity absent")
    artifact_anchor = prior.get("artifact_manifest")
    require(isinstance(artifact_anchor, dict), "accepted artifact-manifest identity absent")
    require(identity(args.artifact_manifest)["sha256"] == artifact_anchor["sha256"],
            "canonical-v6 artifact manifest differs from accepted preflight")
    accepted_binaries = prior.get("binaries")
    require(isinstance(accepted_binaries, dict) and
            "DiskANN_search_disk_index" in accepted_binaries,
            "accepted canonical binary identities absent")
    binaries: dict[str, Any] = {}
    for name, expected in accepted_binaries.items():
        require(isinstance(expected, dict) and isinstance(expected.get("realpath"), str),
                f"accepted binary identity invalid: {name}")
        current = identity(Path(expected["realpath"]))
        require(current == expected, f"accepted canonical binary changed: {name}")
        binaries[name] = current

    # R06 is fresh: before activation it may contain only recovery-gate evidence.
    if result.exists():
        require({entry.name for entry in result.iterdir()} <= {"preflight"},
                "R06 result contains attempt output")
        require(not any(result.glob("DGAI/**")) and not any(result.glob("OdinANN/**"))
                and not any(result.glob("DiskANN/**")), "R06 result attempt not fresh")
    require(not formal.exists() and not replay_formal.exists(), "R06 formal/replay clone target not fresh")
    require(not args.report.exists(), "R06 final report target is not fresh")
    active = active_w1_processes(); units = active_w1_units()
    require(not active and not units, "active W1 process/scope exists")
    for path in (root, formal.parent, replay_formal.parent, delta.parent):
        require(mount_device(path) == expected_device, f"large artifact path not on NVMe: {path}")
    free, memory = shutil.disk_usage(root).free, available_memory()
    require(free >= 128 * 1024**3 and memory >= 64 * 1024**3, "launch space/memory guard failed")
    require(os.environ.get("W1_GLOBAL_LOCK_HELD") == "1", "global W1 flock marker absent")

    report = {"schema": SCHEMA, "status": "pass", "run": R06_RUN,
        "attempts": {"DGAI": "trajectory-cp05-06", "OdinANN": "trajectory-cp05-06",
                     "DiskANN": "stale-cp05-06", "replay": "sequential-cp80-06"},
        "terminal_attempt": {"R03": {"execution_manifest": identity(r03_execution_path),
            "status": "stopped_failed", "stopped_phase": "replay_DGAI", "exit_code": 1,
            "stopped_before_update_worker": True, "no_cp01_cp05_odin_formal_diskann": True,
            "cp00_query_gate": identity(r03_query_gate_path),
            "preservation_after_stop": identity(r03_preservation_path)},
            "R05": {"execution_manifest": identity(r05_execution_path),
                "status": "stopped_failed", "stopped_phase": "replay_DGAI", "exit_code": 1,
                "update_api_completed": True, "performance_evidence_rejected": True,
                "no_cp01_checkpoint_cp05_odin_formal_diskann": True,
                "cp00_query_gate": identity(r05_query_gate_path),
                "stage_local_canary": identity(r05_canary_path),
                "worker_identity": identity(r05_worker_path),
                "preservation_after_stop": identity(r05_preservation_path)}},
        "reused_inputs": {"source_run": R03_RUN, "delta_root": str(delta),
            "delta_tree": delta_tree, "replay_input_root": str(replay_inputs),
            "replay_input_tree": replay_tree, "r03_clone_result_attempt_reused": False},
        "immutable_replay_bases": bases, "static_load_smoke": identity(smoke_path),
        "static_smoke_revalidation": identity(smoke_revalidation_path),
        "query_scope_tests": identity(query_tests_path),
        "input_canary_tests": identity(canary_tests_path),
        "stage_io_primer_tests": identity(primer_tests_path),
        "protected_artifacts": protected, "artifact_manifest": identity(args.artifact_manifest),
        "binaries": binaries,
        "accepted_r03_preflight": identity(r03_preflight_path),
        "diskann_lineage": prior.get("diskann_lineage"),
        "fresh_targets": {"result_root": str(result), "formal_root": str(formal),
            "replay_formal_root": str(replay_formal), "delta_root": str(delta),
            "replay_input_root": str(replay_inputs), "report": str(args.report.resolve(strict=False))},
        "experiment_device": expected_device, "free_bytes": free, "memory_available_bytes": memory,
        "active_w1_processes": active, "active_w1_units": units,
        "held_checkpoints": ["CP10", "CP20"]}
    write_new(output, report); return report


def self_test(args: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory(dir=args.scratch) as tmp:
        root = Path(tmp); old = root / "old"; new = root / "new"
        for directory in (old, new):
            directory.mkdir(); (directory / "x").write_bytes(b"same")
            (directory / "x").chmod(0o444); directory.chmod(0o555)
        positive = compare_trees(old, new, "fixture")["status"] == "pass"
        new.chmod(0o755); (new / "x").chmod(0o644); (new / "x").write_bytes(b"tampered")
        (new / "x").chmod(0o444); new.chmod(0o555)
        negative = False
        try: compare_trees(old, new, "fixture-negative")
        except ValueError: negative = True
        hard = root / "hard"; hard.mkdir(); (hard / "x").write_bytes(b"same")
        os.link(hard / "x", hard / "y"); (hard / "x").chmod(0o444); hard.chmod(0o555)
        hardlink_negative = False
        try: tree(hard, immutable=True)
        except ValueError: hardlink_negative = True
        mode = root / "mode"; mode.mkdir(); (mode / "x").write_bytes(b"same")
        (mode / "x").chmod(0o644); mode.chmod(0o555)
        mode_negative = False
        try: tree(mode, immutable=True)
        except ValueError: mode_negative = True
        require(positive and negative and hardlink_negative and mode_negative, "preflight fixture tests failed")
    write_new(args.output, {"schema": "dynamic-vamana-w1-cp05-r06-preflight-self-test-v1",
                            "status": "pass", "byte_identity_positive": positive,
                            "tamper_negative": negative, "hardlink_negative": hardlink_negative,
                            "mutable_mode_negative": mode_negative})


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(); sub = top.add_subparsers(dest="command", required=True)
    run = sub.add_parser("validate")
    for name in ("root", "artifact-manifest", "r03-result", "r03-formal",
                 "r03-replay-formal", "r03-delta-root", "r03-replay-input-root",
                 "r05-terminal-result", "r05-terminal-replay-formal",
                 "replay-base-root", "static-smoke", "static-smoke-revalidation",
                 "query-scope-tests", "input-canary-tests", "stage-io-primer-tests", "r06-result-root",
                 "r06-formal-root", "r06-replay-formal-root", "report", "output"):
        run.add_argument(f"--{name}", type=Path, required=True)
    run.add_argument("--device", default="259:10")
    test = sub.add_parser("self-test"); test.add_argument("--scratch", type=Path, required=True)
    test.add_argument("--output", type=Path, required=True)
    return top


def main() -> None:
    args = parser().parse_args()
    try: self_test(args) if args.command == "self-test" else validate(args)
    except (KeyError, OSError, RuntimeError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__": main()
