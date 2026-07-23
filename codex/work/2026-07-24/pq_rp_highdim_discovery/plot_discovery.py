#!/usr/bin/env python3
"""Plot the GIST960 Recall–Performance–DRAM characterization."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt

WORK = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_discovery")
SHARE = Path("/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-24")
rows = list(csv.DictReader((WORK / "results/curve_summary.csv").open()))
colors = {"pq16": "#377eb8", "pq32": "#4daf4a", "pq64": "#e41a1c", "exact": "#555555"}
labels = {"pq16": "PQ16 (16 MB)", "pq32": "PQ32 (32 MB)", "pq64": "PQ64 (64 MB)", "exact": "Exact-nav (3.84 GB)"}

fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
for label in ("pq16", "pq32", "pq64", "exact"):
    block = sorted(
        (row for row in rows if row["label"] == label),
        key=lambda row: int(row["L"]),
    )
    recall = [100.0 * float(row["recall_at_10"]) for row in block]
    reads = [float(row["mean_ios"]) for row in block]
    qps = [float(row["qps"]) for row in block]
    axes[0].plot(reads, recall, marker="o", color=colors[label], label=labels[label])
    axes[1].plot(qps, recall, marker="o", color=colors[label], label=labels[label])
    for ax, xs in ((axes[0], reads), (axes[1], qps)):
        for x, y, row in zip(xs, recall, block):
            ax.annotate(f"L{row['L']}", (x, y), xytext=(3, 3), textcoords="offset points", fontsize=7)

axes[0].set_xlabel("SSD reads / query")
axes[0].set_ylabel("Recall@10 (%)")
axes[0].set_xscale("log")
axes[0].set_title("Structural frontier")
axes[1].set_xlabel("Queries / second")
axes[1].set_ylabel("Recall@10 (%)")
axes[1].set_xscale("log")
axes[1].set_title("End-to-end frontier")
for ax in axes:
    ax.grid(True, which="both", alpha=0.25)
axes[0].legend(fontsize=8, loc="lower right")
fig.suptitle("GIST1M-960D: uniform PQ precision trade-off (discovery only)")
fig.tight_layout()
SHARE.mkdir(parents=True, exist_ok=True)
fig.savefig(SHARE / "pq_rp_highdim_discovery_frontier_0724.png", dpi=180, bbox_inches="tight")
fig.savefig(WORK / "results/frontier.png", dpi=180, bbox_inches="tight")

