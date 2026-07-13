#!/usr/bin/env python3
"""Held-out selective-recoupling oracle and strong baseline characterization.

The simulator is page-exact with respect to recorded DGAI node/page requests.
It does not claim end-to-end wall latency for hypothetical layouts.
"""

import argparse
import collections
import csv
import json
import math
import random
from pathlib import Path

PAGE = 4096
TOPO_RECORD = 260
VECTOR_RECORD = 512
COUPLED_RECORD = TOPO_RECORD + VECTOR_RECORD
CAPSULE_RECORDS_PER_PAGE = PAGE // COUPLED_RECORD


def percentile(values, fraction):
    values = sorted(values)
    if not values:
        return 0.0
    return values[int(fraction * (len(values) - 1))]


def unique_order(values):
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def load_trace(path):
    rows = []
    with path.open() as source:
        for line in source:
            raw = json.loads(line)
            rows.append({
                "qid": raw["qid"],
                "region": raw["result_tags"][0] // 10000,
                "topo_nodes": raw["topology_nodes"],
                "topo_pages": raw["topology_pages"],
                "vec_nodes": raw["rerank_nodes"],
                "vec_pages": raw["rerank_pages"],
                "latency_us": raw["latency_us"],
                "recall": raw["recall_at_10"],
            })
    return rows


def workload_splits(rows, seed):
    rng = random.Random(seed)
    all_ids = list(range(len(rows)))
    rng.shuffle(all_ids)
    natural_cut = max(1, len(all_ids) * 3 // 5)
    natural_train, natural_eval = all_ids[:natural_cut], all_ids[natural_cut:]

    by_region = collections.defaultdict(list)
    for idx, row in enumerate(rows):
        by_region[row["region"]].append(idx)
    ranked = sorted(by_region, key=lambda r: (-len(by_region[r]), r))
    hot_a = set(ranked[:12])
    hot_b = set(ranked[12:24])

    a_ids = [idx for idx in all_ids if rows[idx]["region"] in hot_a]
    b_ids = [idx for idx in all_ids if rows[idx]["region"] in hot_b]
    a_cut = max(1, len(a_ids) * 3 // 5)
    skew_train, skew_pool = a_ids[:a_cut], a_ids[a_cut:]
    if not skew_pool:
        raise RuntimeError("empty held-out skew pool")
    # Held-out query vectors never occur in training. Repetition creates a
    # Zipf-like request stream without leaking evaluation vectors.
    zipf_weights = [1.0 / (rank + 1) for rank in range(len(skew_pool))]
    skew_eval = rng.choices(skew_pool, weights=zipf_weights, k=max(400, len(rows) * 2 // 5))

    shift_train = a_ids
    shift_eval = b_ids
    if not shift_train or not shift_eval:
        raise RuntimeError("insufficient regions for hotspot-shift split")

    return {
        "same_distribution": (natural_train, natural_eval),
        "uniform": (natural_train, natural_eval),
        "skewed": (skew_train, skew_eval),
        "hotspot_shift": (shift_train, shift_eval),
    }


def frequencies(rows, ids):
    topo = collections.Counter()
    vec = collections.Counter()
    for idx in ids:
        topo.update(rows[idx]["topo_nodes"])
        vec.update(rows[idx]["vec_nodes"])
    return topo, vec


def pack_static(selected):
    mapping = {}
    for offset, node in enumerate(sorted(selected)):
        mapping[node] = offset // CAPSULE_RECORDS_PER_PAGE
    return mapping


def pack_coaccess(rows, train_ids, selected, score):
    unassigned = set(selected)
    mapping = {}
    page_id = 0
    # Frequent query sets get first choice of page companions. This packing is
    # learned only from training traces.
    query_sets = []
    for idx in train_ids:
        nodes = set(rows[idx]["topo_nodes"]) | set(rows[idx]["vec_nodes"])
        useful = nodes & unassigned
        if useful:
            query_sets.append((sum(score[n] for n in useful), useful))
    query_sets.sort(key=lambda item: item[0], reverse=True)
    for _, nodes in query_sets:
        candidates = sorted((n for n in nodes if n in unassigned), key=lambda n: (-score[n], n))
        while candidates:
            group = candidates[:CAPSULE_RECORDS_PER_PAGE]
            candidates = candidates[CAPSULE_RECORDS_PER_PAGE:]
            for node in group:
                mapping[node] = page_id
                unassigned.remove(node)
            page_id += 1
    fill = 0
    for node in sorted(unassigned, key=lambda n: (-score[n], n)):
        mapping[node] = page_id
        fill += 1
        if fill == CAPSULE_RECORDS_PER_PAGE:
            page_id += 1
            fill = 0
    return mapping


def capsule_query(row, mapping):
    selected = set(mapping)
    topo_selected = set(row["topo_nodes"]) & selected
    vec_selected = set(row["vec_nodes"]) & selected
    remaining_topo = {page for node, page in zip(row["topo_nodes"], row["topo_pages"]) if node not in selected}
    remaining_vec = {page for node, page in zip(row["vec_nodes"], row["vec_pages"]) if node not in selected}
    capsule_pages = {mapping[node] for node in topo_selected | vec_selected}
    dependent_eliminated = len(set(row["vec_nodes"]) & set(row["topo_nodes"]) & selected)
    pages = len(remaining_topo) + len(remaining_vec) + len(capsule_pages)
    return pages, len(remaining_topo), len(remaining_vec), len(capsule_pages), dependent_eliminated


def original_query(row):
    topo = len(set(row["topo_pages"]))
    vec = len(set(row["vec_pages"]))
    return topo + vec, topo, vec, 0, 0


def vector_hot_query(row, hot_nodes):
    topo = len(set(row["topo_pages"]))
    remaining_vec = {p for n, p in zip(row["vec_nodes"], row["vec_pages"]) if n not in hot_nodes}
    return topo + len(remaining_vec), topo, len(remaining_vec), 0, len(set(row["vec_nodes"]) & hot_nodes)


def simulate_lru(rows, train_ids, eval_ids, capacity):
    cache = collections.OrderedDict()

    def access(row, measure):
        misses = 0
        for store, pages in (("t", unique_order(row["topo_pages"])), ("v", unique_order(row["vec_pages"]))):
            for page in pages:
                key = (store, page)
                if key in cache:
                    cache.move_to_end(key)
                else:
                    misses += 1
                    cache[key] = None
                    if len(cache) > capacity:
                        cache.popitem(last=False)
        return misses if measure else 0

    for idx in train_ids:
        access(rows[idx], False)
    return [access(rows[idx], True) for idx in eval_ids]


def simple_prefetch(row):
    demand_pages = 0
    read_pages = 0
    useful = 0
    for pages in (unique_order(row["topo_pages"]), unique_order(row["vec_pages"])):
        prefetched = None
        for page in pages:
            if page == prefetched:
                useful += 1
            else:
                demand_pages += 1
                read_pages += 1
            prefetched = page + 1
            read_pages += 1
    return read_pages, demand_pages, useful


def summarize(workload, budget_fraction, method, per_query, extra_bytes, metadata=None):
    pages = [item[0] for item in per_query]
    topo = [item[1] for item in per_query]
    vec = [item[2] for item in per_query]
    capsule = [item[3] for item in per_query]
    dependent = [item[4] for item in per_query]
    row = {
        "workload": workload,
        "budget_fraction": budget_fraction,
        "method": method,
        "queries": len(per_query),
        "extra_bytes": extra_bytes,
        "mean_pages": sum(pages) / len(pages),
        "p50_pages": percentile(pages, 0.50),
        "p95_pages": percentile(pages, 0.95),
        "p99_pages": percentile(pages, 0.99),
        "mean_bytes": PAGE * sum(pages) / len(pages),
        "mean_topology_pages": sum(topo) / len(topo),
        "mean_vector_pages": sum(vec) / len(vec),
        "mean_capsule_pages": sum(capsule) / len(capsule),
        "mean_dependent_eliminated": sum(dependent) / len(dependent),
    }
    if metadata:
        row.update(metadata)
    return row


def gini(counter):
    values = sorted(counter.values())
    if not values:
        return 0.0
    total = sum(values)
    return sum((2 * i - len(values) - 1) * value for i, value in enumerate(values, 1)) / (len(values) * total)


def main():
    global PAGE, TOPO_RECORD, VECTOR_RECORD, COUPLED_RECORD, CAPSULE_RECORDS_PER_PAGE
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--base-bytes", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=711)
    parser.add_argument("--io-bytes", type=int, default=4096)
    parser.add_argument("--topology-record-bytes", type=int, default=260)
    parser.add_argument("--vector-record-bytes", type=int, default=512)
    args = parser.parse_args()
    PAGE = args.io_bytes
    TOPO_RECORD = args.topology_record_bytes
    VECTOR_RECORD = args.vector_record_bytes
    COUPLED_RECORD = TOPO_RECORD + VECTOR_RECORD
    CAPSULE_RECORDS_PER_PAGE = max(1, PAGE // COUPLED_RECORD)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows = load_trace(args.trace)
    splits = workload_splits(rows, args.seed)
    summaries = []

    for workload, (train_ids, eval_ids) in splits.items():
        topo_freq, vec_freq = frequencies(rows, train_ids)
        original = [original_query(rows[idx]) for idx in eval_ids]
        summaries.append(summarize(workload, 0.0, "B0_original_dgai", original, 0))
        for fraction in (0.01, 0.05, 0.10):
            budget = int(args.base_bytes * fraction)
            page_capacity = budget // PAGE
            node_capacity = (budget // PAGE) * CAPSULE_RECORDS_PER_PAGE

            lru_misses = simulate_lru(rows, train_ids, eval_ids, page_capacity)
            lru_rows = [(miss, 0, 0, 0, 0) for miss in lru_misses]
            summaries.append(summarize(workload, fraction, "B1_lru_pages", lru_rows, page_capacity * PAGE))

            hot_vec = {node for node, _ in vec_freq.most_common(budget // VECTOR_RECORD)}
            vector_rows = [vector_hot_query(rows[idx], hot_vec) for idx in eval_ids]
            summaries.append(summarize(workload, fraction, "B2_vector_hot_cache", vector_rows,
                                       len(hot_vec) * VECTOR_RECORD))

            prefetch_rows = []
            useful = 0
            for idx in eval_ids:
                reads, rounds, hits = simple_prefetch(rows[idx])
                useful += hits
                prefetch_rows.append((reads, 0, 0, 0, 0))
            summaries.append(summarize(workload, fraction, "B3_next_page_prefetch", prefetch_rows, 0,
                                       {"mean_demand_rounds": sum(simple_prefetch(rows[i])[1] for i in eval_ids) / len(eval_ids),
                                        "prefetch_useful_per_query": useful / len(eval_ids)}))

            hot_score = collections.Counter()
            for node in set(topo_freq) | set(vec_freq):
                hot_score[node] = topo_freq[node] + vec_freq[node]
            static_selected = [node for node, _ in hot_score.most_common(node_capacity)]
            static_map = pack_static(static_selected)
            static_rows = [capsule_query(rows[idx], static_map) for idx in eval_ids]
            summaries.append(summarize(workload, fraction, "B4_static_hot_full_record", static_rows,
                                       ((len(static_selected) + CAPSULE_RECORDS_PER_PAGE - 1) //
                                        CAPSULE_RECORDS_PER_PAGE) * PAGE))

            oracle_score = collections.Counter()
            for node in set(topo_freq) | set(vec_freq):
                oracle_score[node] = 8 * min(topo_freq[node], vec_freq[node]) + topo_freq[node] + vec_freq[node]
            oracle_selected = [node for node, _ in oracle_score.most_common(node_capacity)]
            oracle_map = pack_coaccess(rows, train_ids, oracle_selected, oracle_score)
            oracle_rows = [capsule_query(rows[idx], oracle_map) for idx in eval_ids]
            summaries.append(summarize(workload, fraction, "B5_coaccess_capsule_oracle", oracle_rows,
                                       ((len(oracle_selected) + CAPSULE_RECORDS_PER_PAGE - 1) //
                                        CAPSULE_RECORDS_PER_PAGE) * PAGE))

    csv_path = args.output_dir / "c1_c2_summary.csv"
    fields = sorted({key for row in summaries for key in row})
    with csv_path.open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summaries)

    all_topo, all_vec = frequencies(rows, range(len(rows)))
    characterization = {
        "schema": "dgai-c1-c2-characterization-v1",
        "trace": str(args.trace),
        "query_count": len(rows),
        "base_bytes": args.base_bytes,
        "record_bytes": {"topology": TOPO_RECORD, "vector": VECTOR_RECORD, "coupled": COUPLED_RECORD},
        "splits": {name: {"train_requests": len(split[0]), "heldout_requests": len(split[1]),
                           "disjoint_query_ids": not bool(set(split[0]) & set(split[1]))}
                   for name, split in splits.items()},
        "regional_heterogeneity": {
            "topology_node_frequency_gini": gini(all_topo),
            "vector_node_frequency_gini": gini(all_vec),
            "unique_topology_nodes": len(all_topo),
            "unique_vector_nodes": len(all_vec),
            "top_1pct_topology_access_share": sum(v for _, v in all_topo.most_common(max(1, len(all_topo) // 100))) / sum(all_topo.values()),
            "top_1pct_vector_access_share": sum(v for _, v in all_vec.most_common(max(1, len(all_vec) // 100))) / sum(all_vec.values()),
        },
        "summary_csv": str(csv_path),
        "model_scope": "page-exact trace replay; hypothetical methods do not report wall-clock latency",
    }
    with (args.output_dir / "c1_c2_characterization.json").open("w") as target:
        json.dump(characterization, target, indent=2, sort_keys=True)
        target.write("\n")
    print(json.dumps(characterization, sort_keys=True))


if __name__ == "__main__":
    main()
