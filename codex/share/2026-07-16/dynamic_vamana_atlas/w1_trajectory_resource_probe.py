#!/usr/bin/env python3
"""Fail-closed per-scope resource probe for W1 trajectory preparation."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import time
from pathlib import Path


def cgroup_path(pid: int) -> Path:
    for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines():
        hierarchy, controllers, relative = line.split(":", 2)
        if hierarchy == "0" and controllers == "":
            return Path("/sys/fs/cgroup") / relative.lstrip("/")
    raise RuntimeError("unified cgroup path unavailable")


def read_int(path: Path) -> int | None:
    try:
        value = path.read_text().strip()
        return None if value == "max" else int(value)
    except (FileNotFoundError, PermissionError, ValueError):
        return None


def read_kv(path: Path) -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        for line in path.read_text().splitlines():
            fields = line.replace(":", " ", 1).split()
            if len(fields) >= 2 and fields[1].isdigit():
                values[fields[0]] = int(fields[1])
    except (FileNotFoundError, PermissionError, ValueError):
        pass
    return values


def read_io(path: Path, required_device: str) -> tuple[list[dict[str, int | str]], bool]:
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
    present = any(row["device"] == required_device for row in rows)
    if not present:
        rows.append({"device": required_device, "rbytes": 0, "wbytes": 0, "rios": 0, "wios": 0})
    return rows, present


def directory_space(root: Path) -> dict[str, int]:
    apparent = allocated = files = 0
    for current, _, names in os.walk(root):
        for name in names:
            try:
                st = (Path(current) / name).stat()
            except FileNotFoundError:
                continue
            files += 1
            apparent += st.st_size
            allocated += st.st_blocks * 512
    return {"files": files, "apparent_bytes": apparent, "allocated_bytes": allocated}


def children(pid: int) -> list[int]:
    try:
        return [int(value) for value in Path(f"/proc/{pid}/task/{pid}/children").read_text().split()]
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        return []


def process_tree(root: int) -> list[int]:
    pending, seen = [root], set()
    while pending:
        pid = pending.pop()
        if pid not in seen:
            seen.add(pid)
            pending.extend(children(pid))
    return sorted(seen)


def rss_kb(pids: list[int]) -> int:
    total = 0
    for pid in pids:
        try:
            for line in Path(f"/proc/{pid}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    total += int(line.split()[1])
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError):
            pass
    return total


def sample(cgroup: Path, device: str, start: float, root: Path, pid: int | None) -> dict:
    pids = process_tree(pid) if pid is not None else []
    io_rows, device_present = read_io(cgroup / "io.stat", device)
    return {
        "monotonic_ns": time.monotonic_ns(),
        "elapsed_ms": round((time.monotonic() - start) * 1000, 3),
        "process_count": len(pids),
        "tree_rss_kb": rss_kb(pids),
        "cgroup_memory_current": read_int(cgroup / "memory.current"),
        "cgroup_memory_peak": read_int(cgroup / "memory.peak"),
        "cgroup_memory_events": read_kv(cgroup / "memory.events"),
        "cgroup_io_stat": io_rows,
        "target_device_present_raw": device_present,
        "index_space": directory_space(root),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval-ms", type=int, default=100)
    parser.add_argument("--space-root", type=Path, required=True)
    parser.add_argument("--io-device", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or args.output.exists():
        raise SystemExit("resource probe command missing or output reuse attempted")
    root = args.space_root.resolve()
    scope = cgroup_path(os.getpid()).resolve()
    start = time.monotonic()
    baseline = sample(scope, args.io_device, start, root, None)
    proc = subprocess.Popen(command)
    samples = [baseline]
    peak_rss_kb = 0
    interval = args.interval_ms / 1000
    while proc.poll() is None:
        row = sample(scope, args.io_device, start, root, proc.pid)
        samples.append(row)
        peak_rss_kb = max(peak_rss_kb, int(row["tree_rss_kb"]))
        time.sleep(interval)
    returncode = proc.wait()
    samples.append(sample(scope, args.io_device, start, root, None))
    gaps = [(b["monotonic_ns"] - a["monotonic_ns"]) / 1_000_000 for a, b in zip(samples, samples[1:])]
    report = {
        "schema": "dynamic-vamana-w1-trajectory-resource-probe-v1",
        "command": command,
        "returncode": returncode,
        "elapsed_seconds": time.monotonic() - start,
        "root_pid": proc.pid,
        "probe_pid": os.getpid(),
        "cgroup_path": str(scope),
        "io_device": args.io_device,
        "space_root": str(root),
        "space_before": baseline["index_space"],
        "space_final": samples[-1]["index_space"],
        "cgroup_io_baseline": baseline["cgroup_io_stat"],
        "cgroup_io_final": samples[-1]["cgroup_io_stat"],
        "target_device_present_raw_baseline": baseline["target_device_present_raw"],
        "target_device_present_raw_final": samples[-1]["target_device_present_raw"],
        "cgroup_memory_events_final": read_kv(scope / "memory.events"),
        "cgroup_memory_peak_final": read_int(scope / "memory.peak"),
        "peak_process_tree_rss_kb": peak_rss_kb,
        "sampling_interval_ms": args.interval_ms,
        "observed_sampling_period_ms": {"median": statistics.median(gaps), "maximum": max(gaps)},
        "samples": samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(returncode)


if __name__ == "__main__":
    main()
