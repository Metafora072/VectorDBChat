#!/usr/bin/env python3
"""Timestamp native query-driver phase markers without modifying artifact code."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path


MARKERS = {
    "DiskANN": {"load": "Loading the cache list into memory....done.", "warmup_start": "Warming up index...", "warmup_end": "..done"},
    "DGAI": {"load": "INDEX LOADED", "warmup_start": "Use two ANNS for warming up...", "warmup_end": "Warming up finished."},
    "OdinANN": {"load": "SSDIndex loaded successfully.", "warmup_start": None, "warmup_end": None},
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--system", choices=MARKERS, required=True)
    p.add_argument("--query-count", type=int, required=True)
    p.add_argument("--log", type=Path, required=True)
    p.add_argument("--timing", type=Path, required=True)
    p.add_argument("command", nargs=argparse.REMAINDER)
    args = p.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise SystemExit("missing command")
    markers = MARKERS[args.system]
    args.log.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    seen: dict[str, float] = {}
    qps = None
    metric_seen = False
    with args.log.open("w") as log:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        assert proc.stdout is not None
        for line in proc.stdout:
            now = time.monotonic() - start
            log.write(line)
            print(line, end="", flush=True)
            if markers["load"] and markers["load"] in line and "load" not in seen:
                seen["load"] = now
            if markers["warmup_start"] and markers["warmup_start"] in line and "warmup_start" not in seen:
                seen["warmup_start"] = now
            if (markers["warmup_end"] and markers["warmup_end"] in line and "warmup_start" in seen
                    and "warmup_end" not in seen):
                seen["warmup_end"] = now
            if "Recall@10" in line:
                metric_seen = True
                continue
            if metric_seen and qps is None:
                fields = line.split()
                if fields and fields[0].isdigit() and len(fields) >= 3:
                    try:
                        qps = float(fields[2])
                        seen["metric"] = now
                    except ValueError:
                        pass
        code = proc.wait()
    wall = time.monotonic() - start
    load = seen.get("load")
    warmup_start, warmup_end = seen.get("warmup_start"), seen.get("warmup_end")
    timed_start = warmup_end if warmup_end is not None else load
    envelope = (seen["metric"] - timed_start) if timed_start is not None and "metric" in seen else None
    report = {
        "schema": "dynamic-vamana-query-timing-v1",
        "system": args.system,
        "query_count": args.query_count,
        "process_wall_seconds": wall,
        "index_load_seconds": load,
        "warmup_seconds": (warmup_end - warmup_start) if warmup_start is not None and warmup_end is not None else 0.0,
        "warmup_disabled_by_artifact": markers["warmup_start"] is None,
        "timed_search_envelope_seconds": envelope,
        "driver_reported_qps": qps,
        "externally_computed_qps": (args.query_count / envelope) if envelope and envelope > 0 else None,
        "marker_elapsed_seconds": seen,
        "returncode": code,
    }
    args.timing.write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
