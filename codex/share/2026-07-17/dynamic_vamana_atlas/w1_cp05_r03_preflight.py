#!/usr/bin/env python3
"""Fail-closed preflight for CP05 cumulative trajectory R03 recovery."""
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


SCHEMA = "dynamic-vamana-w1-cp05-cumulative-r03-preflight-v1"
R01_RUN = "pilot3_sift10m_w1_cp05_trajectory"
R02_RUN = "pilot3_sift10m_w1_cp05_trajectory_r02"
R03_RUN = "pilot3_sift10m_w1_cp05_trajectory_r03"
R03_REPLAY_RUN = "pilot3_w1_cp05_trajectory_replay_r03"
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
    for item in Path("/proc").iterdir():
        if not item.name.isdigit() or int(item.name) in own: continue
        try: command = (item / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError: continue
        if any(token in command for token in (R03_RUN, R03_REPLAY_RUN, "w1_run_cumulative_trajectory.sh")):
            rows.append({"pid": int(item.name), "command": command[:4096]})
    return rows


def validate(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve(strict=True); expected_device = args.device
    r01_result = args.r01_result.resolve(strict=True); r01_formal = args.r01_formal.resolve(strict=False)
    r02_result = args.r02_result.resolve(strict=True); r02_formal = args.r02_formal.resolve(strict=False)
    r02_replay_formal = args.r02_replay_formal.resolve(strict=True)
    r02_delta = args.r02_delta_root.resolve(strict=True)
    r02_replay = args.r02_replay_input_root.resolve(strict=True)
    base_root = args.replay_base_root.resolve(strict=True); smoke_path = args.static_smoke.resolve(strict=True)
    smoke_revalidation_path = args.static_smoke_revalidation.resolve(strict=True)
    query_tests_path = args.query_scope_tests.resolve(strict=True)
    result = args.r03_result_root.resolve(strict=False); formal = args.r03_formal_root.resolve(strict=False)
    replay_formal = args.r03_replay_formal_root.resolve(strict=False)
    replay_inputs = args.r03_replay_input_root.resolve(strict=True); delta = args.r03_delta_root.resolve(strict=True)
    output = args.output.resolve(strict=False)
    require(r01_result == root / f"results/{R01_RUN}" and r02_result == root / f"results/{R02_RUN}",
            "terminal attempt capability path mismatch")
    require(result == root / f"results/{R03_RUN}" and formal == root / f"formal/{R03_RUN}"
            and replay_formal == root / f"formal/{R03_REPLAY_RUN}", "R03 capability path mismatch")
    require(output == result / "preflight/execution_preflight.json", "R03 preflight output path mismatch")
    require(delta == root / "datasets/sift10m/w1_trajectory/execution_deltas_r03", "R03 delta path mismatch")

    r01_execution_path = r01_result / "execution_manifest.json"; r01_execution = load(r01_execution_path)
    require((r01_execution.get("schema"), r01_execution.get("status"),
             r01_execution.get("stopped_phase"), r01_execution.get("exit_code"))
            == ("dynamic-vamana-w1-cp05-cumulative-execution-v1", "stopped_failed", "replay_DGAI", 1),
            "R01 terminal identity mismatch")
    r01_preservation = load(r01_result / "preflight/preservation_after_stop.json")
    require(r01_preservation.get("status") == "pass" and not r01_preservation.get("mismatches"),
            "R01 stop-time preservation is not PASS")
    if r01_formal.exists():
        require(r01_formal.is_dir() and not any(r01_formal.rglob("*")),
                "R01 SIFT10M formal root contains state")
    r01_replay_formal = root / "formal/pilot3_w1_cp05_trajectory_replay"
    require(r01_replay_formal.is_dir(), "R01 replay formal parent evidence absent")
    r01_entries = list(r01_replay_formal.rglob("*"))
    require(len(r01_entries) == 1 and r01_entries[0] == r01_replay_formal / "DGAI"
            and r01_entries[0].is_dir(), "R01 replay formal contains clone/attempt state")
    r01_forbidden = (list(r01_result.glob("**/clone_manifest.json"))
                     + list(r01_result.glob("**/*checkpoint_evidence.json"))
                     + list(r01_result.glob("**/CUMULATIVE_TRAJECTORY_OK")))
    require(not r01_forbidden, "R01 contains clone/checkpoint/completion evidence")

    r02_execution_path = r02_result / "execution_manifest.json"; r02_execution = load(r02_execution_path)
    require((r02_execution.get("schema"), r02_execution.get("status"),
             r02_execution.get("stopped_phase"), r02_execution.get("exit_code"))
            == ("dynamic-vamana-w1-cp05-cumulative-r02-execution-v1",
                "stopped_failed", "replay_DGAI", 1), "R02 terminal identity mismatch")
    require(r02_execution.get("attempts", {}).get("DGAI_replay") == "sequential-cp80-02",
            "R02 replay attempt identity mismatch")
    r02_preservation_path = r02_result / "preflight/preservation_after_stop.json"
    r02_preservation = load(r02_preservation_path)
    require(r02_preservation.get("schema") == "dynamic-vamana-w1-cp05-cumulative-r02-preservation-v1"
            and r02_preservation.get("status") == "pass" and not r02_preservation.get("mismatches"),
            "R02 stop-time preservation is not PASS")
    require(not r02_formal.exists(), "R02 formal attempt unexpectedly exists")
    r02_attempt = r02_replay_formal / "DGAI/sequential-cp80-02"
    require(r02_attempt.is_dir() and (r02_attempt / "clone_manifest.json").is_file(),
            "R02 DGAI replay clone evidence absent")
    r02_query = r02_result / "replay/DGAI/sequential-cp80-02/queries/cp00"
    require(r02_query.is_dir() and len(list(r02_query.glob("*.validation.json"))) == 6,
            "R02 DGAI CP00 query evidence is incomplete")
    require(not (r02_result / "replay/DGAI/sequential-cp80-02/stages").exists()
            and not (r02_result / "replay/DGAI/sequential-cp80-02/queries/cp01").exists()
            and not (r02_result / "replay/DGAI/sequential-cp80-02/queries/cp05").exists()
            and not (r02_result / "replay/OdinANN").exists()
            and not (r02_result / "DGAI").exists()
            and not (r02_result / "OdinANN").exists()
            and not (r02_result / "DiskANN").exists(),
            "R02 advanced beyond DGAI CP00 query gate")
    require(not list(r02_result.glob("**/STAGE_WORKER_OK"))
            and not list(r02_result.glob("**/stage_evidence.json"))
            and not list(r02_result.glob("**/CUMULATIVE_TRAJECTORY_OK")),
            "R02 contains update or completion evidence")

    delta_compare = compare_trees(r02_delta, delta, "R03 execution deltas")
    replay_compare = compare_trees(r02_replay, replay_inputs, "R03 replay inputs")
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

    r02_preflight_path = r02_result / "preflight/execution_preflight.json"; prior = load(r02_preflight_path)
    require(prior.get("schema") == "dynamic-vamana-w1-cp05-cumulative-r02-preflight-v1"
            and prior.get("status") == "pass", "R02 accepted preflight absent")
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

    # result root may contain only newly derived replay inputs and this not-yet-written preflight parent.
    if result.exists():
        allowed_top = {"replay", "preflight"}
        require({entry.name for entry in result.iterdir()} <= allowed_top, "R03 result contains attempt output")
        replay_parent = result / "replay"
        require(replay_parent.is_dir() and
                {entry.name for entry in replay_parent.iterdir()} == {"inputs"} and
                replay_parent / "inputs" == replay_inputs,
                "R03 result/replay contains non-input state")
        require(not any(result.glob("DGAI/**")) and not any(result.glob("OdinANN/**"))
                and not any(result.glob("DiskANN/**")), "R03 result attempt not fresh")
    require(not formal.exists() and not replay_formal.exists(), "R03 formal/replay clone target not fresh")
    require(not args.report.exists(), "R03 final report target is not fresh")
    active = active_w1_processes(); require(not active, "active W1 process exists")
    for path in (root, formal.parent, replay_formal.parent, delta.parent):
        require(mount_device(path) == expected_device, f"large artifact path not on NVMe: {path}")
    free, memory = shutil.disk_usage(root).free, available_memory()
    require(free >= 128 * 1024**3 and memory >= 64 * 1024**3, "launch space/memory guard failed")
    require(os.environ.get("W1_GLOBAL_LOCK_HELD") == "1", "global W1 flock marker absent")

    report = {"schema": SCHEMA, "status": "pass", "run": R03_RUN,
        "attempts": {"DGAI": "trajectory-cp05-03", "OdinANN": "trajectory-cp05-03",
                     "DiskANN": "stale-cp05-03", "replay": "sequential-cp80-03"},
        "terminal_attempts": {
            "R01": {"execution_manifest": identity(r01_execution_path), "status": "stopped_failed",
                "stopped_phase": "replay_DGAI", "exit_code": 1,
                "no_clone_or_checkpoint": True,
                "preservation_after_stop": identity(r01_result / "preflight/preservation_after_stop.json")},
            "R02": {"execution_manifest": identity(r02_execution_path), "status": "stopped_failed",
                "stopped_phase": "replay_DGAI", "exit_code": 1,
                "stopped_before_update_api": True, "no_cp01_cp05_odin_formal_diskann": True,
                "preservation_after_stop": identity(r02_preservation_path)}},
        "r02_r03_delta_identity": delta_compare, "r02_r03_replay_input_identity": replay_compare,
        "immutable_replay_bases": bases, "static_load_smoke": identity(smoke_path),
        "static_smoke_revalidation": identity(smoke_revalidation_path),
        "query_scope_tests": identity(query_tests_path),
        "protected_artifacts": protected, "artifact_manifest": identity(args.artifact_manifest),
        "binaries": binaries,
        "accepted_r02_preflight": identity(r02_preflight_path),
        "diskann_lineage": prior.get("diskann_lineage"),
        "fresh_targets": {"result_root": str(result), "formal_root": str(formal),
            "replay_formal_root": str(replay_formal), "delta_root": str(delta),
            "replay_input_root": str(replay_inputs), "report": str(args.report.resolve(strict=False))},
        "experiment_device": expected_device, "free_bytes": free, "memory_available_bytes": memory,
        "active_w1_processes": active, "held_checkpoints": ["CP10", "CP20"]}
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
    write_new(args.output, {"schema": "dynamic-vamana-w1-cp05-r03-preflight-self-test-v1",
                            "status": "pass", "byte_identity_positive": positive,
                            "tamper_negative": negative, "hardlink_negative": hardlink_negative,
                            "mutable_mode_negative": mode_negative})


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(); sub = top.add_subparsers(dest="command", required=True)
    run = sub.add_parser("validate")
    for name in ("root", "artifact-manifest", "r01-result", "r01-formal", "r02-result",
                 "r02-formal", "r02-replay-formal", "r02-delta-root", "r02-replay-input-root",
                 "replay-base-root", "static-smoke", "static-smoke-revalidation",
                 "query-scope-tests", "r03-result-root",
                 "r03-formal-root", "r03-replay-formal-root", "r03-replay-input-root",
                 "r03-delta-root", "report", "output"):
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
