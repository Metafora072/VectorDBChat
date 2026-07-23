#!/usr/bin/env python3
from plot_curve import generate

generate(
    "touched_bytes_per_query",
    "NVMe + navigation DRAM bytes/query (KiB)",
    "fig7_recall_bytes",
    scale=1024.0,
)
