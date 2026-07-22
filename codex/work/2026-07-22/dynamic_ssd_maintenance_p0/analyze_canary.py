#!/usr/bin/env python3
"""Reduce corrective-canary JSONL into the registered gate decision."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load(name):
    with (ROOT / "results" / name).open(encoding="utf-8") as src:
        return [json.loads(line) for line in src if line.strip()]


def pct(value, baseline):
    return 100.0 * (value / baseline - 1.0)


layout = load("layout_aging.jsonl")
writes = load("write_path.jsonl")
deletion = load("deletion_cost.jsonl")

search_a = {r["label"]: r for r in layout if r["record"] == "search" and not r["label"].startswith("sanity")}
update_b = {r["label"]: r for r in writes if r["record"] == "update"}
search_c = {(r["label"], r["phase"]): r for r in deletion if r["record"] == "search"}
merge_c = next(r for r in deletion if r["record"] == "merge")

s0 = search_a["S0_static"]
layout_delta = {}
for label in ("S1_insert", "S2_churn", "S3_rebuild"):
    row = search_a[label]
    layout_delta[label] = {
        "visited_nodes_pct_vs_s0": pct(row["visited_nodes_mean"], s0["visited_nodes_mean"]),
        "distinct_pages_pct_vs_s0": pct(row["distinct_pages_mean"], s0["distinct_pages_mean"]),
        "page_accesses_pct_vs_s0": pct(row["page_accesses_mean"], s0["page_accesses_mean"]),
        "nodes_per_page_pct_vs_s0": pct(row["nodes_per_page_mean"], s0["nodes_per_page_mean"]),
    }

stable_visited = all(abs(layout_delta[x]["visited_nodes_pct_vs_s0"]) < 5.0 for x in ("S1_insert", "S2_churn"))
page_increase = any(layout_delta[x]["distinct_pages_pct_vs_s0"] > 10.0 for x in ("S1_insert", "S2_churn"))
rebuild_near_s0 = abs(layout_delta["S3_rebuild"]["distinct_pages_pct_vs_s0"]) < 5.0
pass_layout = stable_visited and page_increase and rebuild_near_s0

write_comparison = {}
for count in (1000, 10000):
    cow = update_b[f"B_COW_{count // 1000}K"]
    inplace = update_b[f"B_INPLACE_{count // 1000}K"]
    write_comparison[str(count)] = {
        "cow_write_bytes": cow["proc_write_bytes"],
        "inplace_write_bytes": inplace["proc_write_bytes"],
        "inplace_over_cow_actual_bytes": inplace["proc_write_bytes"] / cow["proc_write_bytes"],
        "cow_bytes_per_insert": cow["proc_write_bytes"] / count,
        "inplace_bytes_per_insert": inplace["proc_write_bytes"] / count,
        "cow_distinct_dirty_pages": cow["distinct_dirty_pages"],
        "inplace_distinct_dirty_pages": inplace["distinct_dirty_pages"],
        "cow_repeat_touches": cow["repeat_write_touches"],
        "inplace_repeat_touches": inplace["repeat_write_touches"],
        "cow_wall_seconds": cow["wall_seconds"],
        "inplace_wall_seconds": inplace["wall_seconds"],
    }

c0 = search_c[("C_TOMBSTONE_0", "pre_merge")]
tombstone = {}
for level, label in ((0.05, "C_TOMBSTONE_5"), (0.10, "C_TOMBSTONE_10")):
    row = search_c[(label, "pre_merge")]
    tombstone[label] = {
        "deleted_visit_fraction": row["deleted_visit_fraction"],
        "enrichment_over_uniform_fraction": row["deleted_visit_fraction"] / level,
        "distinct_pages_pct_vs_0": pct(row["distinct_pages_mean"], c0["distinct_pages_mean"]),
        "visited_nodes_pct_vs_0": pct(row["visited_nodes_mean"], c0["visited_nodes_mean"]),
        "latency_p50_pct_vs_0": pct(row["latency_p50_us"], c0["latency_p50_us"]),
    }

pre = search_c[("C_MERGE_10", "pre_merge")]
post = search_c[("C_MERGE_10", "post_merge")]
merge_summary = {
    **merge_c,
    "distinct_pages_pct_post_vs_pre": pct(post["distinct_pages_mean"], pre["distinct_pages_mean"]),
    "latency_p50_pct_post_vs_pre": pct(post["latency_p50_us"], pre["latency_p50_us"]),
    "recall_delta_pp": 100.0 * (post["recall_at_10"] - pre["recall_at_10"]),
}

# Q3 offers no page-local signal: deleted expansions are near the uniform delete
# rate and distinct pages do not increase. Q1 alone is explicitly barred from
# founding a project, so failure of Q2 and Q3 implies the registered KILL.
page_local_signal = any(v["enrichment_over_uniform_fraction"] >= 1.5 for v in tombstone.values()) and any(
    v["distinct_pages_pct_vs_0"] > 10.0 for v in tombstone.values()
)
verdict = "PASS-L-PHYSICAL-AGING" if pass_layout else (
    "PASS-D-PAGE-LOCAL-OPPORTUNITY" if page_local_signal else "KILL-DYNAMIC-SSD-MAINTENANCE"
)

summary = {
    "schema_version": 1,
    "verdict": verdict,
    "layout_gate": {
        "stable_visited_lt_5pct": stable_visited,
        "distinct_pages_increase_gt_10pct": page_increase,
        "rebuild_within_5pct_of_s0": rebuild_near_s0,
        "pass": pass_layout,
        "deltas": layout_delta,
    },
    "write_path": write_comparison,
    "tombstone": tombstone,
    "page_local_signal": page_local_signal,
    "merge": merge_summary,
    "raw_files": ["layout_aging.jsonl", "write_path.jsonl", "deletion_cost.jsonl"],
}

with (ROOT / "results" / "summary.json").open("w", encoding="utf-8") as dst:
    json.dump(summary, dst, indent=2, sort_keys=True)
    dst.write("\n")

print(json.dumps(summary, indent=2, sort_keys=True))
