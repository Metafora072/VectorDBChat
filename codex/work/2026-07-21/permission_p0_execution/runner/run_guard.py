#!/usr/bin/env python3
"""Run one P0 stage with wall/RSS/space/path guards.

This is an execution guard, not a benchmark. It writes only below --run-root.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


GIB = 1024 ** 3
DATA_PREFIX = "/home/ubuntu/pz/VectorDB/data/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--soft-wall", type=int, default=13_500)
    parser.add_argument("--hard-wall", type=int, default=14_400)
    parser.add_argument("--soft-rss-gib", type=float, default=20.0)
    parser.add_argument("--hard-rss-gib", type=float, default=24.0)
    parser.add_argument("--soft-data-gib", type=float, default=8.5)
    parser.add_argument("--hard-data-gib", type=float, default=10.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("missing command after --")
    return args


def proc_table() -> dict[int, int]:
    table: dict[int, int] = {}
    for item in Path("/proc").iterdir():
        if not item.name.isdigit():
            continue
        try:
            fields = (item / "stat").read_text().split()
            table[int(item.name)] = int(fields[3])
        except (OSError, ValueError, IndexError):
            continue
    return table


def descendants(root: int) -> set[int]:
    table = proc_table()
    result = {root}
    changed = True
    while changed:
        changed = False
        for pid, ppid in table.items():
            if pid not in result and ppid in result:
                result.add(pid)
                changed = True
    return result


def rss_bytes(pids: set[int]) -> int:
    total = 0
    for pid in pids:
        try:
            for line in Path(f"/proc/{pid}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    total += int(line.split()[1]) * 1024
                    break
        except (OSError, ValueError):
            continue
    return total


def writable_paths(pids: set[int]) -> list[str]:
    bad: set[str] = set()
    for pid in pids:
        fd_root = Path(f"/proc/{pid}/fd")
        try:
            fds = list(fd_root.iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                info = Path(f"/proc/{pid}/fdinfo/{fd.name}").read_text()
                flags_line = next(x for x in info.splitlines() if x.startswith("flags:"))
                flags = int(flags_line.split()[1], 8)
                if (flags & os.O_ACCMODE) == os.O_RDONLY:
                    continue
                target = os.readlink(fd)
            except (OSError, StopIteration, ValueError):
                continue
            if target.startswith(("pipe:[", "socket:[", "anon_inode:", "/dev/null", DATA_PREFIX)):
                continue
            bad.add(target)
    return sorted(bad)


def disk_bytes(path: Path) -> int:
    proc = subprocess.run(
        ["du", "-sb", str(path)], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, check=False,
    )
    if proc.returncode != 0:
        return -1
    return int(proc.stdout.split()[0])


def terminate_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    time.sleep(3)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def atomic_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def main() -> int:
    args = parse_args()
    root = Path(args.run_root).resolve()
    if not str(root).startswith(DATA_PREFIX):
        raise SystemExit(f"run root is not on data disk: {root}")
    logs = root / "logs"
    state_dir = root / "state"
    tmpdir = root / "tmp"
    home = root / "home"
    cache = root / "cache"
    for directory in (logs, state_dir, tmpdir, home, cache):
        directory.mkdir(parents=True, exist_ok=True)

    epoch_file = state_dir / "run_started_epoch"
    if epoch_file.exists():
        run_started = float(epoch_file.read_text().strip())
    else:
        run_started = time.time()
        epoch_file.write_text(f"{run_started:.6f}\n")

    elapsed_before = time.time() - run_started
    if elapsed_before >= args.soft_wall:
        atomic_json(state_dir / f"{args.stage}.json", {
            "stage": args.stage, "status": "NOT_STARTED_SOFT_WALL",
            "elapsed_seconds": elapsed_before,
        })
        return 75

    env = os.environ.copy()
    env.update({
        "TMPDIR": str(tmpdir),
        "TMP": str(tmpdir),
        "TEMP": str(tmpdir),
        "HOME": str(home),
        "XDG_CACHE_HOME": str(cache),
        "PYTHONPYCACHEPREFIX": str(cache / "pycache"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    log_path = logs / f"{args.stage}.log"
    started = time.time()
    peak_rss = 0
    peak_data = 0
    reason = "process_exit"
    with log_path.open("ab", buffering=0) as log:
        proc = subprocess.Popen(
            args.command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        while proc.poll() is None:
            pids = descendants(proc.pid)
            rss = rss_bytes(pids)
            used = disk_bytes(root)
            peak_rss = max(peak_rss, rss)
            peak_data = max(peak_data, used)
            elapsed = time.time() - run_started
            bad_paths = writable_paths(pids)
            hard_reason = None
            if bad_paths:
                hard_reason = "writable_path_outside_data_disk:" + ",".join(bad_paths[:8])
            elif elapsed >= args.hard_wall:
                hard_reason = "hard_wall"
            elif rss >= args.hard_rss_gib * GIB:
                hard_reason = "hard_rss"
            elif used >= args.hard_data_gib * GIB:
                hard_reason = "hard_data"
            if hard_reason:
                reason = hard_reason
                terminate_group(proc.pid)
                break
            time.sleep(2)
        rc = proc.wait()

    total_elapsed = time.time() - run_started
    soft_crossed = (
        total_elapsed >= args.soft_wall
        or peak_rss >= args.soft_rss_gib * GIB
        or peak_data >= args.soft_data_gib * GIB
    )
    payload = {
        "command": args.command,
        "exit_code": rc,
        "finished_epoch": time.time(),
        "log": str(log_path),
        "peak_data_bytes": peak_data,
        "peak_rss_bytes": peak_rss,
        "reason": reason,
        "run_elapsed_seconds": total_elapsed,
        "soft_line_crossed": soft_crossed,
        "stage": args.stage,
        "stage_elapsed_seconds": time.time() - started,
        "status": "PASS" if rc == 0 and reason == "process_exit" else "FAIL",
    }
    atomic_json(state_dir / f"{args.stage}.json", payload)
    if soft_crossed:
        (state_dir / "STOP_BEFORE_NEXT_STAGE").write_text(json.dumps(payload, indent=2) + "\n")
    return rc if rc != 0 else (76 if reason != "process_exit" else 0)


if __name__ == "__main__":
    sys.exit(main())
