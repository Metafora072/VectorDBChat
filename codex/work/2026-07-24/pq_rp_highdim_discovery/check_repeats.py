#!/usr/bin/env python3
"""Apply the preregistered conditional-third-repeat rule."""

from __future__ import annotations

import csv
import json
from pathlib import Path

WORK = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_discovery")
RESULTS = WORK / "results"
LABELS = ("pq16", "pq32", "pq64", "exact")
LIMIT = 0.25


def read(label: str, repeat: int) -> dict[int, dict[str, str]]:
    path = RESULTS / f"discovery_{label}_r{repeat}_summary.csv"
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if {int(row["L"]) for row in rows} != {50, 100, 200, 400, 800}:
        raise ValueError(f"incomplete summary: {path}")
    return {int(row["L"]): row for row in rows}


def drift(a: float, b: float) -> float:
    return abs(a - b) / max(min(a, b), 1e-12)


audit: dict[str, object] = {"limit": LIMIT, "representations": {}}
triggered = []
for label in LABELS:
    r1, r2 = read(label, 1), read(label, 2)
    points = {}
    trigger = False
    for search_l in sorted(r1):
        p50 = drift(float(r1[search_l]["p50_us"]), float(r2[search_l]["p50_us"]))
        qps = drift(float(r1[search_l]["qps"]), float(r2[search_l]["qps"]))
        points[str(search_l)] = {
            "p50_drift": p50,
            "qps_drift": qps,
            "within_25pct": p50 <= LIMIT and qps <= LIMIT,
        }
        trigger |= p50 > LIMIT or qps > LIMIT
    audit["representations"][label] = {
        "trigger_third_repeat": trigger,
        "points": points,
    }
    if trigger:
        triggered.append(label)

audit["triggered"] = triggered
(RESULTS / "repeat_gate.json").write_text(
    json.dumps(audit, indent=2, sort_keys=True) + "\n"
)
print(" ".join(triggered))

