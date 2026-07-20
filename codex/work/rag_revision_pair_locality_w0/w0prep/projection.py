"""Preparation-only timing/RSS/storage projection; computes no W0 outcomes."""

from __future__ import annotations

import json
from pathlib import Path
import resource
import time
from typing import Any

import numpy as np

from .common import PreparationGuard, read_jsonl, write_json
from .models import configure_cpu, load_local_model
from .oracle import exhaustive_topk_queries


def _encode(model: Any, texts: list[str], prefix: str) -> tuple[np.ndarray, float]:
    started = time.perf_counter()
    values = model.encode(
        [prefix + text for text in texts],
        batch_size=32,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype(np.float32, copy=False)
    return values, time.perf_counter() - started


def run_projection(config_path: Path, output: Path) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config["authorization"]["full_measurement"]:
        raise RuntimeError("projection requires full_measurement=false")
    data_root = Path(config["data_root"])
    configure_cpu(int(config["resources"]["threads"]))
    guard = PreparationGuard(data_root, config)
    start_resource = guard.check("projection:start")

    texts_by_source: dict[str, list[str]] = {}
    selected_pair_counts: dict[str, int] = {}
    for source in sorted(config["sources"]):
        rows = read_jsonl(
            data_root / "manifests" / source / "fixed_reference_universe.jsonl"
        )
        if len(rows) < 1024:
            raise RuntimeError(f"{source} has fewer than 1024 reference chunks")
        texts_by_source[source] = [row["payload"] for row in rows[:1024]]
        summary = json.loads(
            (data_root / "manifests" / source / "summary.json").read_text()
        )
        selected_pair_counts[source] = int(summary["selected_pair_count"])

    encode_records: list[dict[str, Any]] = []
    nomic_for_graph: list[np.ndarray] = []
    for model_key in ("minilm", "nomic"):
        load_started = time.perf_counter()
        model = load_local_model(config, model_key)
        load_seconds = time.perf_counter() - load_started
        for source in sorted(texts_by_source):
            values, seconds = _encode(
                model,
                texts_by_source[source],
                config["models"][model_key]["prefix"],
            )
            encode_records.append(
                {
                    "model": model_key,
                    "source": source,
                    "count": len(values),
                    "dimension": int(values.shape[1]),
                    "load_seconds": load_seconds,
                    "encode_seconds": seconds,
                    "texts_per_second": len(values) / seconds,
                }
            )
            if model_key == "nomic":
                nomic_for_graph.append(values)
        del model

    graph_values = np.ascontiguousarray(np.concatenate(nomic_for_graph, axis=0))
    graph_ids = [f"projection-{i:05d}" for i in range(len(graph_values))]
    graph_started = time.perf_counter()
    graph = exhaustive_topk_queries(
        graph_values,
        graph_ids,
        graph_values,
        graph_ids,
        k=321,
        query_block_size=config["oracle"]["query_block"],
        # Force three corpus merges in the 2,048-node canary; a single block
        # would not exercise the exact stable merge path being projected.
        corpus_block_size=768,
        exclude_matching_ids=True,
    )
    graph_seconds = time.perf_counter() - graph_started
    if graph.neighbor_ids.shape != (2048, 321):
        raise AssertionError("projection graph shape mismatch")

    universe = config["fixed_reference"]["universe_size"]
    canary_n = len(graph_values)
    # Two source graphs for each model. Nomic is the measured 1.0 dimension
    # factor; MiniLM contributes 384/768. A 1.75 safety factor covers three
    # corpus-block merges at full N and Python stable-sort overhead.
    graph_projected = graph_seconds * (universe / canary_n) ** 2 * 2 * 1.5 * 1.75
    encode_projected = 0.0
    for record in encode_records:
        pairs = selected_pair_counts[record["source"]]
        projected_texts = universe + 3 * pairs
        encode_projected += record["encode_seconds"] * projected_texts / record["count"]
    bootstrap_and_io_allowance = 900.0
    projected_total = encode_projected + graph_projected + bootstrap_and_io_allowance

    # Conservative output allocation: embeddings plus four top-321 graphs,
    # query records, manifests, and a 2x serialization/log safety factor.
    embedding_bytes = 2 * universe * (384 + 768) * 4
    graph_bytes = 4 * universe * 321 * (4 + 4)
    projected_incremental_bytes = 2 * (embedding_bytes + graph_bytes + 512 * 1024 * 1024)
    current_bytes = start_resource["storage_bytes"]
    result = {
        "kind": "projection-only-no-outcome-metrics",
        "encode_records": encode_records,
        "exact_graph_canary": {
            "nodes": canary_n,
            "dimension": int(graph_values.shape[1]),
            "topk": 321,
            "seconds": graph_seconds,
        },
        "projection": {
            "encode_seconds": encode_projected,
            "exact_graph_seconds": graph_projected,
            "allowance_seconds": bootstrap_and_io_allowance,
            "total_seconds": projected_total,
            "passes_soft_wall": projected_total
            < config["resources"]["projection_wall_seconds"],
            "current_storage_bytes": current_bytes,
            "projected_incremental_bytes": projected_incremental_bytes,
            "projected_total_storage_bytes": current_bytes + projected_incremental_bytes,
            "passes_hard_storage": current_bytes + projected_incremental_bytes
            < config["resources"]["hard_storage_bytes"],
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "passes_hard_rss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            < config["resources"]["hard_rss_bytes"],
        },
        "guard": guard.check("projection:complete"),
    }
    write_json(output, result)
    return result
