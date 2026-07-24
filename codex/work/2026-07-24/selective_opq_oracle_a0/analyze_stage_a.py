#!/usr/bin/env python3
"""Analyze Stage-A algorithmic results and selector overlap/coverage."""

from __future__ import annotations

import csv
import gzip
import itertools
import json
from pathlib import Path

import numpy as np

WORK = Path("/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/selective_opq_oracle_a0")
SOURCE = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_highdim_a0_0724")
DATA = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/selective_opq_oracle_a0_0724")
LS = (50, 100, 200, 400, 800)
BUDGETS = (40, 48, 56)
SELECTORS = ("random", "visit_frequency", "distance_regret", "routing_aware")
ROUTING = ("distance_regret", "routing_aware")
N = 1_000_000


gt = np.memmap(
    SOURCE / "converted/gist_gt100.truthset",
    dtype="<u4",
    mode="r",
    offset=8,
    shape=(1000, 100),
)


def load_metrics(path: Path) -> dict[int, list[dict[str, str]]]:
    result: dict[int, list[dict[str, str]]] = {}
    with gzip.open(path, "rt", newline="") as handle:
        for row in csv.DictReader(handle):
            result.setdefault(int(row["L"]), []).append(row)
    for search_l, rows in result.items():
        if len(rows) != 1000:
            raise RuntimeError(f"{path} L{search_l}: expected 1000 rows, got {len(rows)}")
    return result


def summarize(rows: list[dict[str, str]]) -> dict[str, float | int]:
    hits = 0
    reads = []
    comparisons = []
    for row in rows:
        qid = int(row["qid"])
        returned = {int(row[f"id{k}"]) for k in range(10)}
        hits += len(returned & set(map(int, gt[qid, :10])))
        reads.append(float(row["n_ios"]))
        comparisons.append(float(row["n_cmps"]))
    return {
        "hits": hits,
        "recall": hits / 10_000.0,
        "reads": float(np.mean(reads)),
        "comparisons": float(np.mean(comparisons)),
    }


uniform: dict[int, dict[int, dict[str, float | int]]] = {}
for budget in BUDGETS:
    by_l = load_metrics(DATA / f"results/uniform_opq{budget}.csv.gz")
    uniform[budget] = {search_l: summarize(by_l[search_l]) for search_l in LS}

rows_out: list[dict[str, object]] = []
positive_routing: list[dict[str, object]] = []
positive_controls: list[dict[str, object]] = []
for search_l in LS:
    for budget in BUDGETS:
        baseline = uniform[budget][search_l]
        for selector in SELECTORS:
            path = DATA / f"results/mixed_L{search_l}_b{budget}_{selector}.csv.gz"
            metrics = summarize(load_metrics(path)[search_l])
            recall_delta = float(metrics["recall"]) - float(baseline["recall"])
            hits_delta = int(metrics["hits"]) - int(baseline["hits"])
            reads_abs = float(baseline["reads"]) - float(metrics["reads"])
            comps_abs = float(baseline["comparisons"]) - float(metrics["comparisons"])
            reads_pct = 100.0 * reads_abs / float(baseline["reads"])
            comps_pct = 100.0 * comps_abs / float(baseline["comparisons"])
            signal = recall_delta >= 0 and reads_abs > 0 and comps_abs > 0
            row = {
                "L": search_l,
                "budget": budget,
                "selector": selector,
                "baseline_recall": baseline["recall"],
                "mixed_recall": metrics["recall"],
                "recall_delta": recall_delta,
                "baseline_hits": baseline["hits"],
                "mixed_hits": metrics["hits"],
                "hits_delta": hits_delta,
                "baseline_reads": baseline["reads"],
                "mixed_reads": metrics["reads"],
                "reads_reduction_abs": reads_abs,
                "reads_reduction_pct": reads_pct,
                "baseline_comparisons": baseline["comparisons"],
                "mixed_comparisons": metrics["comparisons"],
                "comparisons_reduction_abs": comps_abs,
                "comparisons_reduction_pct": comps_pct,
                "strict_signal": signal,
            }
            rows_out.append(row)
            if signal:
                (positive_routing if selector in ROUTING else positive_controls).append(row)

comparison_path = WORK / "results/stage_a_comparison.csv"
with comparison_path.open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows_out[0]))
    writer.writeheader()
    writer.writerows(rows_out)

with (WORK / "results/uniform_summary.csv").open("w", newline="") as handle:
    fieldnames = ("budget", "L", "hits", "recall", "reads", "comparisons")
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    for budget in BUDGETS:
        for search_l in LS:
            writer.writerow(
                {"budget": budget, "L": search_l, **uniform[budget][search_l]}
            )


def load_selection(search_l: int, budget: int, selector: str) -> np.ndarray:
    return np.memmap(
        DATA / f"selectors/L{search_l}/{selector}_b{budget}.u8",
        dtype="u1",
        mode="r",
        shape=(N,),
    )


def jaccard(left: np.ndarray, right: np.ndarray) -> float:
    intersection = np.count_nonzero((left != 0) & (right != 0))
    union = np.count_nonzero((left != 0) | (right != 0))
    return float(intersection / union) if union else 1.0


within_l: list[dict[str, object]] = []
for budget in BUDGETS:
    for selector in SELECTORS:
        for left_l, right_l in itertools.combinations(LS, 2):
            within_l.append(
                {
                    "budget": budget,
                    "selector": selector,
                    "left_L": left_l,
                    "right_L": right_l,
                    "jaccard": jaccard(
                        load_selection(left_l, budget, selector),
                        load_selection(right_l, budget, selector),
                    ),
                }
            )

cross_selector: list[dict[str, object]] = []
for search_l in LS:
    for budget in BUDGETS:
        for left, right in itertools.combinations(
            ("visit_frequency", "distance_regret", "routing_aware"), 2
        ):
            cross_selector.append(
                {
                    "L": search_l,
                    "budget": budget,
                    "left_selector": left,
                    "right_selector": right,
                    "jaccard": jaccard(
                        load_selection(search_l, budget, left),
                        load_selection(search_l, budget, right),
                    ),
                }
            )

selector_reports = {
    str(search_l): json.loads((WORK / f"results/selector_L{search_l}.json").read_text())
    for search_l in LS
}

for filename, records in (
    ("within_selector_L_jaccard.csv", within_l),
    ("cross_selector_jaccard.csv", cross_selector),
):
    with (WORK / f"results/{filename}").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

score_rows: list[dict[str, object]] = []
coverage_rows: list[dict[str, object]] = []
for search_l in LS:
    report = selector_reports[str(search_l)]
    for selector, stats in report["score_distributions"].items():
        score_rows.append({"L": search_l, "selector": selector, **stats})
    for budget in BUDGETS:
        for selector, stats in report["selectors"][str(budget)].items():
            coverage_rows.append(
                {
                    "L": search_l,
                    "budget": budget,
                    "selector": selector,
                    "selected_nodes": stats["selected_nodes"],
                    "selected_trace_visits": stats["selected_trace_visits"],
                    "all_trace_visits": stats["all_trace_visits"],
                    "visit_coverage": stats["visit_coverage"],
                    "selected_unique_visited": stats["selected_unique_visited"],
                    "all_unique_visited": stats["all_unique_visited"],
                    "selected_score_sum": stats["selected_score_sum"],
                }
            )
for filename, records in (
    ("selector_score_distributions.csv", score_rows),
    ("selector_visit_coverage.csv", coverage_rows),
):
    with (WORK / f"results/{filename}").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

if positive_routing:
    verdict = [
        "PASS-ALGORITHMIC-SELECTIVITY-SIGNAL",
        "HOLD-STAGE-B-FOR-REVIEW",
    ]
elif positive_controls:
    verdict = ["HOLD-HOTNESS-ONLY", "HOLD-STAGE-B-FOR-REVIEW"]
else:
    verdict = ["KILL-TESTED-STATIC-SELECTORS-ON-GIST-A0"]

decision = {
    "experiment": "SELECTIVE-OPQ-ORACLE-A0-STAGE-A",
    "scope": [
        "GIST1M-960D",
        "frozen graph",
        "OPQ32/64",
        "tested per-L selectors",
    ],
    "system_claim_authorized": False,
    "stage_b_authorized": False,
    "verdict": verdict,
    "positive_routing_signals": positive_routing,
    "positive_control_signals": positive_controls,
    "within_selector_L_jaccard": within_l,
    "cross_selector_jaccard": cross_selector,
    "selector_reports": selector_reports,
}
(WORK / "results/decision.json").write_text(
    json.dumps(decision, indent=2, sort_keys=True) + "\n"
)
print(json.dumps({"verdict": verdict, "positive_routing": len(positive_routing)}, indent=2))
