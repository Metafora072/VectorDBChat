#!/usr/bin/env python3
"""Create or read-only verify lineage-bound immutable SIFT1M replay bases.

The production paths and accepted R07 lineage are intentionally fixed.  A
successful create publishes the entire cp00 directory with one atomic rename;
an existing final directory is never modified and can only be verified.
"""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import pwd
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SCHEMA = "dynamic-vamana-w1-immutable-replay-base-v1"
ACCEPTED_RUN = "pilot3_w1_formal_path_replay_r07"
ACCEPTED_ATTEMPT = "replay-01"
EXPECTED_DEVICE = "259:10"
SYSTEMS = ("DGAI", "OdinANN")
FINAL_REL = Path("formal/pilot3_w1_cp05_replay_bases_v1")
SOURCE_REL = {
    "DGAI": Path("index/atlas1m/DGAI/sift1m"),
    "OdinANN": Path("index/atlas1m/OdinANN/sift1m"),
}
EVIDENCE_NAMES = (
    "immutable_replay_base_manifest.json",
    "base_content.tsv",
    "base_mode.tsv",
    "source_content_before.tsv",
    "source_content_after.tsv",
    "source_mode_before.tsv",
    "source_mode_after.tsv",
    "write_denial_audit.json",
    "IMMUTABLE_REPLAY_BASE_OK",
)


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        fail(f"identity target is not a regular file: {path}")
    return {"realpath": str(path), "size": info.st_size, "sha256": sha256_file(path)}


def identity_as(path: Path, published_path: Path) -> dict[str, Any]:
    """Identity bytes at a partial path using their post-rename realpath."""
    current = identity(path)
    current["realpath"] = str(published_path.absolute())
    return current


def device(path: Path) -> str:
    info = path.stat()
    return f"{os.major(info.st_dev)}:{os.minor(info.st_dev)}"


def safe_walk(root: Path) -> list[tuple[Path, str, os.stat_result]]:
    """Walk without following links and reject every non-dir/non-regular node."""
    root = root.resolve(strict=True)
    rows: list[tuple[Path, str, os.stat_result]] = []

    def visit(path: Path, relative: str) -> None:
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            kind = "directory"
        elif stat.S_ISREG(info.st_mode):
            kind = "regular"
            if info.st_nlink != 1:
                fail(f"regular file hard-link count is not one: {path} nlink={info.st_nlink}")
        else:
            fail(f"unsupported source object: {path} mode={info.st_mode:o}")
        rows.append((path, relative, info))
        if kind == "directory":
            with os.scandir(path) as entries:
                names = sorted(entry.name for entry in entries)
            for name in names:
                visit(path / name, name if relative == "." else f"{relative}/{name}")

    visit(root, ".")
    return rows


def content_bytes(root: Path) -> bytes:
    lines: list[str] = []
    for path, relative, info in safe_walk(root):
        if stat.S_ISREG(info.st_mode):
            lines.append(f"{relative}\t{info.st_size}\t{sha256_file(path)}\n")
    return "".join(lines).encode()


def mode_bytes(root: Path) -> bytes:
    lines = ["relative_path\ttype\tuid\tgid\tmode_octal\tinode\tlink_count\n"]
    for _path, relative, info in safe_walk(root):
        kind = "directory" if stat.S_ISDIR(info.st_mode) else "regular"
        lines.append(
            f"{relative}\t{kind}\t{info.st_uid}\t{info.st_gid}\t"
            f"{stat.S_IMODE(info.st_mode):04o}\t{info.st_ino}\t{info.st_nlink}\n"
        )
    return "".join(lines).encode()


def tree_space(root: Path) -> dict[str, int]:
    apparent = allocated = regular = directories = 0
    for _path, _relative, info in safe_walk(root):
        apparent += info.st_size
        allocated += info.st_blocks * 512
        if stat.S_ISDIR(info.st_mode):
            directories += 1
        else:
            regular += 1
    return {
        "apparent_bytes": apparent,
        "allocated_bytes": allocated,
        "regular_file_count": regular,
        "directory_count": directories,
    }


def block_snapshot(majmin: str) -> dict[str, int]:
    fields = (Path("/sys/dev/block") / majmin / "stat").read_text().split()
    if len(fields) < 11:
        fail(f"invalid block-device stat for {majmin}")
    return {
        "read_bytes": int(fields[2]) * 512,
        "write_bytes": int(fields[6]) * 512,
        "read_ios": int(fields[0]),
        "write_ios": int(fields[4]),
    }


def block_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {key: after[key] - before[key] for key in before}


def proc_io_snapshot() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/self/io").read_text().splitlines():
        key, value = line.split(":", 1)
        if key in ("read_bytes", "write_bytes", "rchar", "wchar"):
            values[key] = int(value.strip())
    return values


def open_writable_source_fds(source: Path) -> list[dict[str, Any]]:
    """Find live O_WRONLY/O_RDWR descriptors referring to any source inode."""
    if os.geteuid() != 0:
        fail("writable-FD lineage scan requires root")
    objects = {(info.st_dev, info.st_ino) for _p, _r, info in safe_walk(source)}
    hits: list[dict[str, Any]] = []
    for proc in sorted(Path("/proc").iterdir(), key=lambda p: p.name):
        if not proc.name.isdigit():
            continue
        fd_root = proc / "fd"
        try:
            fds = list(fd_root.iterdir())
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        for fd in fds:
            try:
                info = fd.stat()
                if (info.st_dev, info.st_ino) not in objects:
                    continue
                flags_line = next(line for line in (proc / "fdinfo" / fd.name).read_text().splitlines()
                                  if line.startswith("flags:"))
                flags = int(flags_line.split()[1], 8)
                if flags & os.O_ACCMODE in (os.O_WRONLY, os.O_RDWR):
                    try:
                        target = os.readlink(fd)
                    except OSError:
                        target = "unavailable"
                    hits.append({"pid": int(proc.name), "fd": int(fd.name), "flags_octal": f"{flags:o}",
                                 "target": target, "device": f"{os.major(info.st_dev)}:{os.minor(info.st_dev)}",
                                 "inode": info.st_ino})
            except (StopIteration, FileNotFoundError, PermissionError, ProcessLookupError, OSError, ValueError):
                continue
    return hits


def lineage_paths(root: Path, system: str) -> dict[str, Path]:
    formal = root / f"formal/{ACCEPTED_RUN}/{system}/{ACCEPTED_ATTEMPT}"
    result = root / f"results/{ACCEPTED_RUN}/{system}/{ACCEPTED_ATTEMPT}"
    return {
        "base_before": formal / "base_before.tsv",
        "base_after": formal / "base_after.tsv",
        "base_after_attempt": result / "base_after_attempt.tsv",
        "clone_manifest": formal / "clone_manifest.json",
        "system_marker": result / "FORMAL_W1_CANARY_OK",
        "global_marker": root / f"results/{ACCEPTED_RUN}/FORMAL_PATH_REPLAY_OK",
    }


def validate_lineage(root: Path, system: str, source: Path) -> tuple[bytes, dict[str, Any]]:
    paths = lineage_paths(root, system)
    for name, path in paths.items():
        if not path.is_file() or path.is_symlink():
            fail(f"accepted R07 lineage file absent or unsafe: {name}: {path}")
    before = paths["base_before"].read_bytes()
    if not before or paths["base_after"].read_bytes() != before or paths["base_after_attempt"].read_bytes() != before:
        fail(f"accepted R07 before/after lineage mismatch: {system}")
    clone = json.loads(paths["clone_manifest"].read_text())
    if clone.get("schema") != "dynamic-vamana-w1-clone-v2" or clone.get("system") != system:
        fail(f"accepted R07 clone manifest identity mismatch: {system}")
    if Path(clone.get("base", "")).resolve(strict=True) != source:
        fail(f"accepted R07 clone manifest source mismatch: {system}")
    evidence = {name: identity(path) for name, path in paths.items()}
    evidence.update({"run": ACCEPTED_RUN, "attempt": ACCEPTED_ATTEMPT})
    return before, evidence


def check_source(root: Path, system: str) -> Path:
    expected = root / SOURCE_REL[system]
    source = expected.resolve(strict=True)
    if source != expected.absolute():
        fail(f"source is not the exact non-symlink atlas1m path: {expected} -> {source}")
    if device(source) != EXPECTED_DEVICE:
        fail(f"source is not on expected project NVMe {EXPECTED_DEVICE}: {source}")
    safe_walk(source)
    return source


def copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(mode=0o700)

    def copy_dir(src: Path, dst: Path) -> None:
        with os.scandir(src) as entries:
            names = sorted(entry.name for entry in entries)
        for name in names:
            src_path, dst_path = src / name, dst / name
            info = src_path.lstat()
            if stat.S_ISDIR(info.st_mode):
                dst_path.mkdir(mode=0o700)
                copy_dir(src_path, dst_path)
            elif stat.S_ISREG(info.st_mode):
                if info.st_nlink != 1:
                    fail(f"source hard link appeared during copy: {src_path}")
                in_fd = os.open(src_path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
                try:
                    out_fd = os.open(dst_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
                    try:
                        while True:
                            block = os.read(in_fd, 8 << 20)
                            if not block:
                                break
                            view = memoryview(block)
                            while view:
                                written = os.write(out_fd, view)
                                view = view[written:]
                        os.fsync(out_fd)
                    finally:
                        os.close(out_fd)
                finally:
                    os.close(in_fd)
            else:
                fail(f"unsupported object appeared during copy: {src_path}")
        dir_fd = os.open(dst, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    copy_dir(source, destination)


def assert_inode_independent(source: Path, copy: Path) -> int:
    source_rows = {relative: info for _path, relative, info in safe_walk(source)}
    copy_rows = {relative: info for _path, relative, info in safe_walk(copy)}
    if set(source_rows) != set(copy_rows):
        fail("copy/source path sets differ")
    checked = 0
    for relative, src in source_rows.items():
        dst = copy_rows[relative]
        if stat.S_IFMT(src.st_mode) != stat.S_IFMT(dst.st_mode):
            fail(f"copy/source type differs: {relative}")
        if (src.st_dev, src.st_ino) == (dst.st_dev, dst.st_ino):
            fail(f"copy aliases source inode: {relative}")
        checked += 1
    return checked


def normalize_immutable(root: Path) -> None:
    rows = safe_walk(root)
    for path, _relative, info in rows:
        if stat.S_ISREG(info.st_mode):
            os.chown(path, 0, 0, follow_symlinks=False)
            os.chmod(path, 0o444, follow_symlinks=False)
    for path, _relative, info in reversed(rows):
        if stat.S_ISDIR(info.st_mode):
            os.chown(path, 0, 0, follow_symlinks=False)
            os.chmod(path, 0o555, follow_symlinks=False)


def assert_immutable_policy(root: Path) -> dict[str, int]:
    files = directories = 0
    for path, _relative, info in safe_walk(root):
        is_dir = stat.S_ISDIR(info.st_mode)
        expected = 0o555 if is_dir else 0o444
        if info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != expected:
            fail(f"immutable policy mismatch: {path}")
        if is_dir:
            directories += 1
        else:
            files += 1
    return {"regular_files": files, "directories": directories}


def denial_child(root: Path) -> dict[str, Any]:
    account = pwd.getpwnam("ubuntu")
    if (os.geteuid(), os.getegid()) != (account.pw_uid, account.pw_gid):
        fail("denial child is not running as ubuntu")
    files_checked = dirs_checked = open_denied = create_denied = rename_denied = unlink_denied = 0
    for path, _relative, info in safe_walk(root):
        if stat.S_ISREG(info.st_mode):
            files_checked += 1
            try:
                fd = os.open(path, os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW)
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EPERM, errno.EROFS):
                    raise
                open_denied += 1
            else:
                os.close(fd)
                fail(f"ubuntu unexpectedly opened immutable file O_RDWR: {path}")
        else:
            dirs_checked += 1
            children = sorted(path.iterdir(), key=lambda p: p.name)
            if not children:
                fail(f"cannot perform rename/unlink denial audit on empty immutable directory: {path}")
            child = children[0]
            nonce = f".w1-denial-{os.getpid()}"
            dir_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                try:
                    fd = os.open(nonce, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                                 0o600, dir_fd=dir_fd)
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EPERM, errno.EROFS):
                        raise
                    create_denied += 1
                else:
                    os.close(fd)
                    fail(f"ubuntu unexpectedly created file in immutable directory: {path}")
                try:
                    os.rename(child.name, nonce, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EPERM, errno.EROFS):
                        raise
                    rename_denied += 1
                else:
                    fail(f"ubuntu unexpectedly renamed immutable child: {child}")
                try:
                    if child.is_dir():
                        os.rmdir(child.name, dir_fd=dir_fd)
                    else:
                        os.unlink(child.name, dir_fd=dir_fd)
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EPERM, errno.EROFS):
                        raise
                    unlink_denied += 1
                else:
                    fail(f"ubuntu unexpectedly unlinked immutable child: {child}")
            finally:
                os.close(dir_fd)
    return {
        "schema": "dynamic-vamana-w1-immutable-write-denial-v1",
        "status": "pass",
        "audit_uid": os.geteuid(),
        "audit_gid": os.getegid(),
        "files_checked": files_checked,
        "directories_checked": dirs_checked,
        "open_rdwr_denied": open_denied,
        "create_denied": create_denied,
        "rename_denied": rename_denied,
        "unlink_denied": unlink_denied,
    }


def run_denial_audit(script: Path, root: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["runuser", "-u", "ubuntu", "--", sys.executable, str(script), "denial-child", "--root", str(root)],
        text=True, capture_output=True,
    )
    if result.returncode != 0:
        fail(f"ubuntu write-denial audit failed: stdout={result.stdout!r} stderr={result.stderr!r}")
    report = json.loads(result.stdout)
    counts = (report.get("files_checked", 0), report.get("directories_checked", 0))
    if report.get("status") != "pass" or min(counts) < 1:
        fail("ubuntu write-denial audit returned incomplete evidence")
    if report["open_rdwr_denied"] != counts[0] or any(report[key] != counts[1]
            for key in ("create_denied", "rename_denied", "unlink_denied")):
        fail("ubuntu write-denial counts are not exact")
    return report


def write_new(path: Path, payload: bytes, mode: int = 0o600) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, mode)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_tree(root: Path) -> None:
    for path, _relative, info in reversed(safe_walk(root)):
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        if stat.S_ISDIR(info.st_mode):
            flags |= os.O_DIRECTORY
        fd = os.open(path, flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def remove_partial(path: Path) -> None:
    if not path.exists():
        return
    # The partial is capability-bound and never follows links.
    if path.is_symlink() or ".partial." not in path.name:
        fail(f"unsafe partial cleanup refused: {path}")
    for directory, dirs, files in os.walk(path, topdown=False, followlinks=False):
        base = Path(directory)
        os.chmod(base, 0o700, follow_symlinks=False)
        for name in files:
            item = base / name
            if item.is_symlink():
                item.unlink()
            else:
                os.chmod(item, 0o600, follow_symlinks=False)
                item.unlink()
        for name in dirs:
            item = base / name
            os.chmod(item, 0o700, follow_symlinks=False)
            item.rmdir()
    path.rmdir()


def manifest_projection(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": manifest.get("schema"), "status": manifest.get("status"), "system": manifest.get("system"),
        "accepted_run": manifest.get("accepted_r07", {}).get("run"),
        "accepted_attempt": manifest.get("accepted_r07", {}).get("attempt"),
        "source_realpath": manifest.get("source", {}).get("realpath"),
        "immutable_base_realpath": manifest.get("immutable_base", {}).get("realpath"),
        "owner_uid": manifest.get("immutable_base", {}).get("owner_uid"),
        "owner_gid": manifest.get("immutable_base", {}).get("owner_gid"),
        "directory_mode": manifest.get("immutable_base", {}).get("directory_mode"),
        "file_mode": manifest.get("immutable_base", {}).get("file_mode"),
        "copy_method": manifest.get("copy", {}).get("method"),
        "atomic_publish": manifest.get("atomic_publish"),
    }


def verify_final(root: Path, system: str, *, run_denial: bool = True) -> dict[str, Any]:
    if os.geteuid() != 0:
        fail("immutable replay-base read-only verification requires root")
    source = check_source(root, system)
    accepted, accepted_evidence = validate_lineage(root, system, source)
    final = root / FINAL_REL / system / "cp00"
    if not final.is_dir() or final.is_symlink():
        fail(f"immutable replay base final absent or unsafe: {final}")
    expected_names = sorted(("index",) + EVIDENCE_NAMES)
    if sorted(item.name for item in final.iterdir()) != expected_names:
        fail(f"immutable replay base final contains missing/extra entries: {final}")
    final_info = final.lstat()
    if (final_info.st_uid, final_info.st_gid, stat.S_IMODE(final_info.st_mode)) != (0, 0, 0o555):
        fail("immutable replay base cp00 directory policy mismatch")
    for name in EVIDENCE_NAMES:
        info = (final / name).lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (0, 0, 0o444)):
            fail(f"immutable replay base evidence policy mismatch: {name}")
    base = final / "index"
    if base.resolve(strict=True) != base.absolute() or device(base) != EXPECTED_DEVICE:
        fail("immutable replay base path/device mismatch")
    manifest_path = final / "immutable_replay_base_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest_projection(manifest) != {
        "schema": SCHEMA, "status": "pass", "system": system,
        "accepted_run": ACCEPTED_RUN, "accepted_attempt": ACCEPTED_ATTEMPT,
        "source_realpath": str(source), "immutable_base_realpath": str(base),
        "owner_uid": 0, "owner_gid": 0, "directory_mode": "0555", "file_mode": "0444",
        "copy_method": "buffered_byte_copy_no_reflink_no_hardlink", "atomic_publish": True,
    }:
        fail("immutable replay base manifest fixed fields mismatch")
    if manifest.get("accepted_r07") != accepted_evidence:
        fail("immutable replay base accepted R07 evidence is stale")
    current_source_content = content_bytes(source)
    current_source_mode = mode_bytes(source)
    live_writable = open_writable_source_fds(source)
    if live_writable:
        fail(f"source has live writable file descriptors during verification: {json.dumps(live_writable, sort_keys=True)}")
    if current_source_content != accepted:
        fail("current source content no longer equals accepted R07 lineage")
    for name in ("source_content_before.tsv", "source_content_after.tsv"):
        if (final / name).read_bytes() != current_source_content:
            fail(f"source content evidence mismatch: {name}")
    for name in ("source_mode_before.tsv", "source_mode_after.tsv"):
        if (final / name).read_bytes() != current_source_mode:
            fail(f"source mode evidence mismatch: {name}")
    base_content = content_bytes(base)
    base_mode = mode_bytes(base)
    if base_content != accepted or (final / "base_content.tsv").read_bytes() != base_content:
        fail("immutable replay base content mismatch")
    if (final / "base_mode.tsv").read_bytes() != base_mode:
        fail("immutable replay base mode evidence mismatch")
    policy = assert_immutable_policy(base)
    source_rows = {relative: info for _p, relative, info in safe_walk(source)}
    base_rows = {relative: info for _p, relative, info in safe_walk(base)}
    if set(source_rows) != set(base_rows) or any(
        (source_rows[key].st_dev, source_rows[key].st_ino) == (base_rows[key].st_dev, base_rows[key].st_ino)
        for key in source_rows
    ):
        fail("immutable replay base is not inode-independent")
    if manifest.get("source", {}).get("content_before") != identity(final / "source_content_before.tsv"):
        fail("manifest source content identity mismatch")
    if manifest.get("source", {}).get("content_after") != identity(final / "source_content_after.tsv"):
        fail("manifest source after identity mismatch")
    if manifest.get("source", {}).get("mode_before") != identity(final / "source_mode_before.tsv"):
        fail("manifest source mode identity mismatch")
    if manifest.get("source", {}).get("mode_after") != identity(final / "source_mode_after.tsv"):
        fail("manifest source mode after identity mismatch")
    if manifest.get("immutable_base", {}).get("content_manifest") != identity(final / "base_content.tsv"):
        fail("manifest base content identity mismatch")
    if manifest.get("immutable_base", {}).get("mode_manifest") != identity(final / "base_mode.tsv"):
        fail("manifest base mode identity mismatch")
    if manifest.get("immutable_base", {}).get("content") != identity(final / "base_content.tsv"):
        fail("manifest base content alias mismatch")
    if manifest.get("immutable_base", {}).get("mode") != identity(final / "base_mode.tsv"):
        fail("manifest base mode alias mismatch")
    if manifest.get("immutable_base_realpath") != str(base):
        fail("flat immutable base realpath mismatch")
    if manifest.get("content_manifest_sha256") != sha256_file(final / "base_content.tsv"):
        fail("flat content manifest SHA mismatch")
    if manifest.get("mode_manifest_sha256") != sha256_file(final / "base_mode.tsv"):
        fail("flat mode manifest SHA mismatch")
    expected_space = tree_space(base)
    for key, value in expected_space.items():
        if manifest.get("immutable_base", {}).get(key) != value:
            fail(f"manifest base space/count mismatch: {key}")
    if manifest.get("immutable_base", {}).get("inode_independent") is not True:
        fail("manifest inode independence absent")
    if manifest.get("source", {}).get("open_writable_fd_count") != 0:
        fail("manifest writable-FD evidence is not zero")
    if (final / "IMMUTABLE_REPLAY_BASE_OK").read_text() != SCHEMA + "\n":
        fail("immutable replay base completion marker mismatch")
    stored_denial = json.loads((final / "write_denial_audit.json").read_text())
    if manifest.get("write_denial") != identity(final / "write_denial_audit.json") or stored_denial.get("status") != "pass":
        fail("stored write-denial evidence mismatch")
    denial = run_denial_audit(Path(__file__).resolve(), base) if run_denial else stored_denial
    if run_denial and {key: denial[key] for key in denial if key not in ()} != stored_denial:
        fail("live write-denial audit differs from published evidence")
    return {
        "schema": SCHEMA, "status": "pass", "action": "verified_read_only", "system": system,
        "final_root": str(final), "immutable_base": str(base),
        "manifest_sha256": sha256_file(manifest_path), "content_manifest_sha256": sha256_bytes(base_content),
        "mode_manifest_sha256": sha256_bytes(base_mode), "policy": policy,
        "write_denial": denial,
    }


def ensure(root: Path, system: str, *, injection: str = "") -> dict[str, Any]:
    if os.geteuid() != 0:
        fail("immutable replay-base creation requires root")
    root = root.resolve(strict=True)
    if device(root) != EXPECTED_DEVICE:
        fail(f"atlas root is not on expected project NVMe {EXPECTED_DEVICE}")
    final = root / FINAL_REL / system / "cp00"
    if final.exists():
        return verify_final(root, system)
    source = check_source(root, system)
    accepted, accepted_evidence = validate_lineage(root, system, source)
    source_content_before = content_bytes(source)
    source_mode_before = mode_bytes(source)
    if source_content_before != accepted:
        fail("current source content does not equal accepted R07 base-before manifest")
    writable = open_writable_source_fds(source)
    if writable:
        fail(f"source has live writable file descriptors: {json.dumps(writable, sort_keys=True)}")

    system_parent = root / FINAL_REL / system
    system_parent.mkdir(parents=True, mode=0o755, exist_ok=True)
    if system_parent.resolve(strict=True) != system_parent.absolute() or device(system_parent) != EXPECTED_DEVICE:
        fail("immutable replay base parent path/device mismatch")
    partial = Path(f"{final}.partial.{os.getpid()}")
    if partial.exists():
        fail(f"current process partial already exists: {partial}")
    partial.mkdir(mode=0o700)
    base = partial / "index"
    block_before = block_snapshot(EXPECTED_DEVICE)
    proc_before = proc_io_snapshot()
    started = time.monotonic()
    published = False
    try:
        copy_tree(source, base)
        copy_wall = time.monotonic() - started
        proc_after = proc_io_snapshot()
        block_after = block_snapshot(EXPECTED_DEVICE)
        if content_bytes(base) != accepted:
            fail("copied replay base content differs from accepted R07 lineage")
        inode_count = assert_inode_independent(source, base)
        if injection == "after_copy":
            fail("fixture failure injection after_copy")
        normalize_immutable(base)
        if content_bytes(base) != accepted:
            fail("immutable normalization changed replay base content")
        policy = assert_immutable_policy(base)
        base_content = content_bytes(base)
        base_mode = mode_bytes(base)
        # The denial child must be able to traverse the unpublished cp00 root.
        # Root can still create the evidence files below after this transition.
        os.chown(partial, 0, 0, follow_symlinks=False)
        os.chmod(partial, 0o555, follow_symlinks=False)
        denial = run_denial_audit(Path(__file__).resolve(), base)
        source_content_after = content_bytes(source)
        source_mode_after = mode_bytes(source)
        if source_content_after != source_content_before or source_mode_after != source_mode_before:
            fail("source content/mode changed during immutable replay-base creation")
        if open_writable_source_fds(source):
            fail("source acquired a live writable descriptor during creation")

        payloads = {
            "base_content.tsv": base_content,
            "base_mode.tsv": base_mode,
            "source_content_before.tsv": source_content_before,
            "source_content_after.tsv": source_content_after,
            "source_mode_before.tsv": source_mode_before,
            "source_mode_after.tsv": source_mode_after,
            "write_denial_audit.json": (json.dumps(denial, indent=2, sort_keys=True) + "\n").encode(),
        }
        for name, payload in payloads.items():
            write_new(partial / name, payload)
        space = tree_space(base)
        base_content_identity = identity_as(partial / "base_content.tsv", final / "base_content.tsv")
        base_mode_identity = identity_as(partial / "base_mode.tsv", final / "base_mode.tsv")
        manifest = {
            "schema": SCHEMA, "status": "pass", "system": system,
            "accepted_r07": accepted_evidence,
            "immutable_base_realpath": str(final / "index"),
            "content_manifest_sha256": base_content_identity["sha256"],
            "mode_manifest_sha256": base_mode_identity["sha256"],
            "source": {
                "realpath": str(source), "device": device(source),
                "content_before": identity_as(partial / "source_content_before.tsv", final / "source_content_before.tsv"),
                "content_after": identity_as(partial / "source_content_after.tsv", final / "source_content_after.tsv"),
                "mode_before": identity_as(partial / "source_mode_before.tsv", final / "source_mode_before.tsv"),
                "mode_after": identity_as(partial / "source_mode_after.tsv", final / "source_mode_after.tsv"),
                "open_writable_fd_count": 0, "special_object_count": 0, "regular_hardlink_count": 0,
            },
            "immutable_base": {
                "realpath": str(final / "index"), "device": device(base),
                "content": base_content_identity, "mode": base_mode_identity,
                "content_manifest": base_content_identity, "mode_manifest": base_mode_identity,
                "owner_uid": 0, "owner_gid": 0, "directory_mode": "0555", "file_mode": "0444",
                **space, "inode_independent": True, "inode_pairs_checked": inode_count,
            },
            "copy": {
                "method": "buffered_byte_copy_no_reflink_no_hardlink", "wall_seconds": copy_wall,
                "target_device": EXPECTED_DEVICE, "target_device_io_before": block_before,
                "target_device_io_after": block_after, "target_device_io_delta": block_delta(block_before, block_after),
                "process_io_before": proc_before, "process_io_after": proc_after,
                "process_io_delta": {key: proc_after[key] - proc_before[key] for key in proc_before},
            },
            "write_denial": identity_as(partial / "write_denial_audit.json", final / "write_denial_audit.json"),
            "write_denial_counts": denial,
            "atomic_publish": True,
        }
        write_new(partial / "immutable_replay_base_manifest.json",
                  (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
        write_new(partial / "IMMUTABLE_REPLAY_BASE_OK", (SCHEMA + "\n").encode())
        for name in EVIDENCE_NAMES:
            os.chown(partial / name, 0, 0, follow_symlinks=False)
            os.chmod(partial / name, 0o444, follow_symlinks=False)
        fsync_tree(partial)
        fsync_dir(partial)
        if injection == "before_publish":
            fail("fixture failure injection before_publish")
        os.chown(partial, 0, 0, follow_symlinks=False)
        os.chmod(partial, 0o555, follow_symlinks=False)
        if final.exists():
            fail("immutable replay base appeared concurrently; overwrite refused")
        os.rename(partial, final)
        published = True
        fsync_dir(system_parent)
    finally:
        if not published and partial.exists():
            remove_partial(partial)
    verified = verify_final(root, system)
    verified["action"] = "created_and_verified"
    return verified


def audit_source(root: Path, system: str) -> dict[str, Any]:
    """Read-only production lineage audit; it never creates a target parent."""
    if os.geteuid() != 0:
        fail("replay-base source audit requires root")
    root = root.resolve(strict=True)
    if device(root) != EXPECTED_DEVICE:
        fail(f"atlas root is not on expected project NVMe {EXPECTED_DEVICE}")
    source = check_source(root, system)
    accepted, accepted_evidence = validate_lineage(root, system, source)
    current_content = content_bytes(source)
    current_mode = mode_bytes(source)
    if current_content != accepted:
        fail("current source content does not equal accepted R07 lineage")
    writable = open_writable_source_fds(source)
    if writable:
        fail(f"source has live writable file descriptors: {json.dumps(writable, sort_keys=True)}")
    final = root / FINAL_REL / system / "cp00"
    return {
        "schema": "dynamic-vamana-w1-immutable-replay-base-source-audit-v1",
        "status": "pass", "action": "read_only_source_audit", "system": system,
        "source_realpath": str(source), "source_device": device(source),
        "accepted_r07": accepted_evidence,
        "content_manifest_sha256": sha256_bytes(current_content),
        "mode_manifest_sha256": sha256_bytes(current_mode),
        "source_space": tree_space(source), "open_writable_fd_count": 0,
        "formal_target_absent": not final.exists(),
    }


def snapshot_tree(root: Path) -> list[tuple[str, int, int, int, int, int, int, str]]:
    rows = []
    for path, relative, info in safe_walk(root):
        digest = sha256_file(path) if stat.S_ISREG(info.st_mode) else ""
        rows.append((relative, info.st_dev, info.st_ino, info.st_uid, info.st_gid,
                     stat.S_IMODE(info.st_mode), info.st_nlink, digest))
    return rows


def fixture_lineage(root: Path, system: str) -> Path:
    source = root / SOURCE_REL[system]
    source.mkdir(parents=True)
    (source / "BUILD_OK").write_bytes(b"")
    (source / "index.bin").write_bytes(b"fixture-index\x00" * 1024)
    os.chmod(source, 0o775)
    for path in source.iterdir():
        os.chmod(path, 0o664)
    payload = content_bytes(source)
    paths = lineage_paths(root, system)
    for name in ("base_before", "base_after", "base_after_attempt"):
        paths[name].parent.mkdir(parents=True, exist_ok=True)
        paths[name].write_bytes(payload)
    clone = {"schema": "dynamic-vamana-w1-clone-v2", "system": system,
             "clone_mode": "copy_or_filesystem_reflink_auto", "base": str(source.resolve())}
    paths["clone_manifest"].write_text(json.dumps(clone) + "\n")
    paths["system_marker"].touch()
    paths["global_marker"].parent.mkdir(parents=True, exist_ok=True)
    paths["global_marker"].touch()
    return source


def make_fixture_root(scratch: Path, name: str) -> Path:
    root = scratch / name
    root.mkdir(parents=True)
    return root


def self_test(scratch: Path, output: Path) -> dict[str, Any]:
    if os.geteuid() != 0:
        fail("replay-base recovery self-test requires root")
    scratch = scratch.absolute()
    if scratch.exists() or output.exists():
        fail("self-test scratch/output freshness guard failed")
    scratch.parent.mkdir(parents=True, exist_ok=True)
    if device(scratch.parent) != EXPECTED_DEVICE:
        fail("self-test scratch must be on project NVMe 259:10")
    scratch.mkdir(mode=0o755)
    tests: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: str = "") -> None:
        tests.append({"name": name, "passed": passed, "detail": detail})

    try:
        root = make_fixture_root(scratch, "happy")
        source = fixture_lineage(root, "DGAI")
        before = snapshot_tree(source)
        created = ensure(root, "DGAI")
        after_create = snapshot_tree(source)
        final = root / FINAL_REL / "DGAI/cp00"
        final_before = snapshot_tree(final)
        verified = ensure(root, "DGAI")
        final_after = snapshot_tree(final)
        record("create_and_idempotent_read_only_verify",
               created["action"] == "created_and_verified" and verified["action"] == "verified_read_only"
               and before == after_create and final_before == final_after)

        for case in ("history_after_mismatch", "current_source_mismatch", "symlink", "fifo", "hardlink"):
            case_root = make_fixture_root(scratch, case)
            case_source = fixture_lineage(case_root, "DGAI")
            if case == "history_after_mismatch":
                lineage_paths(case_root, "DGAI")["base_after"].write_text("bad\n")
            elif case == "current_source_mismatch":
                (case_source / "index.bin").write_bytes(b"changed")
            elif case == "symlink":
                (case_source / "bad-link").symlink_to(case_source / "index.bin")
            elif case == "fifo":
                os.mkfifo(case_source / "bad-fifo")
            else:
                os.link(case_source / "index.bin", case_source / "bad-hardlink")
            rejected = False
            try:
                ensure(case_root, "DGAI")
            except RuntimeError:
                rejected = True
            record("reject_" + case, rejected and not (case_root / FINAL_REL / "DGAI/cp00").exists())

        fd_root = make_fixture_root(scratch, "writable_fd")
        fd_source = fixture_lineage(fd_root, "DGAI")
        fd = os.open(fd_source / "index.bin", os.O_RDWR | os.O_CLOEXEC)
        try:
            rejected = False
            try:
                ensure(fd_root, "DGAI")
            except RuntimeError as exc:
                rejected = "writable file descriptors" in str(exc)
        finally:
            os.close(fd)
        record("reject_live_writable_source_fd", rejected and not (fd_root / FINAL_REL / "DGAI/cp00").exists())

        for injection in ("after_copy", "before_publish"):
            inj_root = make_fixture_root(scratch, injection)
            inj_source = fixture_lineage(inj_root, "DGAI")
            inj_before = snapshot_tree(inj_source)
            rejected = False
            try:
                ensure(inj_root, "DGAI", injection=injection)
            except RuntimeError:
                rejected = True
            parent = inj_root / FINAL_REL / "DGAI"
            partials = list(parent.glob("cp00.partial.*")) if parent.exists() else []
            record("atomic_failure_" + injection, rejected and not (parent / "cp00").exists()
                   and not partials and snapshot_tree(inj_source) == inj_before)

        tamper_root = make_fixture_root(scratch, "tamper")
        fixture_lineage(tamper_root, "DGAI")
        ensure(tamper_root, "DGAI")
        tamper = tamper_root / FINAL_REL / "DGAI/cp00/index/index.bin"
        os.chmod(tamper, 0o644)
        rejected = False
        try:
            verify_final(tamper_root, "DGAI")
        except RuntimeError:
            rejected = True
        record("read_only_verify_rejects_mode_tamper", rejected)

        report = {"schema": "dynamic-vamana-w1-immutable-replay-base-self-test-v1",
                  "status": "pass" if all(row["passed"] for row in tests) else "fail",
                  "test_count": len(tests), "tests": tests,
                  "formal_target_touched": False}
    finally:
        if scratch.exists():
            remove_fixture(scratch)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if report["status"] != "pass":
        fail("immutable replay-base self-test failed")
    return report


def remove_fixture(path: Path) -> None:
    for directory, dirs, files in os.walk(path, topdown=False, followlinks=False):
        base = Path(directory)
        try:
            os.chmod(base, 0o700, follow_symlinks=False)
        except FileNotFoundError:
            continue
        for name in files:
            item = base / name
            if item.is_symlink():
                item.unlink()
            else:
                os.chmod(item, 0o600, follow_symlinks=False)
                item.unlink()
        for name in dirs:
            item = base / name
            if item.is_symlink():
                item.unlink()
            else:
                os.chmod(item, 0o700, follow_symlinks=False)
                item.rmdir()
    path.rmdir()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("ensure", "verify", "audit-source"):
        item = sub.add_parser(command)
        item.add_argument("--root", type=Path, required=True)
        item.add_argument("--system", choices=SYSTEMS, required=True)
    child = sub.add_parser("denial-child")
    child.add_argument("--root", type=Path, required=True)
    test = sub.add_parser("self-test")
    test.add_argument("--scratch", type=Path, required=True)
    test.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        if args.command == "denial-child":
            report = denial_child(args.root.resolve(strict=True))
        elif args.command == "self-test":
            report = self_test(args.scratch, args.output)
        else:
            root = args.root.resolve(strict=True)
            if args.command == "ensure":
                report = ensure(root, args.system)
            elif args.command == "verify":
                report = verify_final(root, args.system)
            else:
                report = audit_source(root, args.system)
        print(json.dumps(report, sort_keys=True))
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"w1_replay_base_recovery: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
