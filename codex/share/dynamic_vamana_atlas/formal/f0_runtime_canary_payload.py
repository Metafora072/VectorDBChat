#!/usr/bin/env python3
"""Small cgroup/NUMA payload run inside the F0 transient scope."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path


def read_memory_events() -> dict[str, int]:
    events: dict[str, int] = {}
    for line in Path("/sys/fs/cgroup/memory.events").read_text().splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].isdigit():
            events[fields[0]] = int(fields[1])
    return events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--nvme-file", type=Path, required=True)
    parser.add_argument("--hold-seconds", type=float, default=3.0)
    args = parser.parse_args()
    args.nvme_file.parent.mkdir(parents=True, exist_ok=True)
    # Touch memory pages and issue NVMe write/read without becoming a workload.
    memory = bytearray(16 * 1024 * 1024)
    for index in range(0, len(memory), 4096):
        memory[index] = index // 4096 % 251
    with args.nvme_file.open("wb") as handle:
        handle.write(memory[:1024 * 1024])
        handle.flush()
        os.fsync(handle.fileno())
    _ = args.nvme_file.read_bytes()
    numa_show = subprocess.check_output(["numactl", "--show"], text=True, stderr=subprocess.STDOUT)
    payload = {
        "schema": "dynamic-vamana-f0-runtime-canary-payload-v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "uid": os.geteuid(),
        "gid": os.getegid(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "numactl_show": numa_show,
        "cgroup": Path("/proc/self/cgroup").read_text(),
        "memory_events": read_memory_events(),
        "nvme_file": str(args.nvme_file),
        "nvme_file_uid": args.nvme_file.stat().st_uid,
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    time.sleep(args.hold_seconds)


if __name__ == "__main__":
    main()
