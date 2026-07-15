#!/usr/bin/env python3
"""Fail-closed statistics gate for fixed-configuration query repetitions."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path


T975 = {2: 4.302653, 9: 2.262157}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--points-root", type=Path, required=True)
    p.add_argument("--expected-count", type=int, required=True)
    p.add_argument("--historical-recall", type=float, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    paths = sorted(args.points_root.glob("r*/point.json"))
    rows = [json.loads(path.read_text()) for path in paths]
    if len(rows) != args.expected_count:
        raise SystemExit(f"expected {args.expected_count} points, found {len(rows)}")
    invalid = [str(path) for path, row in zip(paths, rows) if row.get("valid") is not True]
    if invalid:
        raise SystemExit("invalid repeat point(s): " + ", ".join(invalid))
    identities = [json.dumps(row.get("artifact_identity"), sort_keys=True) for row in rows]
    if not identities[0] or any(item != identities[0] for item in identities[1:]):
        raise SystemExit("artifact identity missing or inconsistent across repetitions")
    values = [float(row["recall_at_10"]) for row in rows]
    n = len(values)
    sample_sd = statistics.stdev(values) if n > 1 else 0.0
    critical = T975.get(n - 1)
    if critical is None:
        raise SystemExit(f"no t critical value configured for n={n}")
    mean = statistics.mean(values)
    ci_half = critical * sample_sd / math.sqrt(n)
    pi_half = critical * sample_sd * math.sqrt(1 + 1 / n)
    prediction = [mean - pi_half, mean + pi_half]
    passed = ci_half <= 0.001 and prediction[0] <= args.historical_recall <= prediction[1]
    payload = {"schema": "dynamic-vamana-repeatability-v1", "n": n, "recalls": values,
               "mean_recall": mean, "median_recall": statistics.median(values), "sample_sd": sample_sd,
               "minimum_recall": min(values), "maximum_recall": max(values),
               "confidence_interval_95": [mean - ci_half, mean + ci_half], "ci_half_width_95": ci_half,
               "prediction_interval_95": prediction, "historical_f0_recall": args.historical_recall,
               "historical_within_prediction_interval": prediction[0] <= args.historical_recall <= prediction[1],
               "passed": passed, "point_paths": [str(path) for path in paths]}
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    if not passed:
        raise SystemExit("repeatability gate failed")


if __name__ == "__main__":
    main()
