#!/usr/bin/env python3
"""Small-space oracle analysis for the VAQ semantic G0 gate.

This is exhaustive analysis over already executed configurations, not an
advisor.  It deliberately stops if a sequential frontier reaches the joint
semantic frontier.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


KEY = ["ann", "design", "effort"]
COMMON_COST = ["latency_ms", "index_bytes", "build_ms", "update_ms_per_vector"]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--run-root", type=Path,
                   default=Path("/home/ubuntu/pz/VectorDB/data/vaq_semantic_g0/runs/full"))
    return p.parse_args()


def frontier(df: pd.DataFrame, objectives: list[str]) -> pd.DataFrame:
    a = df[objectives].to_numpy(np.float64)
    keep = []
    for i, x in enumerate(a):
        dominated = np.all(a <= x, axis=1) & np.any(a < x, axis=1)
        dominated[i] = False
        if not dominated.any():
            keep.append(i)
    return df.iloc[keep].copy()


def keys(df: pd.DataFrame) -> set[tuple]:
    return set(map(tuple, df[KEY].itertuples(index=False, name=None)))


def json_keys(items: set[tuple]) -> list[list]:
    return [list(x) for x in sorted(items)]


def ci(values: np.ndarray, seed: int, rounds: int = 4000) -> list[float]:
    rng = np.random.default_rng(seed)
    ids = rng.integers(0, len(values), size=(rounds, len(values)))
    return np.quantile(values[ids].mean(axis=1), [.025, .975]).tolist()


def representative_pair(raw: pd.DataFrame, candidates: list[dict], seed: int) -> dict | None:
    if not candidates:
        return None
    pair = min(candidates, key=lambda x: (abs(x["recall_diff"]), -abs(x["error_diff"])))
    def split(label: str):
        design, effort = label.rsplit("@", 1)
        return design, int(effort)
    da, ea = split(pair["a"]); db, eb = split(pair["b"])
    a = raw[(raw.ann == pair["ann"]) & (raw.design == da) & (raw.effort == ea)]
    b = raw[(raw.ann == pair["ann"]) & (raw.design == db) & (raw.effort == eb)]
    m = a.merge(b, on="query_id", suffixes=("_a", "_b"))
    result = dict(pair)
    for metric in ["join_tuple_recall", "count_rel_error", "sum_rel_error",
                   "avg_rel_error", "fn_high_weight_share", "fn_group_hhi",
                   "top_group_rank_overlap", "returned"]:
        diff = (m[f"{metric}_a"] - m[f"{metric}_b"]).to_numpy()
        result[f"{metric}_a"] = float(m[f"{metric}_a"].mean())
        result[f"{metric}_b"] = float(m[f"{metric}_b"].mean())
        result[f"{metric}_diff_ci95"] = ci(diff, seed + len(metric))
    return result


def main():
    args = parse_args()
    matched = json.loads((args.run_root / "analysis.json").read_text())["qualifying_pairs"]
    output = {"definition": {
        "vector_local": COMMON_COST + ["1-local_recall"],
        "relational_local": COMMON_COST + ["candidate_count"],
        "sequential_v_to_r": "joint Pareto restricted to vector-local frontier",
        "sequential_r_to_v": "vector Pareto restricted to relational-local frontier, then joint Pareto",
        "joint_semantic": COMMON_COST + ["downstream_answer_error"],
        "dominance": "exact weak Pareto dominance; no hand-set scalar weights or SLO thresholds",
    }, "cases": [], "decision": None}
    v_to_r_reaches_all = True
    seed = 901
    for dataset in ["tpch_sift", "movielens"]:
        raw_all = pd.read_csv(args.run_root / dataset / "query_records.csv")
        summary = (raw_all.groupby(["query_family"] + KEY, as_index=False)
                   .agg(local_recall=("local_recall", "mean"),
                        downstream_error=("downstream_error", "mean"),
                        latency_ms=("latency_ms", "mean"),
                        index_bytes=("index_bytes", "first"), build_ms=("build_ms", "first"),
                        update_ms_per_vector=("update_ms_per_vector", "first"),
                        candidates=("candidates", "mean")))
        summary["recall_loss"] = 1.0-summary.local_recall
        for family, table in summary.groupby("query_family"):
            vf = frontier(table, COMMON_COST + ["recall_loss"])
            rf = frontier(table, COMMON_COST + ["candidates"])
            jf = frontier(table, COMMON_COST + ["downstream_error"])
            vtr = frontier(vf, COMMON_COST + ["downstream_error"])
            rtv0 = frontier(rf, COMMON_COST + ["recall_loss"])
            rtv = frontier(rtv0, COMMON_COST + ["downstream_error"])
            jk, vk, rk, vtrk, rtvk = map(keys, [jf, vf, rf, vtr, rtv])
            reaches = jk == vtrk
            v_to_r_reaches_all &= reaches
            evidence = [p for p in matched if p["dataset"] == dataset and
                        p["query_family"] == family]
            raw = raw_all[raw_all.query_family == family]
            case = {"dataset": dataset, "query_family": family,
                    "vector_local_frontier": json_keys(vk),
                    "relational_local_frontier": json_keys(rk),
                    "sequential_v_to_r_frontier": json_keys(vtrk),
                    "sequential_r_to_v_frontier": json_keys(rtvk),
                    "joint_semantic_frontier": json_keys(jk),
                    "joint_minus_v_to_r": json_keys(jk-vtrk),
                    "v_to_r_reaches_joint": reaches,
                    "representative_error_propagation_pair": representative_pair(raw, evidence, seed)}
            output["cases"].append(case); seed += 100
    output["all_v_to_r_frontiers_equal_joint"] = v_to_r_reaches_all
    output["decision"] = ("KILL_SEQUENTIAL_REACHES_JOINT_FRONTIER" if v_to_r_reaches_all
                          else "CONTINUE_FOR_HELDOUT_SIMPLE_RULE_TEST")
    path = args.run_root / "oracle_analysis.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"decision": output["decision"],
                      "cases": len(output["cases"]),
                      "all_v_to_r_frontiers_equal_joint": v_to_r_reaches_all}, indent=2))


if __name__ == "__main__":
    main()
