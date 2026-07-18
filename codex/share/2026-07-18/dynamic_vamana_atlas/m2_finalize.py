#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def ratio(a: float, b: float) -> float:
    return a / b


def page_distribution(hist: dict[str, int]) -> dict:
    rows = sorted(((int(touches), int(pages)) for touches, pages in hist.items()), reverse=True)
    total_pages = sum(pages for _, pages in rows)
    total_touches = sum(touches * pages for touches, pages in rows)
    rewritten_pages = sum(pages for touches, pages in rows if touches > 1)
    rewritten_touches = sum(touches * pages for touches, pages in rows if touches > 1)

    def top_fraction(fraction: float) -> dict:
        target = max(1, int(total_pages * fraction + 0.999999999))
        remaining = target
        touches_sum = 0
        for touches, pages in rows:
            take = min(remaining, pages)
            touches_sum += touches * take
            remaining -= take
            if remaining == 0:
                break
        return {"page_count": target, "touch_count": touches_sum, "touch_fraction": touches_sum / total_touches}

    return {
        "total_pages": total_pages,
        "total_touches": total_touches,
        "rewritten_page_fraction": rewritten_pages / total_pages,
        "touch_fraction_from_rewritten_pages": rewritten_touches / total_touches,
        "top_1pct_pages": top_fraction(0.01),
        "top_10pct_pages": top_fraction(0.10),
    }


parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--result-root", type=Path, required=True)
parser.add_argument("--formal-root", type=Path, required=True)
parser.add_argument("--build-manifest", type=Path, required=True)
parser.add_argument("--m1-summary", type=Path, required=True)
parser.add_argument("--free-before", type=int, required=True)
args = parser.parse_args()

points = []
for size in (50000, 400000):
    for system in ("DGAI", "OdinANN"):
        path = args.result_root / system / f"m2-n{size}-01/m2_summary.json"
        row = load(path)
        assert row["status"] == "pass" and row["system"] == system and row["size"] == size
        row["summary"] = str(path.resolve())
        row["summary_sha256"] = sha256(path)
        row["page_distribution"] = page_distribution(row["page_touch_frequency"]["submitted_neighbor_only_pages"])
        points.append(row)

comparisons = {}
by_key = {(row["system"], row["size"]): row for row in points}
for size in (50000, 400000):
    dg = by_key[("DGAI", size)]
    od = by_key[("OdinANN", size)]
    dm, om = dg["metrics"], od["metrics"]
    factors = {
        "repair_fanout_ratio": ratio(om["repair_attempts_per_replacement"], dm["repair_attempts_per_replacement"]),
        "accepted_repair_ratio": ratio(om["accepted_reverse_updates_per_replacement"], dm["accepted_reverse_updates_per_replacement"]),
        "mutated_record_ratio": ratio(om["mutated_neighbor_records_per_replacement"], dm["mutated_neighbor_records_per_replacement"]),
        "stage_unique_page_mapping_ratio": ratio(om["stage_unique_neighbor_only_pages_per_scheduled_record"], dm["stage_unique_neighbor_only_pages_per_scheduled_record"]),
        "temporal_rewrite_ratio": ratio(om["temporal_rewrite_factor"], dm["temporal_rewrite_factor"]),
        "physical_neighbor_write_ratio": ratio(om["neighbor_write_bytes_per_replacement"], dm["neighbor_write_bytes_per_replacement"]),
    }
    factors["exact_factor_product"] = factors["repair_fanout_ratio"] * factors["stage_unique_page_mapping_ratio"] * factors["temporal_rewrite_ratio"]
    factors["product_equals_physical_ratio"] = abs(factors["exact_factor_product"] - factors["physical_neighbor_write_ratio"]) < 1e-12
    comparisons[str(size)] = factors

free_after = int(__import__("subprocess").check_output(["df", "-PB1", str(args.root)], text=True).splitlines()[1].split()[3])
formal_bytes = sum(path.stat().st_size for path in args.formal_root.rglob("*") if path.is_file())
result_bytes = sum(path.stat().st_size for path in args.result_root.rglob("*") if path.is_file())
build = load(args.build_manifest)
m1 = load(args.m1_summary)
freeze = {}
for system in ("DGAI", "OdinANN"):
    path = args.root / f"results/pilot3_sift10m_w1_cp10_trajectory_r12/{system}/trajectory-cp10-12/checkpoints/cp10/cp10_freeze_evidence.json"
    freeze[system] = {"path": str(path.resolve()), "sha256": sha256(path)}

summary = {
    "schema": "dynamic-vamana-neighbor-repair-m2-summary-v1",
    "status": "complete",
    "completed_at_utc8": datetime.now(timezone(timedelta(hours=8))).isoformat(),
    "scope": "DGAI/OdinANN 50K and 400K only; no optimization prototype",
    "m1_scale_summary": {"path": str(args.m1_summary.resolve()), "sha256": sha256(args.m1_summary)},
    "build_manifest": {"path": str(args.build_manifest.resolve()), "sha256": sha256(args.build_manifest), "profiler_sha256": build["profiler_sha256"]},
    "frozen_sources": freeze,
    "points": points,
    "cross_system_factor_decomposition": comparisons,
    "space": {
        "free_before_bytes": args.free_before,
        "free_after_bytes": free_after,
        "free_space_delta_bytes": args.free_before - free_after,
        "formal_apparent_bytes": formal_bytes,
        "result_apparent_bytes": result_bytes,
    },
    "m1_physical_points_preserved": len(m1["points"]) == 8,
    "experiments_started_beyond_gate": False,
}
output = args.result_root / "m2_summary.json"
output.write_text(json.dumps(summary, indent=2) + "\n")
(args.result_root / "M2_COMPLETE").touch()
print(output)
