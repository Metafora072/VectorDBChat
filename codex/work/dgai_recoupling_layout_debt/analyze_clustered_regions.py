#!/usr/bin/env python3
import argparse, collections, csv, json
from pathlib import Path


def pct(values, q):
    values = sorted(values)
    return values[int(q * (len(values) - 1))]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--trace", type=Path, required=True)
    p.add_argument("--layout", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    traces = collections.defaultdict(list)
    needed = collections.defaultdict(set)
    with a.trace.open() as f:
        for line in f:
            r = json.loads(line); cp = r["checkpoint_percent"]
            traces[cp].append(r)
            needed[cp].update(r["topology_nodes"]); needed[cp].update(r["rerank_nodes"])
    base_t, base_v, metas = [-1] * 900000, [-1] * 900000, collections.defaultdict(dict)
    with a.layout.open() as f:
        for r in csv.DictReader(f):
            cp = int(r["checkpoint_percent"]); internal = int(r["internal_id"]); tag = int(r["tag"])
            t, v = int(r["topology_location"]), int(r["vector_location"])
            if cp == 0: base_t[tag], base_v[tag] = t, v
            if internal in needed[cp]: metas[cp][internal] = (tag, t, v)
    out = []
    for cp, rows in traces.items():
        for region, selected in (("aligned", [r for r in rows if r["qid"] < 1000]),
                                 ("separate", [r for r in rows if 2000 <= r["qid"] < 3000])):
            current, fresh, recall, latency = [], [], [], []
            for r in selected:
                m = metas[cp]
                current.append(len(set(r["topology_pages"])) + len(set(r["rerank_pages"])))
                fresh.append(len({base_t[m[n][0]] // 15 for n in r["topology_nodes"]}) +
                             len({base_v[m[n][0]] // 8 for n in r["rerank_nodes"]}))
                recall.append(r["recall_at_10"]); latency.append(r["latency_us"])
            out.append({"checkpoint_percent": cp, "region": region, "queries": len(selected),
                        "mean_current_pages": sum(current)/len(current), "p99_current_pages": pct(current,.99),
                        "mean_fresh_same_graph_pages": sum(fresh)/len(fresh), "p99_fresh_same_graph_pages": pct(fresh,.99),
                        "fresh_improvement_percent": 100*(sum(current)-sum(fresh))/sum(current),
                        "mean_recall_at_10": sum(recall)/len(recall), "actual_p99_latency_us": pct(latency,.99)})
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open("w", newline="") as f:
        w=csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    print(json.dumps(out, sort_keys=True))


if __name__ == "__main__": main()
