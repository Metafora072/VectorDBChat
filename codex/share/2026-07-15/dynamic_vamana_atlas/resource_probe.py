#!/usr/bin/env python3
"""Prototype process-tree, smaps, cgroup, and page-cache resource sampler."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path


def read_kv(path: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        for line in path.read_text().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
            else:
                fields = line.split(maxsplit=1)
                if len(fields) != 2:
                    continue
                key, value = fields
            if not key.isidentifier():
                continue
            fields = value.strip().split()
            if not fields:
                continue
            token = fields[0]
            if token.isdigit():
                out[key] = int(token)
    except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
        pass
    return out


def children_of(pid: int) -> list[int]:
    children = Path(f"/proc/{pid}/task/{pid}/children")
    try:
        return [int(value) for value in children.read_text().split()]
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return []


def process_tree(root: int) -> list[int]:
    seen: set[int] = set()
    pending = [root]
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        pending.extend(children_of(pid))
    return sorted(seen)


def cgroup_path(pid: int) -> Path | None:
    try:
        for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines():
            hierarchy, controllers, rel = line.split(":", 2)
            if hierarchy == "0" and controllers == "":
                return Path("/sys/fs/cgroup") / rel.lstrip("/")
    except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
        return None
    return None


def read_int(path: Path) -> int | None:
    try:
        value = path.read_text().strip()
        return int(value) if value != "max" else None
    except (FileNotFoundError, PermissionError, ValueError):
        return None


def read_proc_io(path: Path) -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        for line in path.read_text().splitlines():
            key, value = line.split(":", 1)
            value = value.strip()
            if value.isdigit():
                values[key] = int(value)
    except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
        pass
    return values


def read_cgroup_io(path: Path) -> list[dict[str, int | str]]:
    rows: list[dict[str, int | str]] = []
    try:
        for line in path.read_text().splitlines():
            fields = line.split()
            if not fields:
                continue
            row: dict[str, int | str] = {"device": fields[0]}
            for field in fields[1:]:
                key, value = field.split("=", 1)
                if value.isdigit():
                    row[key] = int(value)
            rows.append(row)
    except (FileNotFoundError, PermissionError, ValueError):
        pass
    return rows


def directory_space(root: Path | None) -> dict[str, int] | None:
    if root is None:
        return None
    apparent = 0
    allocated = 0
    files = 0
    try:
        for current, _, names in os.walk(root):
            for name in names:
                try:
                    stat = (Path(current) / name).stat()
                except FileNotFoundError:
                    continue
                apparent += stat.st_size
                allocated += stat.st_blocks * 512
                files += 1
    except FileNotFoundError:
        pass
    return {"files": files, "apparent_bytes": apparent, "allocated_bytes": allocated}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--interval-ms", type=int, default=50)
    p.add_argument("--space-root", type=Path)
    p.add_argument("command", nargs=argparse.REMAINDER)
    args = p.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise SystemExit("missing command")

    meminfo_before = read_kv(Path("/proc/meminfo"))
    start = time.monotonic()
    proc = subprocess.Popen(command)
    cg = cgroup_path(proc.pid)
    samples = []
    peak_tree_rss_kb = 0
    peak_tree_io_bytes = {"read_bytes": 0, "write_bytes": 0}
    peak_smaps: dict[str, int] = {}
    while proc.poll() is None:
        pids = process_tree(proc.pid)
        tree_rss_kb = 0
        tree_io_bytes = {"read_bytes": 0, "write_bytes": 0}
        aggregate: dict[str, int] = {}
        for pid in pids:
            status = read_kv(Path(f"/proc/{pid}/status"))
            tree_rss_kb += status.get("VmRSS", 0)
            proc_io = read_proc_io(Path(f"/proc/{pid}/io"))
            for key in tree_io_bytes:
                tree_io_bytes[key] += proc_io.get(key, 0)
            smaps = read_kv(Path(f"/proc/{pid}/smaps_rollup"))
            for key, value in smaps.items():
                aggregate[key] = aggregate.get(key, 0) + value
        peak_tree_rss_kb = max(peak_tree_rss_kb, tree_rss_kb)
        for key, value in tree_io_bytes.items():
            peak_tree_io_bytes[key] = max(peak_tree_io_bytes[key], value)
        for key, value in aggregate.items():
            peak_smaps[key] = max(peak_smaps.get(key, 0), value)
        samples.append(
            {
                "monotonic_ns": time.monotonic_ns(),
                "elapsed_ms": round((time.monotonic() - start) * 1000, 3),
                "process_count": len(pids),
                "tree_rss_kb": tree_rss_kb,
                "process_tree_io_bytes": tree_io_bytes,
                "smaps_rollup_kb": aggregate,
                "cgroup_memory_current": read_int(cg / "memory.current") if cg else None,
                "cgroup_memory_peak": read_int(cg / "memory.peak") if cg else None,
                "cgroup_memory_events": read_kv(cg / "memory.events") if cg else {},
                "cgroup_io_stat": read_cgroup_io(cg / "io.stat") if cg else [],
                "index_space": directory_space(args.space_root),
            }
        )
        time.sleep(args.interval_ms / 1000)
    returncode = proc.wait()
    # Keep a post-command cgroup sample.  Phase collectors need the first
    # sample after a terminal marker instead of a nearest pre-exit sample.
    samples.append(
        {
            "monotonic_ns": time.monotonic_ns(),
            "elapsed_ms": round((time.monotonic() - start) * 1000, 3),
            "process_count": 0,
            "tree_rss_kb": 0,
            "process_tree_io_bytes": {},
            "smaps_rollup_kb": {},
            "cgroup_memory_current": read_int(cg / "memory.current") if cg else None,
            "cgroup_memory_peak": read_int(cg / "memory.peak") if cg else None,
            "cgroup_memory_events": read_kv(cg / "memory.events") if cg else {},
            "cgroup_io_stat": read_cgroup_io(cg / "io.stat") if cg else [],
            "index_space": directory_space(args.space_root),
        }
    )
    meminfo_after = read_kv(Path("/proc/meminfo"))
    report = {
        "schema": "dynamic-vamana-atlas-resource-probe-v1",
        "sampling_interval_ms": args.interval_ms,
        "command": command,
        "returncode": returncode,
        "elapsed_seconds": time.monotonic() - start,
        "root_pid": proc.pid,
        "cgroup_path": str(cg) if cg else None,
        "cgroup_scope_note": "Values are process-specific only if the launcher has a dedicated cgroup.",
        "cgroup_memory_events_final": read_kv(cg / "memory.events") if cg else {},
        "peak_process_tree_rss_kb": peak_tree_rss_kb,
        "peak_process_tree_io_bytes": peak_tree_io_bytes,
        "peak_smaps_rollup_kb": peak_smaps,
        "page_cache_before_kb": meminfo_before.get("Cached"),
        "page_cache_after_kb": meminfo_after.get("Cached"),
        "space_root": str(args.space_root) if args.space_root else None,
        "samples": samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(returncode)


if __name__ == "__main__":
    main()
