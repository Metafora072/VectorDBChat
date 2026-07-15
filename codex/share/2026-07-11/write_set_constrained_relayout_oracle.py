#!/usr/bin/env python3
"""Offline, measurement-only oracle gate for write-set-constrained relayout."""

import argparse
import collections
import csv
import json
import math
import random
import struct
from pathlib import Path


N = 900_000
R = 64


def load_gt(path, topk=10):
    with open(path, "rb") as f:
        nq, k = struct.unpack("<II", f.read(8))
        ids = struct.unpack(f"<{nq * k}I", f.read(4 * nq * k))
    return [tuple(x for x in ids[i * k:i * k + topk] if x < N) for i in range(nq)]


class DGAI:
    name = "DGAI"
    capacity = 15

    def __init__(self, root):
        root = Path(root)
        with open(root / "reorder_map_graph_2", "rb") as f:
            n, _ = struct.unpack("<II", f.read(8))
            assert n == N
            self.loc = struct.unpack(f"<{n}I", f.read(4 * n))
        self.graph_path = root / "reordered_disk_index_graph_2"
        self.pages = [x // self.capacity for x in self.loc]
        self.page_records = collections.defaultdict(list)
        for node, page in enumerate(self.pages):
            self.page_records[page].append(node)

    def neighbors(self, node, limit=32):
        loc = self.loc[node]
        off = (loc // self.capacity) * 4096 + (loc % self.capacity) * 260
        with open(self.graph_path, "rb") as f:
            f.seek(off)
            row = struct.unpack("<65I", f.read(260))
        return tuple(x for x in row[1:1 + min(row[0], limit)] if x < N)


class Odin:
    name = "OdinANN"

    def __init__(self, path):
        self.path = Path(path)
        with open(path, "rb") as f:
            nr, nc = struct.unpack("<II", f.read(8))
            meta = struct.unpack("<9Q", f.read(72))
        assert (nr, nc, meta[0], meta[1]) == (9, 1, N, 128)
        self.node_len = meta[3]
        self.capacity = meta[4]
        self.pages = [1 + i // self.capacity for i in range(N)]

    def neighbors(self, node, limit=32):
        off = 4096 + (node // self.capacity) * 4096 + (node % self.capacity) * self.node_len + 512
        with open(self.path, "rb") as f:
            f.seek(off)
            nnbrs, _ = struct.unpack("<HH", f.read(4))
            row = struct.unpack(f"<{nnbrs}I", f.read(4 * nnbrs))
        return tuple(x for x in row[:limit] if x < N)


def page_reads(queries, placement):
    return sum(len({placement[x] for x in q}) for q in queries)


def relevant_queries(queries, records):
    wanted = set(records)
    return [q for q in queries if wanted.intersection(q)]


def greedy_partition(records, capacities, queries, adjacency=None):
    records = list(dict.fromkeys(records))
    weights = collections.Counter()
    rset = set(records)
    for q in queries:
        hit = [x for x in q if x in rset]
        for i, a in enumerate(hit):
            for b in hit[i + 1:]:
                weights[min(a, b), max(a, b)] += 1
    if adjacency is not None:
        for a in records:
            for b in adjacency.get(a, ()):
                if b in rset and a != b:
                    weights[min(a, b), max(a, b)] += 1
    degree = {x: 0 for x in records}
    for (a, b), w in weights.items():
        degree[a] += w
        degree[b] += w
    remaining = set(records)
    groups = []
    for cap in capacities:
        if not remaining:
            groups.append([])
            continue
        seed = max(remaining, key=lambda x: (degree[x], -x))
        group = [seed]
        remaining.remove(seed)
        while remaining and len(group) < cap:
            nxt = max(remaining, key=lambda x: (sum(weights[min(x, y), max(x, y)] for y in group), degree[x], -x))
            group.append(nxt)
            remaining.remove(nxt)
        groups.append(group)
    return groups


def apply_groups(base, groups, page_ids):
    out = dict(base)
    for page, group in zip(page_ids, groups):
        for node in group:
            out[node] = page
    return out


def select_anchors(hist, future, count, mode, seed):
    rng = random.Random(seed)
    hf = collections.Counter(x for q in hist for x in q)
    ff = collections.Counter(x for q in future for x in q)
    if mode == "aligned":
        pool = [x for x, _ in (hf + ff).most_common(20_000) if hf[x] and ff[x]]
    elif mode == "query_hot_update_cold":
        hot = set(hf) | set(ff)
        pool = [x for x in range(N) if x not in hot]
        rng.shuffle(pool)
        pool = pool[:20_000]
    elif mode == "query_cold_update_hot":
        pool = [x for x, _ in hf.most_common(20_000) if ff[x] == 0]
    else:  # phase_shift
        pool = [x for x, _ in hf.most_common(30_000) if hf[x] >= ff[x]]
    if len(pool) < count:
        pool = [x for x, _ in hf.most_common(50_000)]
    rng.shuffle(pool)
    return pool[:count]


def dgai_event(sys, anchor, hist, future):
    nbrs = sys.neighbors(anchor, 64)
    wpages = sorted({sys.pages[x] for x in nbrs})
    candidates = [p for p in wpages if len(sys.page_records[p]) < sys.capacity]
    if not candidates:
        return None
    # Existing anchor stands in for the arriving semantically equivalent target.
    base = {x: sys.pages[x] for q in (hist + future) for x in q}
    base[anchor] = candidates[0]
    fq = relevant_queries(future, [anchor])
    hq = relevant_queries(hist, [anchor])
    if not fq:
        return {"native": 0, "graph": 0, "historical": 0, "strict": 0, "swap_upper": 0,
                "global_headroom": 0, "effective": 0, "candidates": len(candidates),
                "strict_moves": 1, "swap_extra_moves": sum(len(sys.page_records[p]) for p in wpages),
                "W_pages": len(wpages), "write_bytes": len(wpages) * 4096}
    native = page_reads(fq, base)
    graph_page = max(candidates, key=lambda p: sum(sys.pages[x] == p for x in nbrs))
    graph = page_reads(fq, {**base, anchor: graph_page})
    hist_page = min(candidates, key=lambda p: page_reads(hq, {**base, anchor: p})) if hq else graph_page
    historical = page_reads(fq, {**base, anchor: hist_page})
    strict_page = min(candidates, key=lambda p: page_reads(fq, {**base, anchor: p}))
    strict = page_reads(fq, {**base, anchor: strict_page})
    residents = set().union(*(sys.page_records[p] for p in wpages))
    # Optimistic dirty-page bound; deliberately ignores cross-query conflicts.
    swap_lb = 0
    for q in fq:
        outside = {base[x] for x in q if x not in residents and x != anchor}
        inside = sum(x in residents or x == anchor for x in q)
        swap_lb += len(outside) + math.ceil(inside / sys.capacity)
    global_lb = sum(math.ceil(len(q) / sys.capacity) for q in fq)
    return {"native": native, "graph": graph, "historical": historical, "strict": strict,
            "swap_upper": swap_lb, "global_headroom": global_lb, "effective": int(strict < native),
            "candidates": len(candidates), "strict_moves": 1,
            "swap_extra_moves": len(residents), "W_pages": len(wpages),
            "write_bytes": len(wpages) * 4096}


def odin_event(sys, anchor, hist, future):
    moved = [anchor] + list(sys.neighbors(anchor, 32))
    moved = list(dict.fromkeys(moved))
    capacities = [sys.capacity] * math.ceil(len(moved) / sys.capacity)
    capacities[-1] = len(moved) - sum(capacities[:-1])
    page_ids = list(range(N + 1, N + 1 + len(capacities)))
    base = {x: sys.pages[x] for q in (hist + future) for x in q}
    native_groups = [moved[i:i + sys.capacity] for i in range(0, len(moved), sys.capacity)]
    native_map = apply_groups(base, native_groups, page_ids)
    fq = relevant_queries(future, moved)
    hq = relevant_queries(hist, moved)
    if not fq:
        return {"native": 0, "graph": 0, "historical": 0, "strict": 0, "swap_upper": 0,
                "global_headroom": 0, "effective": 0, "candidates": len(page_ids),
                "strict_moves": len(moved), "swap_extra_moves": 0,
                "W_pages": len(page_ids), "write_bytes": len(page_ids) * 4096}
    native = page_reads(fq, native_map)
    adj = {x: sys.neighbors(x, 32) for x in moved}
    graph_groups = greedy_partition(moved, capacities, [], adjacency=adj)
    hist_groups = greedy_partition(moved, capacities, hq)
    strict_groups = greedy_partition(moved, capacities, fq)
    graph = page_reads(fq, apply_groups(base, graph_groups, page_ids))
    historical = page_reads(fq, apply_groups(base, hist_groups, page_ids))
    strict = page_reads(fq, apply_groups(base, strict_groups, page_ids))
    global_lb = sum(math.ceil(len(q) / sys.capacity) for q in fq)
    return {"native": native, "graph": graph, "historical": historical, "strict": strict,
            "swap_upper": strict, "global_headroom": global_lb, "effective": int(strict < native),
            "candidates": len(page_ids), "strict_moves": len(moved), "swap_extra_moves": 0,
            "W_pages": len(page_ids), "write_bytes": len(page_ids) * 4096}


def aggregate(rows):
    out = {"events": len(rows)}
    for k in rows[0]:
        vals = [r[k] for r in rows]
        out[k] = {"sum": sum(vals), "mean": sum(vals) / len(vals), "median": sorted(vals)[len(vals) // 2]}
    native = out["native"]["sum"]
    for k in ("graph", "historical", "strict", "swap_upper", "global_headroom"):
        out[k]["saved_vs_native"] = native - out[k]["sum"]
    denom = native - out["global_headroom"]["sum"]
    out["strict_recovery_of_global"] = ((native - out["strict"]["sum"]) / denom) if denom > 0 else 0
    rng = random.Random(20260712)
    for method in ("graph", "historical", "strict", "swap_upper"):
        savings = [r["native"] - r[method] for r in rows]
        boots = []
        for _ in range(2000):
            boots.append(sum(savings[rng.randrange(len(savings))] for _ in savings) / len(savings))
        boots.sort()
        out[method]["mean_saved_pages_per_event"] = sum(savings) / len(savings)
        out[method]["mean_saved_pages_ci95"] = [boots[49], boots[1949]]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dgai-root", required=True)
    ap.add_argument("--odin-index", required=True)
    ap.add_argument("--groundtruth", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--events", type=int, default=40)
    args = ap.parse_args()
    queries = load_gt(args.groundtruth)
    even, odd = queries[::2], queries[1::2]
    early_hot = set(x for q in even[:500] for x in q)
    scenarios = {
        "aligned": (even, odd),
        "query_hot_update_cold": (even, odd),
        "query_cold_update_hot": (even, [q for q in odd if not set(q).intersection(early_hot)]),
        "phase_shift": (queries[:5000], queries[5000:]),
    }
    systems = [DGAI(args.dgai_root), Odin(args.odin_index)]
    result = {"protocol": {"events_per_system_scenario": args.events, "query_topk": 10,
                           "page_bytes": 4096, "npoints": N, "R": R}, "systems": {}}
    for sys in systems:
        result["systems"][sys.name] = {}
        for idx, (mode, (hist, future)) in enumerate(scenarios.items()):
            anchors = select_anchors(hist, future, args.events, mode, 20260712 + idx)
            rows = []
            for anchor in anchors:
                row = dgai_event(sys, anchor, hist, future) if sys.name == "DGAI" else odin_event(sys, anchor, hist, future)
                if row is not None:
                    rows.append(row)
            result["systems"][sys.name][mode] = aggregate(rows)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
