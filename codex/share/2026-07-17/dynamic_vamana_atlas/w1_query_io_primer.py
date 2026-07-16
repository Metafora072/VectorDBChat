#!/usr/bin/env python3
"""Prime cgroup device accounting, then exec the frozen query resource probe."""
from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
from pathlib import Path


SCHEMA = "dynamic-vamana-w1-query-io-primer-v1"


def fail(message: str) -> None:
    raise RuntimeError(message)


def snapshot(path: Path) -> dict[str, int | str]:
    info = path.lstat()
    return {
        "realpath": str(path), "device_major_minor": f"{os.major(info.st_dev)}:{os.minor(info.st_dev)}",
        "inode": info.st_ino, "size_bytes": info.st_size, "uid": info.st_uid, "gid": info.st_gid,
        "mode_octal": f"{stat.S_IMODE(info.st_mode):04o}", "link_count": info.st_nlink,
        "mtime_ns": info.st_mtime_ns,
    }


def write_new(path: Path, value: dict[str, object]) -> None:
    if path.exists() or path.is_symlink():
        fail(f"primer report reuse refused: {path}")
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-root", type=Path, required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--primer-report", type=Path, required=True)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--resource-probe", type=Path, required=True)
    parser.add_argument("--query-worker", type=Path, required=True)
    parser.add_argument("--system", choices=("DGAI", "OdinANN"), required=True)
    parser.add_argument("--query-binary", type=Path, required=True)
    parser.add_argument("--query", type=Path, required=True)
    parser.add_argument("--gt", type=Path, required=True)
    parser.add_argument("--result-ids", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--l-value", type=int, required=True)
    parser.add_argument("--active-tags", type=Path, required=True)
    args = parser.parse_args()

    index_root = args.index_root.resolve(strict=True)
    if index_root != args.index_root.absolute() or index_root.is_symlink():
        fail("index root is not an exact canonical path")
    prime = index_root / "index_disk.index"
    if prime.resolve(strict=True) != prime.absolute() or prime.is_symlink():
        fail("primer target is not exact index_root/index_disk.index")
    info = prime.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size < 4096:
        fail("primer target regular-file/size/link policy mismatch")
    mode = stat.S_IMODE(info.st_mode)
    immutable = (info.st_uid, info.st_gid, mode) == (0, 0, 0o444)
    mutable = (info.st_uid, info.st_gid, mode) == (os.geteuid(), os.getegid(), 0o600)
    if not (immutable or mutable):
        fail(f"primer target owner/mode policy mismatch: {info.st_uid}:{info.st_gid} {mode:04o}")
    before = snapshot(prime)
    if before["device_major_minor"] != args.device or not os.access(prime, os.R_OK):
        fail("primer target device/read capability mismatch")
    for path in (args.resource_probe, args.query_worker, args.query_binary, args.query,
                 args.gt, args.active_tags):
        if not path.resolve(strict=True).is_file():
            fail(f"query capability input is not a file: {path}")
    for output in (args.primer_report, args.resources, args.result_ids, args.log):
        if output.exists() or output.is_symlink():
            fail(f"query output reuse refused: {output}")
        if output.parent.resolve(strict=True) != args.primer_report.parent.resolve(strict=True):
            fail("query outputs do not share the exact stem parent")

    completed = subprocess.run([
        "dd", f"if={prime}", "of=/dev/null", "iflag=direct", "bs=4096", "count=1", "status=none"
    ], check=False)
    after = snapshot(prime)
    if completed.returncode != 0 or after != before:
        fail("O_DIRECT primer failed or changed file identity")
    write_new(args.primer_report, {
        "schema": SCHEMA, "status": "pass", "accounting_role": "accounting infrastructure",
        "index_root_realpath": str(index_root), "prime_file": before, "prime_file_after": after,
        "bytes_requested": 4096, "bytes_read": 4096, "return_code": completed.returncode,
        "direct_io": True, "resource_probe_started_after_primer": True,
        "primer_excluded_from_query_delta": True,
    })

    command = [
        "python3", str(args.resource_probe.resolve(strict=True)), "--output", str(args.resources),
        "--interval-ms", "25", "--space-root", str(index_root), "--",
        str(args.query_worker.resolve(strict=True)), args.system,
        str(args.query_binary.resolve(strict=True)), str(index_root / "index"),
        str(args.query.resolve(strict=True)), str(args.gt.resolve(strict=True)),
        str(args.result_ids), str(args.log), str(args.l_value), str(args.active_tags.resolve(strict=True)),
    ]
    os.execvp(command[0], command)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"w1_query_io_primer: {exc}") from exc
