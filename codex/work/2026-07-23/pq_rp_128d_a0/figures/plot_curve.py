from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from paper_plot_style import COLORS, LABELS, MARKERS, save_figure

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "results/curve_summary.csv"


def generate(metric: str, ylabel: str, output: str, scale: float = 1.0) -> None:
    with DATA.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    fig, ax = plt.subplots(figsize=(4.8, 3.25))
    for label in ("pq8", "pq16", "pq32", "exact"):
        block = sorted(
            (row for row in rows if row["label"] == label),
            key=lambda row: float(row["recall_at_10"]),
        )
        x = np.array([100.0 * float(row["recall_at_10"]) for row in block])
        y = np.array([float(row[metric]) / scale for row in block])
        lower = np.array([float(row[f"{metric}_min"]) / scale for row in block])
        upper = np.array([float(row[f"{metric}_max"]) / scale for row in block])
        ax.plot(
            x, y, color=COLORS[label], marker=MARKERS[label],
            linewidth=1.7, markersize=4.5, label=LABELS[label],
        )
        ax.fill_between(x, lower, upper, color=COLORS[label], alpha=0.12, linewidth=0)
    ax.set_xlabel("Recall@10 (%)")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color="#d9d9d9", linewidth=0.55)
    ax.legend(frameon=False, ncol=2)
    save_figure(fig, output)

