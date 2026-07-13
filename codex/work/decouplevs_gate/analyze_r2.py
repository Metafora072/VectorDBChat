#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import numpy as np


R2_RE = re.compile(r"(oracle_final|oracle_safe|oracle_bw)_L100_W(\d+)_B80_Q(\d+)\.csv$")


def load(path: Path, drop_first: int = 5) -> dict[str, np.ndarray]:
    rows = list(csv.DictReader(path.open()))[drop_first:]
    if not rows:
        raise RuntimeError(f"empty result: {path}")
    out = {}
    for key in rows[0]:
        if key == "mode":
            continue
        out[key] = np.asarray([float(row[key]) for row in rows])
    return out


def pct(values: np.ndarray, q: float) -> float:
    return float(np.percentile(values, q, method="higher"))


def aggregate(d: dict[str, np.ndarray]) -> dict[str, float]:
    return {
        "n": int(len(d["qid"])),
        "recall_mean": float(np.mean(d["recall"])),
        "latency_mean_us": float(np.mean(d["total_us"])),
        "latency_p50_us": pct(d["total_us"], 50),
        "latency_p95_us": pct(d["total_us"], 95),
        "latency_p99_us": pct(d["total_us"], 99),
        "traversal_mean_us": float(np.mean(d["traversal_us"])),
        "tail_mean_us": float(np.mean(d["exposed_vector_tail_us"])),
        "tail_p95_us": pct(d["exposed_vector_tail_us"], 95),
        "tail_p99_us": pct(d["exposed_vector_tail_us"], 99),
        "graph_ios_mean": float(np.mean(d["graph_ios"])),
        "vector_ios_mean": float(np.mean(d["vector_ios"])),
        "trigger_rate": float(np.mean(d["stability_expanded"] > 0)),
        "stability_position_mean": float(np.mean(d["stability_position"])),
        "ready_vector_pages_mean": float(np.mean(d["ready_vector_pages_at_traversal_end"])),
        "unfinished_vector_pages_mean": float(np.mean(d["unfinished_vector_pages_at_traversal_end"])),
        "wasted_prefetch_candidates_mean": float(np.mean(d["wasted_prefetch_candidates"])),
        "oracle_final_set_match_rate": float(np.mean(d.get("oracle_final_set_match", np.zeros(len(d["qid"]))))),
        "oracle_earliest_safe_expanded_mean": float(np.mean(d.get("oracle_earliest_safe_expanded", np.zeros(len(d["qid"]))))),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--r1", type=Path, required=True)
    ap.add_argument("--r2", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    data: dict[tuple[str, int, int], dict[str, np.ndarray]] = {}
    rows = []
    for path in sorted(args.r2.glob("*.csv")):
        match = R2_RE.match(path.name)
        if not match:
            continue
        mode, width, quota = match.group(1), int(match.group(2)), int(match.group(3))
        d = load(path)
        data[(mode, width, quota)] = d
        rows.append({"mode": mode, "width": width, "vector_quota": quota, **aggregate(d)})

    baselines = {}
    for width in (4, 8, 16):
        d = load(args.r1 / f"fixed_L100_W{width}_B80.csv")
        baselines[width] = d
        rows.append({"mode": "fixed", "width": width, "vector_quota": 0, **aggregate(d)})
    write_csv(args.out / "r2_aggregate.csv", rows)

    comparison_rows = []
    offline_rows = []
    summary = {"widths": {}}
    for width in (4, 8, 16):
        base = baselines[width]
        base_agg = aggregate(base)
        configs = [
            ("oracle_final", 1, data[("oracle_final", width, 1)]),
            ("oracle_safe", width, data[("oracle_safe", width, width)]),
        ]
        for mode, quota, d in configs:
            agg = aggregate(d)
            comparison_rows.append({
                "width": width,
                "mode": mode,
                "vector_quota": quota,
                "mean_latency_change_pct": 100 * (agg["latency_mean_us"] / base_agg["latency_mean_us"] - 1),
                "p95_latency_change_pct": 100 * (agg["latency_p95_us"] / base_agg["latency_p95_us"] - 1),
                "p99_latency_change_pct": 100 * (agg["latency_p99_us"] / base_agg["latency_p99_us"] - 1),
                "mean_tail_change_pct": 100 * (agg["tail_mean_us"] / base_agg["tail_mean_us"] - 1),
                "recall_delta": agg["recall_mean"] - base_agg["recall_mean"],
                "vector_ios_delta": agg["vector_ios_mean"] - base_agg["vector_ios_mean"],
                "graph_ios_delta": agg["graph_ios_mean"] - base_agg["graph_ios_mean"],
            })

        bw_items = sorted(
            [(quota, d) for (mode, w, quota), d in data.items() if mode == "oracle_bw" and w == width]
        )
        totals = np.vstack([d["total_us"] for _, d in bw_items])
        best_idx = np.argmin(totals, axis=0)
        best_total = np.min(totals, axis=0)
        best_quotas = np.asarray([bw_items[i][0] for i in best_idx])
        for quota, d in bw_items:
            agg = aggregate(d)
            comparison_rows.append({
                "width": width,
                "mode": "oracle_bw",
                "vector_quota": quota,
                "mean_latency_change_pct": 100 * (agg["latency_mean_us"] / base_agg["latency_mean_us"] - 1),
                "p95_latency_change_pct": 100 * (agg["latency_p95_us"] / base_agg["latency_p95_us"] - 1),
                "p99_latency_change_pct": 100 * (agg["latency_p99_us"] / base_agg["latency_p99_us"] - 1),
                "mean_tail_change_pct": 100 * (agg["tail_mean_us"] / base_agg["tail_mean_us"] - 1),
                "recall_delta": agg["recall_mean"] - base_agg["recall_mean"],
                "vector_ios_delta": agg["vector_ios_mean"] - base_agg["vector_ios_mean"],
                "graph_ios_delta": agg["graph_ios_mean"] - base_agg["graph_ios_mean"],
            })
            offline_rows.append({
                "width": width,
                "vector_quota": quota,
                "best_count": int(np.sum(best_quotas == quota)),
                "best_fraction": float(np.mean(best_quotas == quota)),
            })

        summary["widths"][str(width)] = {
            "baseline": base_agg,
            "oracle_final": aggregate(data[("oracle_final", width, 1)]),
            "oracle_safe": aggregate(data[("oracle_safe", width, width)]),
            "offline_bandwidth_oracle": {
                "latency_mean_us": float(np.mean(best_total)),
                "latency_p50_us": pct(best_total, 50),
                "latency_p95_us": pct(best_total, 95),
                "latency_p99_us": pct(best_total, 99),
                "mean_change_vs_fixed_pct": 100 * (float(np.mean(best_total)) / base_agg["latency_mean_us"] - 1),
                "p95_change_vs_fixed_pct": 100 * (pct(best_total, 95) / base_agg["latency_p95_us"] - 1),
                "p99_change_vs_fixed_pct": 100 * (pct(best_total, 99) / base_agg["latency_p99_us"] - 1),
                "quota_distribution": {str(q): int(np.sum(best_quotas == q)) for q, _ in bw_items},
            },
        }

    write_csv(args.out / "r2_comparisons.csv", comparison_rows)
    write_csv(args.out / "r2_offline_bandwidth_choices.csv", offline_rows)
    (args.out / "r2_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
