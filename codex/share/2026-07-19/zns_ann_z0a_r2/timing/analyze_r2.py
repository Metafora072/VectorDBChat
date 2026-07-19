#!/usr/bin/env python3
"""Pre-registered paired timing and mode-neutral structure analysis for R2."""
from __future__ import annotations

import argparse
import collections
import itertools
import json
import math
import random
import statistics
from pathlib import Path

MODES = ("native", "shim", "full")
METRICS = (
    "async_application_bytes", "async_request_count", "async_page_event_count",
    "unique_logical_pages", "insert_phase_requests", "neighbor_repair_requests",
)


def percentile(rows: list[float], q: float) -> float:
    values = sorted(rows)
    position = (len(values) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return values[low]
    return values[low] * (high - position) + values[high] * (position - low)


def bootstrap_median(values: list[float], seed: int, count: int = 100000) -> dict:
    rng = random.Random(seed)
    n = len(values)
    samples = [statistics.median(values[rng.randrange(n)] for _ in range(n)) for _ in range(count)]
    center = statistics.median(values)
    low, high = percentile(samples, 0.05), percentile(samples, 0.95)
    return {
        "paired_log_values": values,
        "median_log_ratio": center,
        "median_ratio": math.exp(center),
        "median_percent": 100 * (math.exp(center) - 1),
        "ci90_log": [low, high],
        "ci90_ratio": [math.exp(low), math.exp(high)],
        "ci90_percent": [100 * (math.exp(low) - 1), 100 * (math.exp(high) - 1)],
        "equivalence_within_plusminus_5_percent": math.exp(low) >= 0.95 and math.exp(high) <= 1.05,
        "bootstrap_resamples": count,
    }


def structure(path: Path) -> dict:
    row = json.loads(path.read_text())
    phases, roles = row.get("phase_counts", {}), row.get("roles", {})
    return {
        "async_application_bytes": int(row["async_application_bytes"]),
        "async_request_count": int(row["async_request_count"]),
        "async_page_event_count": int(row["async_page_event_count"]),
        "unique_logical_pages": int(row["unique_logical_pages"]),
        "insert_phase_requests": int(phases.get("2", {}).get("requests", 0)),
        "neighbor_repair_requests": int(roles.get("neighbor_repair", {}).get("requests", 0)),
    }


def odin_gate(rows: list[dict]) -> dict:
    output = {}
    for metric in METRICS:
        by_mode = {mode: [row["structure"][metric] for row in rows if row["mode"] == mode] for mode in MODES}
        controls = by_mode["native"] + by_mode["shim"]
        natural_scale = max(controls) - min(controls)
        paired = []
        by_triplet = collections.defaultdict(dict)
        for row in rows:
            by_triplet[row["triplet"]][row["mode"]] = row["structure"][metric]
        for triplet in sorted(by_triplet):
            paired.append(by_triplet[triplet]["full"] - by_triplet[triplet]["shim"])
        shift = statistics.median(paired)
        all_above = all(value > max(controls) for value in by_mode["full"])
        all_below = all(value < min(controls) for value in by_mode["full"])
        output[metric] = {
            "raw_by_mode": by_mode,
            "paired_full_minus_shim": paired,
            "paired_median_shift": shift,
            "native_shim_natural_range": [min(controls), max(controls)],
            "native_shim_natural_scale": natural_scale,
            "shift_within_natural_scale": abs(shift) <= natural_scale,
            "full_systematically_outside_controls_same_side": all_above or all_below,
            "pass": abs(shift) <= natural_scale and not (all_above or all_below),
        }
    return {"metrics": output, "pass": all(row["pass"] for row in output.values())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    schedule = json.loads((args.root / "schedule.json").read_text())
    formal = [row for row in schedule["runs"] if not row["warmup"]]
    rows = []
    for planned in formal:
        directory = args.root / "results" / planned["label"]
        if not (directory / "Z0A_R2_RUN_OK").exists():
            raise ValueError(f"incomplete formal run: {planned['label']}")
        status = json.loads((directory / "run_status.json").read_text())
        if status["returncode"] != 0:
            raise ValueError(f"failed formal run: {planned['label']}")
        active = json.loads((directory / "active_audit.json").read_text())
        if active["status"] != "pass":
            raise ValueError(f"active-set failure: {planned['label']}")
        if planned["mode"] == "full":
            for name in ("trace_summary.json", "trace_meta.json", "trace_ledger.json", "independent_readback.json", "replay_validation.json"):
                evidence = json.loads((directory / name).read_text())
                if evidence.get("status") not in ("pass", "complete"):
                    raise ValueError(f"FULL closure failure {planned['label']} {name}")
        rows.append({**planned, "wall_seconds": float(status["wall_seconds"]), "structure": structure(directory / "common_structure_oracle.json")})

    systems = {}
    for system_index, system in enumerate(("DGAI", "OdinANN"), 1):
        selected = [row for row in rows if row["system"] == system]
        by_triplet = collections.defaultdict(dict)
        for row in selected:
            by_triplet[row["triplet"]][row["mode"]] = row
        order_counts = collections.Counter(
            tuple(row["mode"] for row in sorted(by_triplet[t].values(), key=lambda item: item["position"]))
            for t in sorted(by_triplet)
        )
        expected_orders = set(itertools.permutations(MODES))
        if set(order_counts) != expected_orders or any(count != 2 for count in order_counts.values()):
            raise ValueError(f"unbalanced order schedule for {system}: {order_counts}")
        fs = [math.log(by_triplet[t]["full"]["wall_seconds"] / by_triplet[t]["shim"]["wall_seconds"]) for t in sorted(by_triplet)]
        sn = [math.log(by_triplet[t]["shim"]["wall_seconds"] / by_triplet[t]["native"]["wall_seconds"]) for t in sorted(by_triplet)]
        timing = {
            "full_over_shim": bootstrap_median(fs, 2026071900 + system_index),
            "shim_over_native": bootstrap_median(sn, 2026071910 + system_index),
        }
        timing["temporal_equivalence_pass"] = (
            timing["full_over_shim"]["equivalence_within_plusminus_5_percent"]
            and timing["shim_over_native"]["equivalence_within_plusminus_5_percent"]
        )
        order_effect = {
            mode: {str(position): [row["wall_seconds"] for row in selected if row["mode"] == mode and row["position"] == position]
                   for position in (1, 2, 3)} for mode in MODES
        }
        structural_signatures = {
            mode: len({json.dumps(row["structure"], sort_keys=True) for row in selected if row["mode"] == mode}) for mode in MODES
        }
        systems[system] = {
            "raw_runs": selected,
            "balanced_order_counts": {"/".join(order): count for order, count in sorted(order_counts.items())},
            "timing": timing,
            "run_order_raw_seconds": order_effect,
            "distinct_structure_signatures_by_mode": structural_signatures,
        }
        if system == "DGAI":
            systems[system]["structure_exact_all_modes"] = len({json.dumps(row["structure"], sort_keys=True) for row in selected}) == 1
        else:
            systems[system]["odin_natural_variability_gate"] = odin_gate(selected)

    payload = {
        "schema": "zns-ann-z0a-r2-paired-analysis-v1",
        "status": "pass",
        "preregistered_formal_runs": len(formal),
        "all_runs_retained": len(rows) == len(formal),
        "systems": systems,
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "DGAI_temporal": systems["DGAI"]["timing"]["temporal_equivalence_pass"],
        "OdinANN_temporal": systems["OdinANN"]["timing"]["temporal_equivalence_pass"],
        "OdinANN_structure": systems["OdinANN"]["odin_natural_variability_gate"]["pass"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
