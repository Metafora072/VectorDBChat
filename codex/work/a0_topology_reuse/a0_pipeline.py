#!/usr/bin/env python3
"""Reproducible data/embedding/metric utilities for the A0 topology-reuse gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import resource
import re
import struct
import time
from collections import deque
from pathlib import Path

import numpy as np


TRANSITIONS = {
    "minilm_l6_v1_v2": {
        "dataset": "quora",
        "old": "sentence-transformers/all-MiniLM-L6-v1",
        "new": "sentence-transformers/all-MiniLM-L6-v2",
        "corpus_prefix": "",
        "query_prefix": "",
        "relation": "named model version transition",
    },
    "e5_small_v1_v2": {
        "dataset": "nq_top50",
        "old": "intfloat/e5-small",
        "new": "intfloat/e5-small-v2",
        "corpus_prefix": "passage: ",
        "query_prefix": "query: ",
        "relation": "named model version transition",
    },
    "bge_small_v1_v15": {
        "dataset": "nq_top50",
        "old": "BAAI/bge-small-en",
        "new": "BAAI/bge-small-en-v1.5",
        "corpus_prefix": "",
        "query_prefix": "Represent this sentence for searching relevant passages: ",
        "relation": "publisher-recommended successor",
    },
}

DATASETS = {
    "nq_top50": {"repo": "mteb/nq_top_50_only", "corpus_split": "corpus", "query_split": "queries"},
    "quora": {"repo": "mteb/quora", "corpus_split": "corpus", "query_split": "queries"},
}


def dump_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def hash_rank(seed: int, item_id: str) -> int:
    payload = f"{seed}:{item_id}".encode()
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "little")


def record_text(row: dict, is_corpus: bool) -> str:
    title = (row.get("title") or "").strip() if is_corpus else ""
    text = (row.get("text") or "").strip()
    return f"{title}\n{text}".strip() if title else text


def select_rows(dataset, count: int, seed: int, is_corpus: bool) -> list[dict]:
    ranked = []
    for row in dataset:
        item_id = str(row["_id"])
        text = record_text(row, is_corpus)
        if text:
            ranked.append((hash_rank(seed, item_id), item_id, text))
    ranked.sort(key=lambda x: (x[0], x[1]))
    selected = ranked[: min(count, len(ranked))]
    return [{"id": item_id, "text": text} for _, item_id, text in selected]


def cmd_prepare(args: argparse.Namespace) -> None:
    from datasets import load_dataset

    root = Path(args.root)
    spec = DATASETS[args.dataset]
    corpus = load_dataset(spec["repo"], "corpus", split=spec["corpus_split"])
    queries = load_dataset(spec["repo"], "queries", split=spec["query_split"])
    selected_corpus = select_rows(corpus, args.n_corpus, args.seed, True)
    selected_queries = select_rows(queries, args.n_queries, args.seed + 1, False)

    out = root / "datasets" / args.tag / args.dataset
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("corpus", selected_corpus), ("queries", selected_queries)):
        with (out / f"{name}.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    dump_json(
        out / "manifest.json",
        {
            "dataset": args.dataset,
            "source_repo": spec["repo"],
            "seed": args.seed,
            "source_corpus_count": len(corpus),
            "source_query_count": len(queries),
            "selected_corpus_count": len(selected_corpus),
            "selected_query_count": len(selected_queries),
            "selection": "lowest deterministic BLAKE2b(seed:id) ranks; empty texts excluded",
            "corpus_id_sha256": hashlib.sha256("\n".join(x["id"] for x in selected_corpus).encode()).hexdigest(),
            "query_id_sha256": hashlib.sha256("\n".join(x["id"] for x in selected_queries).encode()).hexdigest(),
        },
    )
    print(json.dumps({"out": str(out), "corpus": len(selected_corpus), "queries": len(selected_queries)}))


def read_jsonl_texts(path: Path, prefix: str) -> list[str]:
    texts = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            texts.append(prefix + json.loads(line)["text"])
    return texts


def write_fbin(path: Path, values: np.ndarray) -> None:
    values = np.ascontiguousarray(values, dtype=np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(struct.pack("<II", values.shape[0], values.shape[1]))
        values.tofile(handle)


def fbin_shape(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        return struct.unpack("<II", handle.read(8))


def mmap_fbin(path: Path) -> np.memmap:
    n, d = fbin_shape(path)
    return np.memmap(path, mode="r", dtype=np.float32, offset=8, shape=(n, d))


def cmd_encode(args: argparse.Namespace) -> None:
    import torch
    from huggingface_hub import model_info
    from sentence_transformers import SentenceTransformer

    spec = TRANSITIONS[args.transition]
    dataset = spec["dataset"]
    model_name = spec[args.role]
    prefix = spec["corpus_prefix"] if args.kind == "corpus" else spec["query_prefix"]
    root = Path(args.root)
    source = root / "datasets" / args.tag / dataset / f"{args.kind}.jsonl"
    texts = read_jsonl_texts(source, prefix)

    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    started = time.perf_counter()
    model = SentenceTransformer(model_name, cache_folder=str(root / "models"), device="cpu")
    load_seconds = time.perf_counter() - started
    encode_started = time.perf_counter()
    values = model.encode(
        texts,
        batch_size=args.batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    encode_seconds = time.perf_counter() - encode_started
    out = root / "embeddings" / args.tag / args.transition / f"{args.role}_{args.kind}.fbin"
    write_fbin(out, values)
    revision = None
    try:
        revision = model_info(model_name).sha
    except Exception:
        pass
    dump_json(
        out.with_suffix(".json"),
        {
            "transition": args.transition,
            "relation": spec["relation"],
            "role": args.role,
            "kind": args.kind,
            "dataset": dataset,
            "model": model_name,
            "model_revision": revision,
            "prefix": prefix,
            "normalized": True,
            "count": int(values.shape[0]),
            "dimension": int(values.shape[1]),
            "batch_size": args.batch_size,
            "threads": args.threads,
            "model_max_seq_length": int(model.max_seq_length),
            "load_seconds": load_seconds,
            "encode_seconds": encode_seconds,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        },
    )
    print(json.dumps({"out": str(out), "shape": list(values.shape), "seconds": encode_seconds}))


def cmd_random(args: argparse.Namespace) -> None:
    source = mmap_fbin(Path(args.like))
    rng = np.random.default_rng(args.seed)
    values = rng.standard_normal(source.shape, dtype=np.float32)
    values /= np.maximum(np.linalg.norm(values, axis=1, keepdims=True), 1e-12)
    write_fbin(Path(args.output), values)
    dump_json(Path(args.output).with_suffix(".json"), {"seed": args.seed, "shape": list(values.shape)})


def remove_self(neighbors: np.ndarray, start: int, k: int) -> np.ndarray:
    out = np.empty((neighbors.shape[0], k), dtype=np.uint32)
    for i, row in enumerate(neighbors):
        node = start + i
        filtered = row[row != node]
        if len(filtered) < k:
            raise RuntimeError(f"not enough non-self neighbors for node {node}")
        out[i] = filtered[:k]
    return out


def cmd_exact_corpus(args: argparse.Namespace) -> None:
    import faiss

    source = mmap_fbin(Path(args.input))
    faiss.omp_set_num_threads(args.threads)
    index = faiss.IndexFlatIP(source.shape[1])
    index.add(np.ascontiguousarray(source))
    result = np.empty((source.shape[0], args.k), dtype=np.uint32)
    started = time.perf_counter()
    for start in range(0, source.shape[0], args.batch_size):
        end = min(start + args.batch_size, source.shape[0])
        _, ids = index.search(np.ascontiguousarray(source[start:end]), args.k + 1)
        result[start:end] = remove_self(ids, start, args.k)
        print(f"exact corpus {end}/{source.shape[0]}", flush=True)
    elapsed = time.perf_counter() - started
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    np.save(args.output, result)
    dump_json(Path(args.output).with_suffix(".json"), {"shape": list(result.shape), "seconds": elapsed, "threads": args.threads})


def write_truthset_ids(path: Path, ids: np.ndarray) -> None:
    ids = np.ascontiguousarray(ids, dtype=np.uint32)
    with path.open("wb") as handle:
        handle.write(struct.pack("<II", ids.shape[0], ids.shape[1]))
        ids.tofile(handle)


def cmd_query_gt(args: argparse.Namespace) -> None:
    import faiss

    base = mmap_fbin(Path(args.base))
    queries = mmap_fbin(Path(args.queries))
    faiss.omp_set_num_threads(args.threads)
    index = faiss.IndexFlatIP(base.shape[1])
    index.add(np.ascontiguousarray(base))
    started = time.perf_counter()
    _, ids = index.search(np.ascontiguousarray(queries), args.k)
    elapsed = time.perf_counter() - started
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_truthset_ids(out, ids)
    dump_json(out.with_suffix(".json"), {"base": list(base.shape), "queries": list(queries.shape), "k": args.k, "seconds": elapsed})


def row_overlap(left: np.ndarray, right: np.ndarray, k: int, batch: int = 256) -> np.ndarray:
    scores = np.empty(left.shape[0], dtype=np.float32)
    for start in range(0, left.shape[0], batch):
        end = min(start + batch, left.shape[0])
        a = left[start:end, :k]
        b = right[start:end, :k]
        scores[start:end] = (a[:, :, None] == b[:, None, :]).any(axis=2).sum(axis=1) / k
    return scores


def summarize(values: np.ndarray) -> dict:
    values = np.asarray(values, dtype=np.float64)
    mean = float(values.mean())
    se = float(values.std(ddof=1) / math.sqrt(len(values))) if len(values) > 1 else 0.0
    return {
        "n": int(len(values)),
        "mean": mean,
        "ci95_normal": [mean - 1.96 * se, mean + 1.96 * se],
        "p05": float(np.quantile(values, 0.05)),
        "p25": float(np.quantile(values, 0.25)),
        "p50": float(np.quantile(values, 0.50)),
        "p75": float(np.quantile(values, 0.75)),
        "p95": float(np.quantile(values, 0.95)),
    }


def cmd_overlap(args: argparse.Namespace) -> None:
    left = np.load(args.old, mmap_mode="r")
    right = np.load(args.new, mmap_mode="r")
    if left.shape != right.shape:
        raise ValueError(f"shape mismatch: {left.shape} vs {right.shape}")
    report = {f"knn_overlap_at_{k}": summarize(row_overlap(left, right, k)) for k in args.k}
    dump_json(Path(args.output), report)
    print(json.dumps(report, indent=2))


def load_graph(path: Path, expected_nodes: int) -> tuple[int, list[np.ndarray], dict]:
    graph = []
    with path.open("rb") as handle:
        expected_size, max_degree, start, frozen = struct.unpack("<QIIQ", handle.read(24))
        for _ in range(expected_nodes):
            raw = handle.read(4)
            if len(raw) != 4:
                raise ValueError("truncated graph")
            degree = struct.unpack("<I", raw)[0]
            graph.append(np.frombuffer(handle.read(4 * degree), dtype="<u4").copy())
        actual = handle.tell()
    if actual != expected_size:
        raise ValueError(f"graph size mismatch {actual} != {expected_size}")
    return start, graph, {"file_size": expected_size, "max_degree": max_degree, "frozen": frozen}


def reachable_count(start: int, graph: list[np.ndarray]) -> int:
    seen = np.zeros(len(graph), dtype=np.bool_)
    seen[start] = True
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for neighbor in graph[node]:
            if neighbor < len(graph) and not seen[neighbor]:
                seen[neighbor] = True
                queue.append(int(neighbor))
    return int(seen.sum())


def cmd_graph_stats(args: argparse.Namespace) -> None:
    exact = np.load(args.new_exact, mmap_mode="r")
    start, graph, header = load_graph(Path(args.graph), exact.shape[0])
    retentions = np.empty(len(graph), dtype=np.float32)
    degrees = np.empty(len(graph), dtype=np.int32)
    for node, edges in enumerate(graph):
        degrees[node] = len(edges)
        retentions[node] = np.isin(edges, exact[node, : args.k]).mean() if len(edges) else 0.0
    reach = reachable_count(start, graph)
    report = {
        "header": header,
        "entry_point": start,
        "nodes": len(graph),
        "directed_reachable_from_entry": reach,
        "directed_reachable_fraction": reach / len(graph),
        "degree": summarize(degrees),
        f"edge_retention_in_new_exact_knn_at_{args.k}": summarize(retentions),
    }
    dump_json(Path(args.output), report)
    print(json.dumps(report, indent=2))


def read_truthset(path: Path) -> np.ndarray:
    with path.open("rb") as handle:
        n, k = struct.unpack("<II", handle.read(8))
        ids = np.fromfile(handle, dtype="<u4", count=n * k).reshape(n, k)
    return ids


def cmd_score(args: argparse.Namespace) -> None:
    gt = read_truthset(Path(args.gt))[:, : args.k]
    result = read_truthset(Path(args.result))[:, : args.k]
    if gt.shape != result.shape:
        raise ValueError(f"shape mismatch {gt.shape} vs {result.shape}")
    per_query = np.empty(len(gt), dtype=np.float32)
    for i in range(len(gt)):
        per_query[i] = len(set(gt[i].tolist()) & set(result[i].tolist())) / args.k
    report = {"recall": summarize(per_query), "k": args.k}
    dump_json(Path(args.output), report)
    print(json.dumps(report, indent=2))


def per_query_recall(gt: np.ndarray, result: np.ndarray, k: int) -> np.ndarray:
    values = np.empty(len(gt), dtype=np.float32)
    for i in range(len(gt)):
        values[i] = len(set(gt[i, :k].tolist()) & set(result[i, :k].tolist())) / k
    return values


def cmd_compare_search(args: argparse.Namespace) -> None:
    gt = read_truthset(Path(args.gt))
    prefixes = dict(item.split("=", 1) for item in args.run)
    report = {"k": args.k, "by_L": {}}
    for search_l in args.search_l:
        by_variant = {}
        raw = {}
        for name, prefix in prefixes.items():
            result = read_truthset(Path(f"{prefix}_{search_l}_idx_uint32.bin"))
            raw[name] = per_query_recall(gt, result, args.k)
            by_variant[name] = summarize(raw[name])
        paired = {}
        if "fresh" in raw:
            for name, values in raw.items():
                if name != "fresh":
                    paired[f"{name}_minus_fresh"] = summarize(values - raw["fresh"])
        if "old_topology" in raw and "random_topology" in raw:
            paired["old_minus_random"] = summarize(raw["old_topology"] - raw["random_topology"])
        report["by_L"][str(search_l)] = {"variants": by_variant, "paired_differences": paired}
    dump_json(Path(args.output), report)
    print(json.dumps(report, indent=2))


def cmd_parse_search(args: argparse.Namespace) -> None:
    rows = []
    pattern = re.compile(
        r"^\s*(\d+)\s+(\d+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+"
        r"([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s*$"
    )
    for log in args.log:
        variant, rep, path = log.split("=", 2)
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            match = pattern.match(line)
            if not match:
                continue
            values = match.groups()
            rows.append(
                {
                    "variant": variant,
                    "rep": int(rep),
                    "L": int(values[0]),
                    "beamwidth": int(values[1]),
                    "qps": float(values[2]),
                    "mean_latency_us": float(values[3]),
                    "p999_latency_us": float(values[4]),
                    "mean_ios": float(values[5]),
                    "mean_io_us": float(values[6]),
                    "cpu_s": float(values[7]),
                    "recall_at_10_percent": float(values[8]),
                }
            )
    if not rows:
        raise RuntimeError("no search table rows parsed")
    report = {"rows": rows}
    for variant in sorted({row["variant"] for row in rows}):
        report[variant] = {}
        for search_l in sorted({row["L"] for row in rows if row["variant"] == variant}):
            subset = [row for row in rows if row["variant"] == variant and row["L"] == search_l]
            report[variant][str(search_l)] = {
                metric: summarize(np.array([row[metric] for row in subset]))
                for metric in ["qps", "mean_latency_us", "p999_latency_us", "mean_ios", "mean_io_us", "cpu_s"]
            }
    dump_json(Path(args.output), report)
    print(json.dumps({"parsed_rows": len(rows), "output": args.output}))


def cmd_gate_window(args: argparse.Namespace) -> None:
    comparison = json.loads(Path(args.comparison).read_text(encoding="utf-8"))
    degraded = []
    better_than_random = []
    for search_l, block in comparison["by_L"].items():
        paired = block["paired_differences"]
        fresh_delta = paired["old_topology_minus_fresh"]["ci95_normal"]
        random_delta = paired["old_minus_random"]["ci95_normal"]
        if fresh_delta[1] < 0:
            degraded.append(int(search_l))
        if random_delta[0] > 0:
            better_than_random.append(int(search_l))
    passed = len(degraded) >= args.min_budgets and len(better_than_random) >= args.min_budgets
    report = {
        "passed_reuse_window": passed,
        "rule": "paired 95% CI old-fresh < 0 and old-random > 0 at min_budgets search budgets",
        "min_budgets": args.min_budgets,
        "degraded_vs_fresh_L": degraded,
        "better_than_random_L": better_than_random,
    }
    dump_json(Path(args.output), report)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if passed else 1)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default="/home/ubuntu/pz/VectorDB/data/VectorDB/a0_topology_reuse")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("prepare")
    s.add_argument("--dataset", choices=DATASETS, required=True)
    s.add_argument("--tag", required=True)
    s.add_argument("--n-corpus", type=int, required=True)
    s.add_argument("--n-queries", type=int, required=True)
    s.add_argument("--seed", type=int, default=20260712)
    s.set_defaults(func=cmd_prepare)

    s = sub.add_parser("encode")
    s.add_argument("--transition", choices=TRANSITIONS, required=True)
    s.add_argument("--tag", required=True)
    s.add_argument("--role", choices=["old", "new"], required=True)
    s.add_argument("--kind", choices=["corpus", "queries"], required=True)
    s.add_argument("--batch-size", type=int, default=128)
    s.add_argument("--threads", type=int, default=56)
    s.set_defaults(func=cmd_encode)

    s = sub.add_parser("random")
    s.add_argument("--like", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--seed", type=int, default=20260712)
    s.set_defaults(func=cmd_random)

    s = sub.add_parser("exact-corpus")
    s.add_argument("--input", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--k", type=int, default=64)
    s.add_argument("--batch-size", type=int, default=1024)
    s.add_argument("--threads", type=int, default=56)
    s.set_defaults(func=cmd_exact_corpus)

    s = sub.add_parser("query-gt")
    s.add_argument("--base", required=True)
    s.add_argument("--queries", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--k", type=int, default=100)
    s.add_argument("--threads", type=int, default=56)
    s.set_defaults(func=cmd_query_gt)

    s = sub.add_parser("overlap")
    s.add_argument("--old", required=True)
    s.add_argument("--new", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--k", nargs="+", type=int, default=[10, 32, 64])
    s.set_defaults(func=cmd_overlap)

    s = sub.add_parser("graph-stats")
    s.add_argument("--graph", required=True)
    s.add_argument("--new-exact", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--k", type=int, default=64)
    s.set_defaults(func=cmd_graph_stats)

    s = sub.add_parser("score")
    s.add_argument("--gt", required=True)
    s.add_argument("--result", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--k", type=int, default=10)
    s.set_defaults(func=cmd_score)

    s = sub.add_parser("compare-search")
    s.add_argument("--gt", required=True)
    s.add_argument("--run", action="append", required=True, help="name=result_path_prefix")
    s.add_argument("--search-l", nargs="+", type=int, required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--k", type=int, default=10)
    s.set_defaults(func=cmd_compare_search)

    s = sub.add_parser("parse-search")
    s.add_argument("--log", action="append", required=True, help="variant=rep=path")
    s.add_argument("--output", required=True)
    s.set_defaults(func=cmd_parse_search)

    s = sub.add_parser("gate-window")
    s.add_argument("--comparison", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--min-budgets", type=int, default=2)
    s.set_defaults(func=cmd_gate_window)
    return p


if __name__ == "__main__":
    args = parser().parse_args()
    args.func(args)
