#!/usr/bin/env python3
"""P07 A0 post-hoc analysis of DiskANN expanded-node traces."""

import argparse
import array
import csv
import json
import math
import os
import statistics
import struct
from collections import Counter

SECTOR_LEN = 4096


def load_bin_header(path):
    with open(path, "rb") as f:
        raw = f.read(8)
    if len(raw) != 8:
        raise ValueError(f"short bin header: {path}")
    return struct.unpack("<II", raw)


def load_matrix_u32(path):
    nrows, dim = load_bin_header(path)
    vals = array.array("I")
    with open(path, "rb") as f:
        f.seek(8)
        vals.fromfile(f, nrows * dim)
    if vals.itemsize != 4:
        raise RuntimeError("unexpected uint32 size")
    if len(vals) != nrows * dim:
        raise ValueError(f"truncated uint32 matrix: {path}")
    return nrows, dim, vals


def load_gt_ids(path):
    nrows, dim = load_bin_header(path)
    ids = array.array("I")
    with open(path, "rb") as f:
        f.seek(8)
        ids.fromfile(f, nrows * dim)
    if len(ids) != nrows * dim:
        raise ValueError(f"truncated GT id matrix: {path}")
    expected = 8 + nrows * dim * 8
    if os.path.getsize(path) != expected:
        raise ValueError(
            f"GT size mismatch: got {os.path.getsize(path)}, expected {expected}"
        )
    return nrows, dim, ids


def parse_disk_metadata(path):
    with open(path, "rb") as f:
        nr, nc = struct.unpack("<II", f.read(8))
        if nc != 1 or nr < 8:
            raise ValueError(f"unexpected disk metadata shape {nr}x{nc}")
        vals = struct.unpack("<" + "Q" * nr, f.read(8 * nr))
    names = [
        "n_nodes",
        "dim",
        "medoid",
        "max_node_len",
        "nodes_per_sector",
        "frozen_count",
        "frozen_location",
        "has_reorder_data",
    ]
    meta = {name: vals[i] for i, name in enumerate(names)}
    meta["metadata_values"] = list(vals)
    meta["metadata_rows"] = nr
    meta["metadata_cols"] = nc
    meta["actual_file_size"] = os.path.getsize(path)
    meta["declared_file_size"] = vals[-1]
    nps = meta["nodes_per_sector"]
    if nps == 0:
        raise ValueError("multi-sector nodes are outside this A0 analyzer")
    data_sectors = math.ceil(meta["n_nodes"] / nps)
    dist = Counter()
    full, rem = divmod(meta["n_nodes"], nps)
    if full:
        dist[nps] += full
    if rem:
        dist[rem] += 1
    meta["data_sectors"] = data_sectors
    meta["total_sectors_including_metadata"] = data_sectors + 1
    meta["nodes_per_sector_distribution"] = dict(sorted(dist.items()))
    meta["used_bytes_per_full_sector"] = nps * meta["max_node_len"]
    meta["slack_bytes_per_full_sector"] = SECTOR_LEN - meta["used_bytes_per_full_sector"]
    return meta


def validate_disk_slots(path, meta, samples=1000):
    """Validate sampled implicit node slots by checking stored degree in [1,R]."""
    n = meta["n_nodes"]
    nps = meta["nodes_per_sector"]
    node_len = meta["max_node_len"]
    dim = meta["dim"]
    max_degree = (node_len - dim * 4) // 4 - 1
    ids = sorted({round(i * (n - 1) / (samples - 1)) for i in range(samples)})
    degrees = []
    with open(path, "rb") as f:
        for node_id in ids:
            sector = 1 + node_id // nps
            slot = node_id % nps
            offset = sector * SECTOR_LEN + slot * node_len + dim * 4
            f.seek(offset)
            raw = f.read(4)
            if len(raw) != 4:
                raise ValueError(f"short node slot for id {node_id}")
            degree = struct.unpack("<I", raw)[0]
            if not 1 <= degree <= max_degree:
                raise ValueError(f"invalid degree {degree} for node {node_id}")
            degrees.append(degree)
    return {
        "sampled_slots": len(ids),
        "min_degree": min(degrees),
        "max_degree": max(degrees),
        "mean_degree": statistics.fmean(degrees),
        "derived_max_degree": max_degree,
    }


def percentile(values, p):
    if not values:
        return 0.0
    vals = sorted(values)
    pos = (len(vals) - 1) * p
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(vals[lo])
    return vals[lo] * (hi - pos) + vals[hi] * (pos - lo)


def summary(values):
    return {
        "mean": statistics.fmean(values) if values else 0.0,
        "median": statistics.median(values) if values else 0.0,
        "p95": percentile(values, 0.95),
        "min": min(values) if values else 0.0,
        "max": max(values) if values else 0.0,
    }


def load_traces(path):
    traces = {}
    with open(path, newline="") as f:
        for lineno, row in enumerate(csv.reader(f), 1):
            if len(row) < 2:
                raise ValueError(f"empty trace at line {lineno}")
            qid = int(row[0])
            if qid in traces:
                raise ValueError(f"duplicate trace qid {qid}")
            traces[qid] = [int(x) for x in row[1:]]
    return traces


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--disk-index", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--queries", required=True)
    parser.add_argument("--gt", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--csv-out", required=True)
    args = parser.parse_args()

    meta = parse_disk_metadata(args.disk_index)
    slot_validation = validate_disk_slots(args.disk_index, meta)
    base_n, base_dim = load_bin_header(args.base)
    query_n, query_dim = load_bin_header(args.queries)
    gt_n, gt_k, gt_ids = load_gt_ids(args.gt)
    result_n, result_k, result_ids = load_matrix_u32(args.results)
    traces = load_traces(args.trace)

    checks = {
        "disk_nodes_equal_base_rows": meta["n_nodes"] == base_n,
        "disk_dim_equal_base_dim": meta["dim"] == base_dim,
        "query_dim_equal_base_dim": query_dim == base_dim,
        "gt_rows_equal_queries": gt_n == query_n,
        "results_rows_equal_queries": result_n == query_n,
        "trace_qids_exact_query_order": sorted(traces) == list(range(query_n)),
        "trace_all_nonempty": all(traces.get(i) for i in range(query_n)),
        "disk_file_size_matches_declared": meta["actual_file_size"] == meta["declared_file_size"],
        "disk_file_sector_count_matches": meta["actual_file_size"]
        == meta["total_sectors_including_metadata"] * SECTOR_LEN,
        "gt_has_at_least_100": gt_k >= 100,
    }
    if not all(checks.values()):
        raise ValueError(f"verification failed: {checks}")

    nps = meta["nodes_per_sector"]
    n_nodes = meta["n_nodes"]
    per_query = []
    total_bonus = total_gt = total_later = total_final = 0
    total_reads = total_avoidable = total_unique_sectors = 0
    total_exposures = 0
    total_result_gt100_hits = total_result_exactk_hits = 0

    for qid in range(query_n):
        expanded = traces[qid]
        if len(set(expanded)) != len(expanded):
            raise ValueError(f"query {qid} has duplicate expanded node ids")
        if min(expanded) < 0 or max(expanded) >= n_nodes:
            raise ValueError(f"query {qid} has out-of-range node id")
        expanded_pos = {node: pos for pos, node in enumerate(expanded)}
        gt = set(gt_ids[qid * gt_k : qid * gt_k + 100])
        gt_final_k = set(gt_ids[qid * gt_k : qid * gt_k + result_k])
        final = set(result_ids[qid * result_k : (qid + 1) * result_k])
        total_result_gt100_hits += len(final & gt)
        total_result_exactk_hits += len(final & gt_final_k)

        # Map every co-resident node to the first step where it was available
        # for free, excluding nodes already explicitly expanded by then.
        first_bonus_step = {}
        expanded_so_far = set()
        exposure_count = 0
        for step, requested in enumerate(expanded):
            sector = requested // nps
            start = sector * nps
            stop = min(start + nps, n_nodes)
            for node in range(start, stop):
                if node == requested or node in expanded_so_far:
                    continue
                exposure_count += 1
                first_bonus_step.setdefault(node, step)
            expanded_so_far.add(requested)

        bonus = set(first_bonus_step)
        in_gt = bonus & gt
        in_final = bonus & final
        later = {
            node
            for node, first_step in first_bonus_step.items()
            if node in expanded_pos and expanded_pos[node] > first_step
        }
        sectors = {node // nps for node in expanded}
        reads = len(expanded)
        avoidable = len(later)
        row = {
            "query_id": qid,
            "expanded_reads": reads,
            "unique_sectors": len(sectors),
            "baseline_sector_rereads": reads - len(sectors),
            "bonus_exposures": exposure_count,
            "unique_bonus_nodes": len(bonus),
            "bonus_in_gt100": len(in_gt),
            "bonus_visited_later": len(later),
            "bonus_in_final_topk": len(in_final),
            "bonus_gt100_fraction": len(in_gt) / len(bonus) if bonus else 0.0,
            "bonus_later_fraction": len(later) / len(bonus) if bonus else 0.0,
            "bonus_final_fraction": len(in_final) / len(bonus) if bonus else 0.0,
            "estimated_avoidable_reads": avoidable,
            "estimated_io_savings_fraction": avoidable / reads if reads else 0.0,
        }
        per_query.append(row)
        total_bonus += len(bonus)
        total_gt += len(in_gt)
        total_later += len(later)
        total_final += len(in_final)
        total_reads += reads
        total_avoidable += avoidable
        total_unique_sectors += len(sectors)
        total_exposures += exposure_count

    metric_keys = [
        "expanded_reads",
        "unique_sectors",
        "baseline_sector_rereads",
        "bonus_exposures",
        "unique_bonus_nodes",
        "bonus_in_gt100",
        "bonus_visited_later",
        "bonus_in_final_topk",
        "bonus_gt100_fraction",
        "bonus_later_fraction",
        "bonus_final_fraction",
        "estimated_avoidable_reads",
        "estimated_io_savings_fraction",
    ]
    per_query_summary = {
        key: summary([row[key] for row in per_query]) for key in metric_keys
    }

    gt_counts = sorted((r["bonus_in_gt100"] for r in per_query), reverse=True)
    later_counts = sorted((r["bonus_visited_later"] for r in per_query), reverse=True)
    top10n = max(1, math.ceil(query_n * 0.10))
    concentration = {
        "queries_with_zero_gt100_bonus": sum(r["bonus_in_gt100"] == 0 for r in per_query),
        "queries_with_zero_later_bonus": sum(r["bonus_visited_later"] == 0 for r in per_query),
        "top_10pct_query_share_of_gt100_hits": sum(gt_counts[:top10n]) / total_gt if total_gt else 0.0,
        "top_10pct_query_share_of_later_hits": sum(later_counts[:top10n]) / total_later if total_later else 0.0,
    }

    aggregate = {
        "query_count": query_n,
        "gt_k": gt_k,
        "final_k": result_k,
        "total_expanded_reads": total_reads,
        "total_unique_sectors": total_unique_sectors,
        "total_bonus_exposures": total_exposures,
        "total_unique_bonus_nodes_per_query_sum": total_bonus,
        "bonus_in_gt100": total_gt,
        "bonus_visited_later": total_later,
        "bonus_in_final_topk": total_final,
        "bonus_in_gt100_fraction": total_gt / total_bonus,
        "bonus_visited_later_fraction": total_later / total_bonus,
        "bonus_in_final_topk_fraction": total_final / total_bonus,
        "estimated_avoidable_reads": total_avoidable,
        "estimated_io_savings_fraction": total_avoidable / total_reads,
        "baseline_same_sector_reread_fraction": (total_reads - total_unique_sectors) / total_reads,
        "search_final_topk_fraction_in_gt100": total_result_gt100_hits / (query_n * result_k),
        "search_recall_at_final_k": total_result_exactk_hits / (query_n * result_k),
    }

    output = {
        "disk_layout": meta,
        "slot_validation": slot_validation,
        "verification": checks,
        "aggregate": aggregate,
        "per_query_summary": per_query_summary,
        "utility_concentration": concentration,
    }
    with open(args.json_out, "w") as f:
        json.dump(output, f, indent=2, sort_keys=True)
        f.write("\n")
    with open(args.csv_out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(per_query[0]))
        writer.writeheader()
        writer.writerows(per_query)
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
