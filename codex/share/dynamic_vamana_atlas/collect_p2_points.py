#!/usr/bin/env python3
"""Collect P2 raw point JSON files and determine measured common Recall coverage."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path


TARGETS = [0.93, 0.95, 0.97, 0.98, 0.99]
SYSTEMS = ["DiskANN", "DGAI", "OdinANN"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-root", type=Path, required=True)
    p.add_argument("--output-tsv", type=Path, required=True)
    p.add_argument("--raw-output-tsv", type=Path)
    p.add_argument("--summary", type=Path, required=True)
    args = p.parse_args()
    rows = [json.loads(path.read_text()) for path in sorted(args.raw_root.glob("*/tq*/L*/r*/point.json"))]
    if not rows:
        raise SystemExit("no P2 point.json files")
    keys = sorted({key for row in rows for key in row})
    if args.raw_output_tsv:
        with args.raw_output_tsv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys, delimiter="\t", extrasaction="ignore")
            writer.writeheader(); writer.writerows(rows)
    valid_rows = [row for row in rows if row.get("valid") is True]
    invalid_rows = [row for row in rows if row.get("valid") is not True]
    groups: dict[tuple[str, int, float], list[dict]] = {}
    for row in valid_rows:
        groups.setdefault((row["system"], row["query_threads"], row["L"]), []).append(row)
    median_rows = []
    incomplete_groups = []
    for key, group in sorted(groups.items()):
        identities = {json.dumps(row.get("artifact_identity"), sort_keys=True) for row in group}
        if len(group) != 3 or len(identities) != 1 or not next(iter(identities)):
            incomplete_groups.append({"system": key[0], "query_threads": key[1], "L": key[2], "valid_repeat_count": len(group)})
            continue
        row = {"system": key[0], "query_threads": key[1], "L": key[2], "repeat_count": len(group),
               "valid": True, "artifact_identity": group[0]["artifact_identity"]}
        for metric in ("recall_at_10", "external_qps", "mean_latency_us", "p99_latency_us", "p999_latency_us",
                       "mean_ios", "mean_io_us", "device_read_bytes_delta"):
            values = [item[metric] for item in group if item.get(metric) is not None]
            if values:
                row[metric] = statistics.median(values)
        median_rows.append(row)
    median_keys = sorted({key for row in median_rows for key in row})
    with args.output_tsv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=median_keys, delimiter="\t", extrasaction="ignore")
        writer.writeheader(); writer.writerows(median_rows)
    invalid_reasons: dict[str, int] = {}
    for row in invalid_rows:
        reason = str(row.get("invalid_reason") or "unspecified_invalid_point")
        invalid_reasons[reason] = invalid_reasons.get(reason, 0) + 1

    coverage: dict[str, dict[str, object]] = {}
    for target in TARGETS:
        per_system = {}
        for system in SYSTEMS:
            recalls = sorted(row["recall_at_10"] for row in median_rows
                             if row["system"] == system and row["query_threads"] == 1)
            lower = max((x for x in recalls if x <= target), default=None)
            upper = min((x for x in recalls if x >= target), default=None)
            per_system[system] = {"lower": lower, "upper": upper, "covered": lower is not None and upper is not None}
        coverage[str(target)] = per_system
    common = [float(target) for target, per in coverage.items() if all(per[s]["covered"] for s in SYSTEMS)]
    args.summary.write_text(json.dumps({
        "schema": "dynamic-vamana-p2-calibration-summary-v2",
        "targets": coverage,
        "common_targets": common,
        "point_count": len(rows),
        "valid_point_count": len(valid_rows),
        "invalid_point_count": len(invalid_rows),
        "invalid_reasons": invalid_reasons,
        "median_point_count": len(median_rows),
        "incomplete_or_identity_mismatched_groups": incomplete_groups,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
