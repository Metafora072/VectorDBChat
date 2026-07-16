#!/usr/bin/env python3
"""Normalize only the current capability-bound partial clone into an owner-private mutable tree."""
from __future__ import annotations

import argparse
import json
import os
import pwd
import stat
import time
from pathlib import Path


def proc_io() -> dict[str, int]:
    rows: dict[str, int] = {}
    for line in Path("/proc/self/io").read_text().splitlines():
        key, value = line.split(":", 1); rows[key] = int(value.strip())
    return rows


def validate_scope(clone: Path, base: Path) -> tuple[Path, int]:
    allowed = os.environ.get("W1_ALLOWED_CLONE_TARGET")
    helper_pid_text = os.environ.get("W1_CLONE_HELPER_PID")
    if not allowed or not helper_pid_text or not helper_pid_text.isdigit():
        raise SystemExit("mutable clone helper capability/PID absent")
    helper_pid = int(helper_pid_text)
    if os.getppid() != helper_pid:
        raise SystemExit("mutable clone tool is not a direct clone-helper child")
    allowed_path = Path(allowed).resolve(strict=False)
    expected_partial = Path(f"{allowed_path}.partial.{helper_pid}")
    if clone.name != "index" or clone.parent.resolve(strict=True) != expected_partial.resolve(strict=True):
        raise SystemExit("mutable clone root is not the current capability-bound partial/index")
    if base.resolve(strict=True) == clone.resolve(strict=True) or base.resolve(strict=True) in clone.resolve(strict=True).parents:
        raise SystemExit("base/clone identity or nesting refused")
    return expected_partial, helper_pid


def collect(root: Path) -> tuple[list[Path], list[Path]]:
    directories: list[Path] = []; files: list[Path] = []

    def visit(path: Path) -> None:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode): raise SystemExit(f"symlink refused: {path}")
        if stat.S_ISDIR(info.st_mode):
            directories.append(path)
            with os.scandir(path) as entries: children = sorted((Path(entry.path) for entry in entries), key=lambda row: row.name)
            for child in children: visit(child)
        elif stat.S_ISREG(info.st_mode):
            if info.st_nlink != 1: raise SystemExit(f"hard-link risk refused: {path} nlink={info.st_nlink}")
            files.append(path)
        else: raise SystemExit(f"unsupported clone object refused: {path}")

    visit(root)
    return directories, files


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--clone-root", type=Path, required=True)
    parser.add_argument("--base-root", type=Path, required=True); parser.add_argument("--owner", required=True)
    parser.add_argument("--system", choices=("DGAI", "OdinANN"), required=True); parser.add_argument("--output-manifest", type=Path, required=True)
    args = parser.parse_args(); clone = args.clone_root.resolve(strict=True); base = args.base_root.resolve(strict=True)
    partial, helper_pid = validate_scope(clone, base)
    if args.output_manifest.parent.resolve(strict=True) != partial or args.output_manifest.exists():
        raise SystemExit("normalization manifest must be a fresh file in the current partial root")
    account = pwd.getpwnam(args.owner); uid, gid = account.pw_uid, account.pw_gid
    directories, files = collect(clone)
    started = time.monotonic_ns(); io_before = proc_io(); changed = ownership_changes = mode_changes = 0
    inject = os.environ.get("W1_MUTABLE_FAILURE_INJECTION", "")
    total = len(files) + len(directories)
    for path in files:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if info.st_uid != uid or info.st_gid != gid:
                os.fchown(fd, uid, gid); ownership_changes += 1
            if stat.S_IMODE(info.st_mode) != 0o600: mode_changes += 1
            os.fchmod(fd, 0o600)
        finally: os.close(fd)
        changed += 1
        if inject == "normalization_mid" and changed >= max(1, total // 2): raise SystemExit("injected normalization_mid failure")
    for path in reversed(directories):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if info.st_uid != uid or info.st_gid != gid:
                os.fchown(fd, uid, gid); ownership_changes += 1
            if stat.S_IMODE(info.st_mode) != 0o700: mode_changes += 1
            os.fchmod(fd, 0o700)
        finally: os.close(fd)
        changed += 1
        if inject == "normalization_mid" and changed >= max(1, total // 2): raise SystemExit("injected normalization_mid failure")
    for path in directories + files:
        info = path.lstat(); expected = 0o700 if stat.S_ISDIR(info.st_mode) else 0o600
        if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (uid, gid, expected):
            raise SystemExit(f"mutable normalization postcondition failed: {path}")
    completed = time.monotonic_ns(); io_after = proc_io()
    report = {"schema": "dynamic-vamana-w1-mutable-normalization-v1", "status": "pass", "system": args.system,
              "clone_root": str(clone), "base_root": str(base), "helper_pid": helper_pid,
              "owner": args.owner, "owner_uid": uid, "owner_gid": gid, "directory_mode": "0700", "file_mode": "0600",
              "directories": len(directories), "regular_files": len(files), "normalization_started_ns": started,
              "normalization_completed_ns": completed, "elapsed_seconds": (completed - started) / 1e9,
              "ownership_changes": ownership_changes, "mode_changes": mode_changes,
              "metadata_operations": ownership_changes + len(files) + len(directories),
              "proc_io_before": io_before, "proc_io_after": io_after}
    args.output_manifest.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
