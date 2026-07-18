#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def histogram_stats(hist: dict[str, int]) -> dict:
    pairs = sorted((int(value), int(count)) for value, count in hist.items())
    count = sum(freq for _, freq in pairs)
    total = sum(value * freq for value, freq in pairs)

    def quantile(q: float) -> int:
        rank = max(1, math.ceil(q * count))
        seen = 0
        for value, freq in pairs:
            seen += freq
            if seen >= rank:
                return value
        raise AssertionError("empty histogram")

    return {
        "operation_count": count,
        "mean": total / count,
        "median": quantile(0.5),
        "p95": quantile(0.95),
        "p99": quantile(0.99),
        "max": pairs[-1][0],
    }


parser = argparse.ArgumentParser()
parser.add_argument("--system", required=True, choices=("DGAI", "OdinANN"))
parser.add_argument("--size", required=True, type=int, choices=(50000, 400000))
parser.add_argument("--physical-summary", required=True, type=Path)
parser.add_argument("--logical-profile", required=True, type=Path)
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()

physical = load(args.physical_summary)
logical = load(args.logical_profile)
totals = logical["totals"]
hists = logical["operation_histograms"]
roles = {row["role"]: row for row in physical["application_writes"]["logical_roles"]}
physical_neighbor_bytes = int(roles["neighbor_repair"]["requested_bytes"])
submitted_touches = int(totals["neighbor_only_submitted_page_touches"])
logical_events = int(totals["neighbor_only_logical_page_events"])
stage_unique = int(totals["stage_unique_neighbor_only_pages"])
attempts = int(totals["reverse_edge_repair_attempts"])
mutated = int(totals["mutated_neighbor_node_records"])

gates = {
    "physical_formal_pass": physical["status"] == "pass" and all(physical["gates"].values()),
    "logical_schema_complete": logical.get("schema") == "dynamic-vamana-neighbor-repair-m2-logical-v1" and logical.get("status") == "complete",
    "identity_exact": physical["system"] == args.system and physical["size"] == args.size and logical["config"]["system"] == args.system,
    "replacement_count_exact": int(totals["replacements"]) == args.size,
    "histogram_operation_count_exact": all(sum(int(v) for v in hist.values()) == args.size for hist in hists.values()),
    "fanout_identity_exact": attempts == int(totals["accepted_reverse_edge_updates"]) + int(totals["pruned_or_rejected_updates"]),
    "per_operation_page_closure": logical["closure"]["operation_page_set_mismatch_count"] == 0,
    "logical_submit_count_closure": logical_events == submitted_touches and logical["closure"]["logical_neighbor_only_events_equal_submitted_touches"],
    "physical_byte_closure": physical_neighbor_bytes == submitted_touches * 4096,
    "configuration_stable": logical["closure"]["configuration_mismatch_count"] == 0,
    "positive_stage_unique_pages": stage_unique > 0,
}

metrics = {
    "repair_attempts_per_replacement": attempts / args.size,
    "accepted_reverse_updates_per_replacement": int(totals["accepted_reverse_edge_updates"]) / args.size,
    "mutated_neighbor_records_per_replacement": mutated / args.size,
    "logical_neighbor_pages_per_replacement": int(totals["neighbor_logical_page_events"]) / args.size,
    "logical_neighbor_only_pages_per_replacement": logical_events / args.size,
    "submitted_neighbor_only_pages_per_replacement": submitted_touches / args.size,
    "scheduled_nodes_per_logical_neighbor_only_page": attempts / logical_events,
    "mutated_nodes_per_logical_neighbor_only_page": mutated / logical_events,
    "temporal_rewrite_factor": submitted_touches / stage_unique,
    "neighbor_write_bytes_per_replacement": physical_neighbor_bytes / args.size,
    "stage_unique_neighbor_only_pages_per_scheduled_record": stage_unique / attempts,
    "logical_to_submit_factor": submitted_touches / logical_events,
}
metrics["exact_stage_factor_product"] = (
    metrics["repair_attempts_per_replacement"]
    * metrics["stage_unique_neighbor_only_pages_per_scheduled_record"]
    * metrics["temporal_rewrite_factor"]
)
metrics["exact_stage_factor_product_equals_submitted_pages_per_replacement"] = math.isclose(
    metrics["exact_stage_factor_product"], metrics["submitted_neighbor_only_pages_per_replacement"], rel_tol=0, abs_tol=1e-12
)

report = {
    "schema": "dynamic-vamana-neighbor-repair-m2-run-v1",
    "status": "pass" if all(gates.values()) else "fail",
    "system": args.system,
    "size": args.size,
    "physical_summary": str(args.physical_summary.resolve()),
    "logical_profile": str(args.logical_profile.resolve()),
    "physical_summary_sha256": sha256(args.physical_summary),
    "logical_profile_sha256": sha256(args.logical_profile),
    "config": logical["config"],
    "totals": totals,
    "histogram_statistics": {name: histogram_stats(hist) for name, hist in hists.items()},
    "page_touch_frequency": logical["page_touch_frequency"],
    "hottest_submitted_neighbor_only_page": logical["hottest_submitted_neighbor_only_page"],
    "metrics": metrics,
    "physical_neighbor_repair_only_bytes": physical_neighbor_bytes,
    "gates": gates,
}
args.output.write_text(json.dumps(report, indent=2) + "\n")
if report["status"] != "pass":
    raise SystemExit("M2 logical/physical gate failed")
print(args.output)
