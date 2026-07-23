from pathlib import Path

import matplotlib.pyplot as plt

FIG_DIR = Path(__file__).resolve().parent
COLORS = {
    "pq8": "#0072B2",
    "pq16": "#E69F00",
    "pq32": "#009E73",
    "exact": "#CC79A7",
}
MARKERS = {"pq8": "o", "pq16": "s", "pq32": "^", "exact": "D"}
LABELS = {"pq8": "PQ-8B", "pq16": "PQ-16B", "pq32": "PQ-32B", "exact": "Exact nav"}

plt.rcParams.update({
    "font.size": 10,
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.04,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "mathtext.fontset": "stix",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


def save_figure(fig, name: str) -> None:
    fig.savefig(FIG_DIR / f"{name}.pdf")
    fig.savefig(FIG_DIR / f"{name}.png")
    plt.close(fig)

