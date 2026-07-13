#!/usr/bin/env python3
import argparse
import collections
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import analyze_c1_c2 as c12


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--ops", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--base-bytes", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = c12.load_trace(args.trace)
    train_ids, eval_ids = c12.workload_splits(rows, 711)["same_distribution"]
    topo, vec = c12.frequencies(rows, train_ids)
    score = collections.Counter()
    for node in set(topo) | set(vec):
        score[node] = 8 * min(topo[node], vec[node]) + topo[node] + vec[node]
    capacity = int(args.base_bytes * 0.10) // c12.COUPLED_RECORD
    selected = [node for node, _ in score.most_common(capacity)]
    capsule = c12.pack_coaccess(rows, train_ids, selected, score)
    capsule_count = max(capsule.values()) + 1
    base_page_to_capsules = collections.defaultdict(set)
    internal_to_tag = {}
    current_cp = None
    with args.layout.open() as source:
        for row in csv.DictReader(source):
            cp = int(row["checkpoint_percent"])
            internal = int(row["internal_id"])
            tag = int(row["tag"])
            if cp == 0 and internal in capsule:
                base_page_to_capsules[int(row["topology_location"]) // 15].add(capsule[internal])
            if cp == 20 and internal >= 900000:
                internal_to_tag[internal] = tag

    target_invalid_at = {}
    thresholds = [(1, 4500), (5, 22500), (10, 45000), (20, 90000)]
    with args.ops.open() as source:
        for row in csv.DictReader(source):
            op = int(row["op_id"])
            internal = int(row["target_id"])
            tag = internal_to_tag.get(internal)
            if tag in capsule:
                target_invalid_at.setdefault(capsule[tag], op)

    page_invalid_at = {}
    with args.events.open() as source:
        for row in csv.DictReader(source):
            if row["page_type"] != "topology" or row["event_type"] != "write":
                continue
            op = int(row["op_id"])
            for cap in base_page_to_capsules.get(int(row["page_id"]), ()):
                page_invalid_at.setdefault(cap, op)

    combined = dict(target_invalid_at)
    for cap, op in page_invalid_at.items():
        combined[cap] = min(combined.get(cap, op), op)

    original = [c12.original_query(rows[i]) for i in eval_ids]
    oracle = [c12.capsule_query(rows[i], capsule) for i in eval_ids]
    saved_bytes = 4096 * (sum(x[0] for x in original) - sum(x[0] for x in oracle)) / len(eval_ids)
    result = []
    for cp, limit in thresholds:
        target = sum(op < limit for op in target_invalid_at.values())
        pages = sum(op < limit for op in combined.values())
        rebuild = pages * 4096
        result.append({
            "checkpoint_percent": cp,
            "capsule_pages": capsule_count,
            "target_only_invalid_pages": target,
            "target_only_invalid_fraction": target / capsule_count,
            "target_plus_insert_page_invalid_pages": pages,
            "target_plus_insert_page_invalid_fraction": pages / capsule_count,
            "conservative_delete_scan_invalid_fraction": 1.0,
            "reason_conservative": "trigger_deletion rewrites every topology page at each checkpoint",
            "optimistic_rebuild_bytes": rebuild,
            "heldout_saved_bytes_per_query": saved_bytes,
            "optimistic_break_even_queries": rebuild / saved_bytes if saved_bytes > 0 else None,
        })
    payload = {
        "schema": "dgai-capsule-lifecycle-v1",
        "budget_fraction": 0.10,
        "selected_nodes": len(selected),
        "capsule_pages": capsule_count,
        "heldout_saved_bytes_per_query": saved_bytes,
        "bounds": result,
        "limitation": "delete neighbor-list logical modifications are not individually traced; target+insert-page is optimistic, full-page-version invalidation is conservative",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as target:
        json.dump(payload, target, indent=2, sort_keys=True)
        target.write("\n")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
