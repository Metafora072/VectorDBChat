#!/usr/bin/env python3
"""Summarize one multi-L process while preserving per-query raw data."""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--phase", required=True)
parser.add_argument("--label", required=True)
parser.add_argument("--mode", required=True)
parser.add_argument("--repeat", type=int, required=True)
parser.add_argument("--metrics", type=Path, required=True)
parser.add_argument("--time-log", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()

with args.metrics.open(newline="") as handle:
    rows = list(csv.DictReader(handle))
if len(rows) % 5 != 0:
    raise ValueError(f"expected five equal L blocks, got {len(rows)} rows")

time_text = args.time_log.read_text()
rss_match = re.search(r"Maximum resident set size \(kbytes\):\s+(\d+)", time_text)
elapsed_match = re.search(r"Elapsed \(wall clock\) time.*:\s+([^\n]+)", time_text)
peak_rss_kib = int(rss_match.group(1)) if rss_match else -1

fields = [
    "phase", "label", "mode", "repeat", "L", "queries", "qps", "run_wall_s",
    "p50_us", "p95_us", "p99_us", "mean_cpu_us", "mean_io_us",
    "mean_comparisons", "mean_hops", "mean_ios", "mean_exact_nav_reads",
    "ssd_bytes_per_query", "nav_dram_bytes_per_query", "touched_bytes_per_query",
    "peak_rss_kib", "process_elapsed",
]
out = []
for search_l in sorted({int(row["L"]) for row in rows}):
    block = [row for row in rows if int(row["L"]) == search_l]
    latency = np.array([float(row["total_us"]) for row in block])
    mean_ios = float(np.mean([float(row["n_ios"]) for row in block]))
    mean_exact = float(np.mean([float(row["n_exact_nav_reads"]) for row in block]))
    ssd_bytes = 4096.0 * mean_ios
    nav_bytes = 128.0 * 4.0 * mean_exact
    out.append({
        "phase": args.phase,
        "label": args.label,
        "mode": args.mode,
        "repeat": args.repeat,
        "L": search_l,
        "queries": len(block),
        "qps": float(block[0]["qps"]),
        "run_wall_s": float(block[0]["run_wall_s"]),
        "p50_us": float(np.quantile(latency, 0.50)),
        "p95_us": float(np.quantile(latency, 0.95)),
        "p99_us": float(np.quantile(latency, 0.99)),
        "mean_cpu_us": float(np.mean([float(row["cpu_us"]) for row in block])),
        "mean_io_us": float(np.mean([float(row["io_us"]) for row in block])),
        "mean_comparisons": float(np.mean([float(row["n_cmps"]) for row in block])),
        "mean_hops": float(np.mean([float(row["n_hops"]) for row in block])),
        "mean_ios": mean_ios,
        "mean_exact_nav_reads": mean_exact,
        "ssd_bytes_per_query": ssd_bytes,
        "nav_dram_bytes_per_query": nav_bytes,
        "touched_bytes_per_query": ssd_bytes + nav_bytes,
        "peak_rss_kib": peak_rss_kib,
        "process_elapsed": elapsed_match.group(1).strip() if elapsed_match else "",
    })

args.output.parent.mkdir(parents=True, exist_ok=True)
with args.output.open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(out)
