#!/usr/bin/env python3
"""Aggregate GraphAging A0 results without hiding early-stop decisions."""

from __future__ import annotations

import json
import glob
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"


def jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summary(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    mean = statistics.mean(values)
    if len(values) == 1:
        return {"n": 1, "mean": mean, "std": 0.0, "ci95": 0.0, "min": mean, "max": mean}
    std = statistics.stdev(values)
    t95 = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776}.get(len(values), 1.96)
    return {
        "n": len(values),
        "mean": mean,
        "std": std,
        "ci95": t95 * std / math.sqrt(len(values)),
        "min": min(values),
        "max": max(values),
    }


def pct(now: float, base: float) -> float:
    return (now / base - 1.0) * 100.0


def official_searches(name: str, checkpoints: list[int]) -> list[dict]:
    path = RESULTS / "ip_diskann" / name
    if not path.exists():
        return []
    payload = json.loads(path.read_text())[0]["results"]
    searches = []
    for stage_index, item in enumerate(payload, start=1):
        if "Search" not in item:
            continue
        row = item["Search"][0]
        searches.append(
            {
                "result_index": stage_index,
                "recall_at_10": row["recall"]["average"],
                "distance_calcs_mean": row["mean_cmps"],
                "hops_mean": row["mean_hops"],
                "latency_mean_us": row["mean_latencies"][0],
                "latency_p99_us": row["p99_latencies"][0],
                "qps": row["qps"][0],
            }
        )
    for row, checkpoint in zip(searches, checkpoints):
        row["checkpoint"] = checkpoint
    return searches


def main() -> None:
    static = jsonl(RESULTS / "static_seeds.jsonl")
    g0 = next(r for r in jsonl(RESULTS / "a01_full.jsonl") if r["label"] == "g0_identity")
    a01_10pct = jsonl(RESULTS / "a01_seeds.jsonl")
    a01_1pct = jsonl(RESULTS / "a01_1pct_seed2001_v2.jsonl")
    path2 = jsonl(RESULTS / "a02_path2_seed11_v3.jsonl")
    path2_all = [row for path in sorted(RESULTS.glob("a02_path2_seed*_v2.jsonl")) for row in jsonl(path)]
    path3_all = [row for path in sorted(RESULTS.glob("a02_path3_seed*_v2.jsonl")) for row in jsonl(path)]
    smoke = jsonl(RESULTS / "smoke_v2.jsonl")

    official_replace = official_searches("sift1m_cycle_100.json", [0, 1, 10, 100])
    official_ipdelete = official_searches("sift1m_ipdelete_cycle_100.json", [0, 1, 10, 100])

    build_recall = summary([r["recall_at_10"] for r in static])
    build_cmps = summary([r["distance_calcs_mean"] for r in static])

    a01_by_cp = {}
    for cp in (1, 10, 100):
        rows = [r for r in a01_10pct if r["checkpoint"] == cp]
        a01_by_cp[str(cp)] = {
            "recall": summary([r["recall_at_10"] for r in rows]),
            "distance_calcs": summary([r["distance_calcs_mean"] for r in rows]),
            "edge_jaccard": summary([r["edge_jaccard_vs_g0"] for r in rows]),
        }
    for row in a01_1pct:
        if row["experiment"] == "a0_1":
            a01_by_cp[f"1pct_{row['checkpoint']}"] = row
    fresh_oracle = [r for r in a01_1pct if r["experiment"] == "a0_4"]

    def with_delta(rows: list[dict]) -> list[dict]:
        if not rows:
            return []
        base = rows[0]
        out = []
        for row in rows:
            item = dict(row)
            item["delta_recall_pp"] = (row["recall_at_10"] - base["recall_at_10"]) * 100.0
            item["delta_distance_calcs_pct"] = pct(row["distance_calcs_mean"], base["distance_calcs_mean"])
            item["delta_hops_pct"] = pct(row["hops_mean"], base["hops_mean"])
            out.append(item)
        return out

    path2_summary = {}
    if path2:
        static11 = next(r for r in static if r["label"] == "static_seed11")
        for row in path2:
            path2_summary[row["experiment"]] = {
                "row": row,
                "delta_recall_vs_static11_pp": (row["recall_at_10"] - static11["recall_at_10"]) * 100.0,
                "delta_cmps_vs_static11_pct": pct(row["distance_calcs_mean"], static11["distance_calcs_mean"]),
            }

    def path_aggregate(rows: list[dict]) -> dict:
        result = {}
        for experiment in sorted({row["experiment"] for row in rows}):
            selected = [row for row in rows if row["experiment"] == experiment]
            result[experiment] = {
                "n": len(selected),
                "recall": summary([row["recall_at_10"] for row in selected]),
                "distance_calcs_mean": summary([row["distance_calcs_mean"] for row in selected]),
                "distance_calcs_p50": summary([row["distance_calcs_p50"] for row in selected]),
                "distance_calcs_p95": summary([row["distance_calcs_p95"] for row in selected]),
                "distance_calcs_p99": summary([row["distance_calcs_p99"] for row in selected]),
                "visited_nodes_mean": summary([row["visited_nodes_mean"] for row in selected]),
                "visited_nodes_p50": summary([row["visited_nodes_p50"] for row in selected]),
                "visited_nodes_p95": summary([row["visited_nodes_p95"] for row in selected]),
                "visited_nodes_p99": summary([row["visited_nodes_p99"] for row in selected]),
                "edge_jaccard": summary([row["edge_jaccard_vs_g0"] for row in selected]),
            }
        return result

    smoke_oracle = [r for r in smoke if r["experiment"] == "a0_4"]
    output = {
        "decision": "KILL_NO_PROBLEM_AND_SHADOW_NO_UTILITY",
        "decision_reason": (
            "Official IP-DiskANN and PipeANN update histories did not reach the pre-registered "
            "1pp recall-loss or 5% search-work-growth gate, while Oracle Shadow Replay did not "
            "improve the fixed-L recall/work tradeoff."
        ),
        "g0": g0,
        "ordinary_build_seed_variance": {"recall": build_recall, "distance_calcs": build_cmps},
        "freshdiskann_pipeann": a01_by_cp,
        "freshdiskann_oracle_shadow": fresh_oracle,
        "official_diskann3_replace_control": with_delta(official_replace),
        "official_ip_diskann_explicit_delete": with_delta(official_ipdelete),
        "path2_seed11": path2_summary,
        "path2_five_seed": path_aggregate(path2_all),
        "path3_five_seed": path_aggregate(path3_all),
        "smoke_oracle_shadow": smoke_oracle,
        "early_stop": {
            "not_run": [
                "full seven-history x multi-seed matrix",
                "A0-3 filesystem/block write tracing",
                "semi-coupled system implementation",
            ],
            "why": "The pre-registered strong-baseline and shadow-utility stop gates fired.",
        },
    }
    out = RESULTS / "final_summary.json"
    out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
