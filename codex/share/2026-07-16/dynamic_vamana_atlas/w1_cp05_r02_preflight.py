#!/usr/bin/env python3
"""Fail-closed preflight for CP05 cumulative trajectory R02 recovery."""
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


SCHEMA = "dynamic-vamana-w1-cp05-cumulative-r02-preflight-v1"
OLD_RUN = "pilot3_sift10m_w1_cp05_trajectory"
R02_RUN = "pilot3_sift10m_w1_cp05_trajectory_r02"
R02_REPLAY_RUN = "pilot3_w1_cp05_trajectory_replay_r02"


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
    builder_path = Path(__file__).with_name("w1_replay_base_recovery.py")
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
        if any(token in command for token in (R02_RUN, R02_REPLAY_RUN, "w1_run_cumulative_trajectory.sh")):
            rows.append({"pid": int(item.name), "command": command[:4096]})
    return rows


def validate(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve(strict=True); expected_device = args.device
    old_result = args.old_result.resolve(strict=True); old_formal = args.old_formal.resolve(strict=False)
    old_delta = args.old_delta_root.resolve(strict=True); old_replay = args.old_replay_input_root.resolve(strict=True)
    base_root = args.replay_base_root.resolve(strict=True); smoke_path = args.static_smoke.resolve(strict=True)
    result = args.r02_result_root.resolve(strict=False); formal = args.r02_formal_root.resolve(strict=False)
    replay_formal = args.r02_replay_formal_root.resolve(strict=False)
    replay_inputs = args.r02_replay_input_root.resolve(strict=True); delta = args.r02_delta_root.resolve(strict=True)
    output = args.output.resolve(strict=False)
    require(result == root / f"results/{R02_RUN}" and formal == root / f"formal/{R02_RUN}"
            and replay_formal == root / f"formal/{R02_REPLAY_RUN}", "R02 capability path mismatch")
    require(output == result / "preflight/execution_preflight.json", "R02 preflight output path mismatch")
    require(delta == root / "datasets/sift10m/w1_trajectory/execution_deltas_r02", "R02 delta path mismatch")

    execution_path = old_result / "execution_manifest.json"; execution = load(execution_path)
    require((execution.get("schema"), execution.get("status"), execution.get("stopped_phase"), execution.get("exit_code"))
            == ("dynamic-vamana-w1-cp05-cumulative-execution-v1", "stopped_failed", "replay_DGAI", 1),
            "old attempt terminal identity mismatch")
    old_preservation = load(old_result / "preflight/preservation_after_stop.json")
    require(old_preservation.get("status") == "pass" and not old_preservation.get("mismatches"),
            "old stop-time preservation is not PASS")
    if old_formal.exists():
        require(old_formal.is_dir() and not any(old_formal.rglob("*")),
                "old SIFT10M formal root contains state")
    old_replay_formal = root / "formal/pilot3_w1_cp05_trajectory_replay"
    require(old_replay_formal.is_dir(), "old replay formal parent evidence absent")
    old_replay_entries = list(old_replay_formal.rglob("*"))
    require(len(old_replay_entries) == 1 and old_replay_entries[0] == old_replay_formal / "DGAI"
            and old_replay_entries[0].is_dir(), "old replay formal contains clone/attempt state")
    forbidden = list(old_result.glob("**/clone_manifest.json")) + list(old_result.glob("**/*checkpoint_evidence.json"))
    forbidden += list(old_result.glob("**/CUMULATIVE_TRAJECTORY_OK"))
    require(not forbidden, "old attempt contains clone/checkpoint/completion evidence")

    delta_compare = compare_trees(old_delta, delta, "R02 execution deltas")
    replay_compare = compare_trees(old_replay, replay_inputs, "R02 replay inputs")
    bases = {system: verify_base(base_root, system) for system in ("DGAI", "OdinANN")}
    smoke = load(smoke_path)
    require(smoke.get("schema") == "dynamic-vamana-w1-cp05-r02-static-load-smoke-v1"
            and smoke.get("status") == "pass" and smoke.get("expected_shape") == [36, 10],
            "R02 static load smoke not PASS")
    for system in ("DGAI", "OdinANN"):
        require(smoke.get("systems", {}).get(system, {}).get("status") == "pass", f"{system} smoke absent")
        require(smoke["systems"][system]["immutable_base_manifest"]["sha256"]
                == bases[system]["manifest"]["sha256"], f"{system} smoke/base lineage mismatch")

    old_preflight_path = old_result / "preflight/execution_preflight.json"; prior = load(old_preflight_path)
    require(prior.get("status") == "pass", "old accepted preflight absent")
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
        require({entry.name for entry in result.iterdir()} <= allowed_top, "R02 result contains attempt output")
        replay_parent = result / "replay"
        require(replay_parent.is_dir() and
                {entry.name for entry in replay_parent.iterdir()} == {"inputs"} and
                replay_parent / "inputs" == replay_inputs,
                "R02 result/replay contains non-input state")
        require(not any(result.glob("DGAI/**")) and not any(result.glob("OdinANN/**"))
                and not any(result.glob("DiskANN/**")), "R02 result attempt not fresh")
    require(not formal.exists() and not replay_formal.exists(), "R02 formal/replay clone target not fresh")
    require(not args.report.exists(), "R02 final report target is not fresh")
    active = active_w1_processes(); require(not active, "active W1 process exists")
    for path in (root, formal.parent, replay_formal.parent, delta.parent):
        require(mount_device(path) == expected_device, f"large artifact path not on NVMe: {path}")
    free, memory = shutil.disk_usage(root).free, available_memory()
    require(free >= 128 * 1024**3 and memory >= 64 * 1024**3, "launch space/memory guard failed")
    require(os.environ.get("W1_GLOBAL_LOCK_HELD") == "1", "global W1 flock marker absent")

    report = {"schema": SCHEMA, "status": "pass", "run": R02_RUN,
        "attempts": {"DGAI": "trajectory-cp05-02", "OdinANN": "trajectory-cp05-02",
                     "DiskANN": "stale-cp05-02", "replay": "sequential-cp80-02"},
        "old_attempt": {"execution_manifest": identity(execution_path), "status": "stopped_failed",
            "stopped_phase": "replay_DGAI", "exit_code": 1, "no_clone_or_checkpoint": True,
            "old_replay_formal_parent": str(old_replay_formal.resolve()),
            "old_replay_formal_only_empty_DGAI_parent": True,
            "preservation_after_stop": identity(old_result / "preflight/preservation_after_stop.json")},
        "old_new_delta_identity": delta_compare, "old_new_replay_input_identity": replay_compare,
        "immutable_replay_bases": bases, "static_load_smoke": identity(smoke_path),
        "protected_artifacts": protected, "artifact_manifest": identity(args.artifact_manifest),
        "binaries": binaries,
        "accepted_preflight": identity(old_preflight_path),
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
    write_new(args.output, {"schema": "dynamic-vamana-w1-cp05-r02-preflight-self-test-v1",
                            "status": "pass", "byte_identity_positive": positive,
                            "tamper_negative": negative, "hardlink_negative": hardlink_negative,
                            "mutable_mode_negative": mode_negative})


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(); sub = top.add_subparsers(dest="command", required=True)
    run = sub.add_parser("validate")
    for name in ("root", "artifact-manifest", "old-result", "old-formal", "old-delta-root",
                 "old-replay-input-root", "replay-base-root", "static-smoke", "r02-result-root",
                 "r02-formal-root", "r02-replay-formal-root", "r02-replay-input-root", "r02-delta-root",
                 "report", "output"):
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
