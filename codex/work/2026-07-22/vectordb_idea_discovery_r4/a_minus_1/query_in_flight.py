#!/usr/bin/env python3
"""A-1: measure whether real text-prefix embeddings permit useful ANN work reuse."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


def read_fbin(path: Path) -> np.ndarray:
    header = np.fromfile(path, dtype=np.uint32, count=2)
    n, d = map(int, header)
    return np.memmap(path, dtype=np.float32, mode="r", offset=8, shape=(n, d))


def normalize(x: np.ndarray) -> np.ndarray:
    y = np.asarray(x, dtype=np.float32)
    return y / np.maximum(np.linalg.norm(y, axis=1, keepdims=True), 1e-12)


def top_ids(scores: np.ndarray, largest: int) -> np.ndarray:
    ids = np.argpartition(scores, -largest, axis=1)[:, -largest:]
    vals = np.take_along_axis(scores, ids, axis=1)
    return np.take_along_axis(ids, np.argsort(-vals, axis=1), axis=1)


def main() -> None:
    p = argparse.ArgumentParser()
    root = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/a0_topology_reuse")
    p.add_argument(
        "--model",
        type=Path,
        default=root
        / "models/models--sentence-transformers--all-MiniLM-L6-v1/snapshots/d8ccfb53d087c448cf4f48efed6ea98a01d7e47a",
    )
    p.add_argument(
        "--corpus",
        type=Path,
        default=root / "embeddings/formal_100k/minilm_l6_v1_v2/old_corpus.fbin",
    )
    p.add_argument(
        "--query-jsonl",
        type=Path,
        default=root / "datasets/formal_100k/quora/queries.jsonl",
    )
    p.add_argument("--queries", type=int, default=180)
    p.add_argument("--min-words", type=int, default=6)
    p.add_argument("--max-words", type=int, default=16)
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--max-l", type=int, default=500)
    p.add_argument("--seed", type=int, default=23)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    started = time.time()

    rows = []
    with args.query_jsonl.open() as f:
        for line in f:
            obj = json.loads(line)
            words = obj["text"].split()
            if args.min_words <= len(words) <= args.max_words:
                rows.append((obj["id"], obj["text"], words))
    rng = np.random.default_rng(args.seed)
    chosen = rng.choice(len(rows), min(args.queries, len(rows)), replace=False)
    rows = [rows[int(i)] for i in chosen]

    progress_points = (0.25, 0.50, 0.75, 1.00)
    texts: list[str] = []
    meta: list[tuple[int, float, int]] = []
    for qi, (_, _, words) in enumerate(rows):
        lengths = []
        for progress in progress_points:
            length = max(1, int(np.ceil(len(words) * progress)))
            length = min(length, len(words))
            if lengths and length == lengths[-1]:
                continue
            lengths.append(length)
            texts.append(" ".join(words[:length]))
            meta.append((qi, length / len(words), length))

    model = SentenceTransformer(str(args.model), device="cpu")
    embedded = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype(np.float32)
    corpus = normalize(read_fbin(args.corpus))
    scores = embedded @ corpus.T
    ids = top_ids(scores, args.max_l)

    by_query: dict[int, list[int]] = {}
    for row_idx, (qi, _, _) in enumerate(meta):
        by_query.setdefault(qi, []).append(row_idx)

    levels = [10, 20, 50, 100, 200, 500]
    records = []
    for qi, row_indices in by_query.items():
        final_idx = row_indices[-1]
        final_top = set(ids[final_idx, : args.k])
        for row_idx in row_indices:
            _, progress, prefix_words = meta[row_idx]
            rho = float(np.linalg.norm(embedded[final_idx] - embedded[row_idx]))
            prefix_top = set(ids[row_idx, : args.k])
            ordered_scores = scores[row_idx, ids[row_idx]]
            # A worst-case unit-vector certificate: every score can move by rho.
            # The prefix top-k identity is invariant for every final q in the ball
            # only if the kth/(k+1)th gap exceeds 2*rho.
            gap = float(ordered_scores[args.k - 1] - ordered_scores[args.k])
            record = {
                "query": qi,
                "progress": progress,
                "prefix_words": prefix_words,
                "query_l2_to_final": rho,
                "query_cosine_to_final": float(embedded[final_idx] @ embedded[row_idx]),
                "topk_overlap": len(final_top & prefix_top) / args.k,
                "prefix_k_margin": gap,
                "worst_case_topk_certified": bool(gap > 2.0 * rho),
            }
            for level in levels:
                record[f"final_topk_coverage_at_{level}"] = len(
                    final_top & set(ids[row_idx, :level])
                ) / args.k
            records.append(record)

    summary: dict[str, dict[str, float]] = {}
    for target in progress_points:
        subset = [r for r in records if abs(r["progress"] - target) <= 0.13]
        if not subset:
            continue
        metrics = {}
        for key in [
            "query_l2_to_final",
            "query_cosine_to_final",
            "topk_overlap",
            "prefix_k_margin",
            "final_topk_coverage_at_10",
            "final_topk_coverage_at_20",
            "final_topk_coverage_at_50",
            "final_topk_coverage_at_100",
            "final_topk_coverage_at_200",
            "final_topk_coverage_at_500",
        ]:
            values = np.asarray([r[key] for r in subset], dtype=float)
            metrics[f"{key}_mean"] = float(values.mean())
            metrics[f"{key}_p10"] = float(np.quantile(values, 0.10))
        metrics["worst_case_topk_certified_fraction"] = float(
            np.mean([r["worst_case_topk_certified"] for r in subset])
        )
        metrics["n"] = len(subset)
        summary[f"progress_{target:.2f}"] = metrics

    report = {
        "experiment": "query_in_flight_a_minus_1",
        "question": "Do real text prefixes expose reusable final candidates and a non-vacuous drift certificate?",
        "dataset": "Quora queries + 100K MiniLM-L6-v1 corpus embeddings",
        "config": {
            "queries": len(rows),
            "words": [args.min_words, args.max_words],
            "k": args.k,
            "max_l": args.max_l,
            "progress_targets": progress_points,
            "seed": args.seed,
        },
        "summary": summary,
        "records": records,
        "elapsed_seconds": time.time() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "records"}, indent=2))


if __name__ == "__main__":
    main()
