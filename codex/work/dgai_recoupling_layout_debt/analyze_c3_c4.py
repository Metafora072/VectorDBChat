#!/usr/bin/env python3
"""Analyze DGAI layout debt and same-graph maintenance baselines."""

import argparse
import bisect
import collections
import csv
import json
import struct
from pathlib import Path

TOPO_CAP = 15
VECTOR_CAP = 8
PAGE = 4096
TOPO_RECORD = 260


def pct(values, q):
    values = sorted(values)
    return values[int(q * (len(values) - 1))] if values else 0.0


def uniq(values):
    return set(values)


def load_traces(path):
    result = collections.defaultdict(list)
    with path.open() as source:
        for line in source:
            row = json.loads(line)
            result[row["checkpoint_percent"]].append(row)
    return result


def coaccess_pack(rows, field, capacity):
    mapping = {}
    page = 0
    for row in sorted(rows, key=lambda r: len(set(r[field])), reverse=True):
        remaining = [n for n in dict.fromkeys(row[field]) if n not in mapping]
        for start in range(0, len(remaining), capacity):
            for node in remaining[start:start + capacity]:
                mapping[node] = page
            page += 1
    return mapping


def graph_pack(graph_path, meta, nodes):
    by_page = collections.defaultdict(list)
    for node in nodes:
        loc = meta[node][1]
        by_page[loc // TOPO_CAP].append((node, loc % TOPO_CAP))
    adjacency = {}
    with graph_path.open("rb") as source:
        for page, entries in by_page.items():
            source.seek(page * PAGE)
            data = source.read(PAGE)
            for node, slot in entries:
                offset = slot * TOPO_RECORD
                degree = min(struct.unpack_from("<I", data, offset)[0], 64)
                neighbors = struct.unpack_from("<" + "I" * degree, data, offset + 4) if degree else ()
                adjacency[node] = [n for n in neighbors if n in nodes]
    order = []
    seen = set()
    for root in sorted(nodes, key=lambda n: (-len(adjacency.get(n, ())), n)):
        if root in seen:
            continue
        queue = collections.deque([root])
        seen.add(root)
        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in adjacency.get(node, ()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
    return {node: pos // TOPO_CAP for pos, node in enumerate(order)}


def summarize(method, checkpoint, rows, pages, modeled_latency, scope):
    recall = [r["recall_at_10"] for r in rows]
    actual_latency = [r["latency_us"] for r in rows]
    return {
        "checkpoint_percent": checkpoint,
        "method": method,
        "scope": scope,
        "queries": len(rows),
        "mean_pages": sum(pages) / len(pages),
        "p50_pages": pct(pages, 0.50),
        "p95_pages": pct(pages, 0.95),
        "p99_pages": pct(pages, 0.99),
        "mean_recall_at_10": sum(recall) / len(recall),
        "actual_p50_latency_us": pct(actual_latency, 0.50) if method == "M0_current" else "",
        "actual_p95_latency_us": pct(actual_latency, 0.95) if method == "M0_current" else "",
        "actual_p99_latency_us": pct(actual_latency, 0.99) if method == "M0_current" else "",
        "modeled_p50_latency_us": pct(modeled_latency, 0.50),
        "modeled_p95_latency_us": pct(modeled_latency, 0.95),
        "modeled_p99_latency_us": pct(modeled_latency, 0.99),
    }


def occupancy(checkpoint, store, locations, capacity):
    counts = collections.Counter(loc // capacity for loc in locations)
    values = list(counts.values())
    return {
        "checkpoint_percent": checkpoint,
        "store": store,
        "active_records": len(locations),
        "used_pages": len(values),
        "mean_occupancy": sum(values) / (len(values) * capacity),
        "p10_occupancy": pct([v / capacity for v in values], 0.10),
        "under_half_page_fraction": sum(v < capacity / 2 for v in values) / len(values),
        "max_location": max(locations),
    }


def analyze_checkpoint(checkpoint, active, traces, base_topo, base_vec, graph_path):
    rows_all = traces[checkpoint]
    rows = [r for r in rows_all if r["qid"] >= 600]
    needed = set()
    for row in rows_all:
        needed.update(row["topology_nodes"])
        needed.update(row["rerank_nodes"])
    meta = {}
    topo_locs, vec_locs = [], []
    for internal, tag, topo_loc, vec_loc in active:
        topo_locs.append(topo_loc)
        vec_locs.append(vec_loc)
        if internal in needed:
            meta[internal] = (tag, topo_loc, vec_loc)
    topo_sorted = sorted(topo_locs)
    vec_sorted = sorted(vec_locs)

    actual = []
    fresh = []
    compact = []
    for row in rows:
        actual.append(len(uniq(row["topology_pages"])) + len(uniq(row["rerank_pages"])))
        fresh_topo = {base_topo[meta[n][0]] // TOPO_CAP for n in row["topology_nodes"]}
        fresh_vec = {base_vec[meta[n][0]] // VECTOR_CAP for n in row["rerank_nodes"]}
        fresh.append(len(fresh_topo) + len(fresh_vec))
        compact_topo = {bisect.bisect_left(topo_sorted, meta[n][1]) // TOPO_CAP for n in row["topology_nodes"]}
        compact_vec = {bisect.bisect_left(vec_sorted, meta[n][2]) // VECTOR_CAP for n in row["rerank_nodes"]}
        compact.append(len(compact_topo) + len(compact_vec))

    xs = [len(uniq(r["topology_pages"])) + len(uniq(r["rerank_pages"])) for r in rows_all]
    ys = [r["latency_us"] for r in rows_all]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom if denom else 0.0
    actual_lats = [r["latency_us"] for r in rows]
    modeled = lambda pages: [max(0.0, latency + slope * (new - old))
                             for latency, new, old in zip(actual_lats, pages, actual)]

    summaries = [
        summarize("M0_current", checkpoint, rows, actual, actual_lats, "actual same-process query"),
        summarize("M1_fresh_initial_layout_same_graph", checkpoint, rows, fresh, modeled(fresh),
                  "same logical query path; restored initial tag layout"),
        summarize("M2_occupancy_compaction", checkpoint, rows, compact, modeled(compact),
                  "same logical query path; physical order preserved, holes removed"),
    ]

    if checkpoint in (0, 20):
        eval_topo = set(n for row in rows for n in row["topology_nodes"])
        adjacency_map = graph_pack(graph_path, meta, eval_topo)
        oracle_topo = coaccess_pack(rows, "topology_nodes", TOPO_CAP)
        oracle_vec = coaccess_pack(rows, "rerank_nodes", VECTOR_CAP)
        adjacency_pages, oracle_pages = [], []
        for row in rows:
            adj_topo = {adjacency_map[n] for n in row["topology_nodes"]}
            cmp_vec = {bisect.bisect_left(vec_sorted, meta[n][2]) // VECTOR_CAP for n in row["rerank_nodes"]}
            adjacency_pages.append(len(adj_topo) + len(cmp_vec))
            oracle_pages.append(len({oracle_topo[n] for n in row["topology_nodes"]}) +
                                len({oracle_vec[n] for n in row["rerank_nodes"]}))
        m4 = summarize("M4_future_heldout_coaccess_oracle", checkpoint, rows, oracle_pages,
                       [0.0] * len(rows), "unattainable upper bound learned on evaluation requests; latency not modeled")
        m4["modeled_p50_latency_us"] = ""
        m4["modeled_p95_latency_us"] = ""
        m4["modeled_p99_latency_us"] = ""
        summaries.extend([
            summarize("M3_graph_adjacency_colocation", checkpoint, rows, adjacency_pages,
                      modeled(adjacency_pages), "same graph; induced adjacency BFS + compact vectors"),
            m4,
        ])

    return summaries, [occupancy(checkpoint, "topology", topo_locs, TOPO_CAP),
                       occupancy(checkpoint, "vector", vec_locs, VECTOR_CAP)], slope


def write_csv(path, rows):
    fields = list(rows[0])
    with path.open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def analyze_updates(path, output):
    ranges = [(1, 4500), (5, 22500), (10, 45000), (20, 90000)]
    groups = {cp: [] for cp, _ in ranges}
    with path.open() as source:
        for row in csv.DictReader(source):
            op = int(row["op_id"])
            for cp, limit in ranges:
                if op < limit:
                    groups[cp].append(row)
                    break
    result = []
    previous = 0
    scan1 = {1: 4381, 5: 16034, 10: 19571, 20: 34270}
    scan2 = {1: 77355, 5: 77356, 10: 77356, 20: 77356}
    for cp, limit in ranges:
        rows = groups[cp]
        writes = [int(r["host_total_update_bytes"]) for r in rows]
        lat = [int(r["latency_us"]) for r in rows]
        result.append({
            "checkpoint_percent": cp,
            "new_insert_ops": limit - previous,
            "insert_total_host_io_bytes": sum(writes),
            "insert_p50_latency_us": pct(lat, 0.50),
            "insert_p95_latency_us": pct(lat, 0.95),
            "delete_scan_read_bytes": (scan1[cp] + scan2[cp]) * PAGE,
            "delete_scan_write_bytes": scan2[cp] * PAGE,
            "delete_scan_source": "runtime console counters",
        })
        previous = limit
    write_csv(output, result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--initial-graph", type=Path, required=True)
    parser.add_argument("--rmw-ops", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    traces = load_traces(args.trace)
    base_topo = [-1] * 900000
    base_vec = [-1] * 900000
    summaries, occupancies, slopes = [], [], {}

    current_cp = None
    active = []
    with args.layout.open() as source:
        reader = csv.DictReader(source)
        for row in reader:
            cp = int(row["checkpoint_percent"])
            if current_cp is not None and cp != current_cp:
                if current_cp == 0:
                    for _, tag, topo, vec in active:
                        base_topo[tag], base_vec[tag] = topo, vec
                graph = args.initial_graph if current_cp == 0 else args.graph
                s, o, slope = analyze_checkpoint(current_cp, active, traces, base_topo, base_vec, graph)
                summaries.extend(s); occupancies.extend(o); slopes[current_cp] = slope
                active = []
            current_cp = cp
            active.append((int(row["internal_id"]), int(row["tag"]),
                           int(row["topology_location"]), int(row["vector_location"])))
    if current_cp == 0:
        for _, tag, topo, vec in active:
            base_topo[tag], base_vec[tag] = topo, vec
    s, o, slope = analyze_checkpoint(current_cp, active, traces, base_topo, base_vec, args.graph)
    summaries.extend(s); occupancies.extend(o); slopes[current_cp] = slope

    write_csv(args.output_dir / "c3_c4_layout_summary.csv", summaries)
    write_csv(args.output_dir / "c3_occupancy.csv", occupancies)
    updates = analyze_updates(args.rmw_ops, args.output_dir / "c3_update_cost.csv")
    report = {
        "schema": "dgai-c3-c4-characterization-v1",
        "checkpoints": sorted(traces),
        "heldout_rule": "qid >= 600 within each 1000-query checkpoint",
        "latency_model": "per-checkpoint linear delta from actual latency versus actual page count",
        "latency_slopes_us_per_page": slopes,
        "same_graph_recall": "identical by construction for M1-M4; query node sequences are fixed",
        "layout_summary": str(args.output_dir / "c3_c4_layout_summary.csv"),
        "occupancy_summary": str(args.output_dir / "c3_occupancy.csv"),
        "update_summary": str(args.output_dir / "c3_update_cost.csv"),
        "update_rows": updates,
    }
    with (args.output_dir / "c3_c4_characterization.json").open("w") as target:
        json.dump(report, target, indent=2, sort_keys=True)
        target.write("\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
