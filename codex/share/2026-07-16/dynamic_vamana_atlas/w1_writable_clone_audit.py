#!/usr/bin/env python3
"""Live no-follow writable-clone and immutable-base denial audit."""
from __future__ import annotations

import argparse
import errno
import json
import os
import pwd
import secrets
import stat
from pathlib import Path


DENIAL_ERRNOS = {errno.EACCES, errno.EPERM, errno.EROFS}


def collect(root: Path) -> tuple[list[Path], list[Path]]:
    directories: list[Path] = []; files: list[Path] = []
    def visit(path: Path) -> None:
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            directories.append(path)
            with os.scandir(path) as entries: children = sorted((Path(row.path) for row in entries), key=lambda row: row.name)
            for child in children: visit(child)
        elif stat.S_ISREG(info.st_mode):
            if info.st_nlink != 1: raise SystemExit(f"hard-link risk refused: {path}")
            files.append(path)
        else: raise SystemExit(f"unsupported object in writable audit: {path}")
    visit(root.resolve(strict=True)); return directories, files


def directory_cycle(path: Path, must_succeed: bool) -> None:
    directory_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    first = f".w1-mutable-audit-{os.getpid()}-{secrets.token_hex(8)}"
    second = first + ".renamed"; created = False
    try:
        try:
            fd = os.open(first, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600, dir_fd=directory_fd)
            os.close(fd); created = True
            if not must_succeed: raise SystemExit(f"immutable base directory unexpectedly writable: {path}")
            os.rename(first, second, src_dir_fd=directory_fd, dst_dir_fd=directory_fd); created = False
            os.unlink(second, dir_fd=directory_fd)
        except OSError as exc:
            if must_succeed or exc.errno not in DENIAL_ERRNOS: raise
    finally:
        if created:
            try: os.unlink(first, dir_fd=directory_fd)
            except FileNotFoundError: pass
        try: os.unlink(second, dir_fd=directory_fd)
        except FileNotFoundError: pass
        os.close(directory_fd)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--clone-root", type=Path, required=True)
    parser.add_argument("--base-root", type=Path, required=True); parser.add_argument("--owner", required=True)
    parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    account = pwd.getpwnam(args.owner)
    if os.geteuid() != account.pw_uid or os.getegid() != account.pw_gid:
        raise SystemExit("writable audit must execute as the configured owner uid/gid")
    clone = args.clone_root.resolve(strict=True); base = args.base_root.resolve(strict=True)
    clone_dirs, clone_files = collect(clone); base_dirs, base_files = collect(base)
    if os.environ.get("W1_MUTABLE_FAILURE_INJECTION") == "live_audit": raise SystemExit("injected live_audit failure")
    for path in clone_files:
        fd = os.open(path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW); os.close(fd)
    for path in clone_dirs: directory_cycle(path, True)
    base_file_denials = 0
    for path in base_files:
        if stat.S_IMODE(path.lstat().st_mode) & 0o222: raise SystemExit(f"immutable base file has write bit: {path}")
        try: fd = os.open(path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
        except OSError as exc:
            if exc.errno not in DENIAL_ERRNOS: raise
            base_file_denials += 1
        else:
            os.close(fd); raise SystemExit(f"immutable base file unexpectedly writable: {path}")
    for path in base_dirs:
        if stat.S_IMODE(path.lstat().st_mode) & 0o222: raise SystemExit(f"immutable base directory has write bit: {path}")
        directory_cycle(path, False)
    if args.output.exists(): raise SystemExit("writable audit output overwrite refused")
    report = {"schema": "dynamic-vamana-w1-writable-clone-audit-v1", "status": "pass", "run_uid": os.geteuid(), "run_gid": os.getegid(),
              "clone_root": str(clone), "base_root": str(base), "regular_file_open_tests": len(clone_files),
              "directory_create_rename_tests": len(clone_dirs), "base_file_write_denial_tests": base_file_denials,
              "base_directory_write_denial_tests": len(base_dirs), "temporary_files_remaining": False}
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
