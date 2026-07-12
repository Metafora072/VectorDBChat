#!/usr/bin/env python3
"""Residual multi-ball Stage A (A0/A1/A2) for PageMaxSim."""

from __future__ import annotations

import argparse
import csv
import json
import math
import struct
import time
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans

import analyze_p0_p1 as p1


SEED = 20260712
U32 = 2.0**-24
U64 = 2.0**-53


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-embeddings", type=Path, required=True)
    ap.add_argument("--train-embeddings", type=Path, required=True)
    ap.add_argument("--p0-p1-artifacts", type=Path, required=True)
    ap.add_argument("--artifacts", type=Path, required=True)
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--candidates", type=int, default=32)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--ks", type=int, nargs="+", default=[64, 256])
    ap.add_argument("--phase", choices=("a0", "full"), default="full")
    ap.add_argument("--kmeans-n-init", type=int, default=10)
    ap.add_argument("--kmeans-max-iter", type=int, default=300)
    return ap.parse_args()


def gamma(n: int, unit: float) -> float:
    return n * unit / (1.0 - n * unit)


G64 = gamma(127, U64)
G32 = gamma(128, U32)


def up(value: float) -> float:
    return float(np.nextafter(np.float64(value), np.float64(np.inf)))


def outward_add(*values: float) -> float:
    total = 0.0
    for value in values:
        total = up(total + float(value))
    return total


def outward_mul(a: float, b: float) -> float:
    return up(float(a) * float(b))


def upper_positive_sum(values: np.ndarray) -> float:
    total = float(np.sum(values, dtype=np.float64))
    return up(total / (1.0 - G64))


def outward_fp32(value: float) -> np.float32:
    encoded = np.float32(value)
    if float(encoded) < value:
        encoded = np.nextafter(encoded, np.float32(np.inf), dtype=np.float32)
    return encoded


def residual_radius(tokens: np.ndarray, center: np.ndarray) -> np.float32:
    differences = tokens.astype(np.float64) - center.astype(np.float64)
    maximum = 0.0
    for row in differences:
        squared_upper = upper_positive_sum(row * row)
        maximum = max(maximum, up(math.sqrt(squared_upper)))
    return outward_fp32(maximum)


def query_components(query: np.ndarray, centers: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    query64 = query.astype(np.float32, copy=False).astype(np.float64)
    centers64 = centers.astype(np.float64)
    dots = query64 @ centers64.T
    absolute_sums = np.abs(query64) @ np.abs(centers64).T
    absolutes = np.nextafter(absolute_sums / (1.0 - G64), np.inf)
    dot_errors = np.nextafter(G64 * absolutes, np.inf)
    bounds = np.nextafter(dots + dot_errors, np.inf)
    qnorm_squared = np.sum(query64 * query64, axis=1, dtype=np.float64)
    qnorm_upper = np.nextafter(qnorm_squared / (1.0 - G64), np.inf)
    qnorms = np.nextafter(np.sqrt(qnorm_upper), np.inf)
    return bounds, absolutes, qnorms


def pair_upper(dot_upper: float, qnorm_upper: float, absolute_upper: float, radius: float) -> float:
    cauchy = outward_mul(qnorm_upper, radius)
    serving_error = outward_mul(G32, outward_add(absolute_upper, cauchy))
    return outward_add(dot_upper, cauchy, serving_error)


def serving_representation(documents: list[np.ndarray], merge_factor: int) -> list[np.ndarray]:
    result: list[np.ndarray] = []
    for document in documents:
        merged = document if merge_factor == 1 else p1.merge_semantic(document, merge_factor)
        restored, _, _ = p1.quantize_dequantize(merged)
        result.append(restored.astype(np.float32, copy=False))
    return result


def assign(tokens: np.ndarray, centers: np.ndarray, block: int = 4096) -> np.ndarray:
    labels = np.empty(len(tokens), dtype=np.int32)
    center_norm = np.sum(centers * centers, axis=1)
    for start in range(0, len(tokens), block):
        x = tokens[start : start + block]
        distances = np.sum(x * x, axis=1)[:, None] + center_norm[None, :] - 2.0 * (x @ centers.T)
        labels[start : start + len(x)] = np.argmin(distances, axis=1)
    return labels


def pack_pages(labels: np.ndarray, row_bytes: int) -> list[np.ndarray]:
    order = np.argsort(labels, kind="stable")
    first = (p1.PAGE_BYTES - p1.HEADER_BYTES) // row_bytes
    following = (p1.PAGE_BYTES - p1.PAGE_HEADER_BYTES) // row_bytes
    pages: list[np.ndarray] = []
    cursor = 0
    capacity = first
    while cursor < len(order):
        pages.append(order[cursor : cursor + capacity])
        cursor += capacity
        capacity = following
    return pages


def build_page_pairs(tokens: np.ndarray, labels: np.ndarray, pages: list[np.ndarray], centers: np.ndarray) -> list[list[tuple[int, np.float32, int]]]:
    result: list[list[tuple[int, np.float32, int]]] = []
    for page in pages:
        pairs: list[tuple[int, np.float32, int]] = []
        for label in np.unique(labels[page]):
            indices = page[labels[page] == label]
            radius = residual_radius(tokens[indices], centers[int(label)])
            pairs.append((int(label), radius, len(indices)))
        result.append(pairs)
    return result


def serialize_control_plane(path: Path, centers: np.ndarray, page_pairs: list[list[list[tuple[int, np.float32, int]]]]) -> dict[str, int]:
    payload = bytearray(struct.pack("<8sIIIIQ", b"PMXMBALL", 1, len(centers), 128, len(page_pairs), sum(len(x) for x in page_pairs)).ljust(64, b"\0"))
    payload.extend(centers.astype("<f2").tobytes())
    document_offsets_position = len(payload)
    payload.extend(b"\0" * (8 * len(page_pairs)))
    document_offsets: list[int] = []
    pair_count = 0
    page_count = 0
    for document in page_pairs:
        document_offsets.append(len(payload))
        for pairs in document:
            payload.extend(struct.pack("<II", len(pairs), pair_count))
            page_count += 1
            for label, radius, count in pairs:
                payload.extend(struct.pack("<HHf", label, count, float(radius)))
                pair_count += 1
    for index, offset in enumerate(document_offsets):
        struct.pack_into("<Q", payload, document_offsets_position + index * 8, offset)
    logical = len(payload)
    payload.extend(b"\0" * (math.ceil(logical / p1.PAGE_BYTES) * p1.PAGE_BYTES - logical))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {
        "persistent_bytes": path.stat().st_size,
        "logical_bytes": logical,
        "page_count": page_count,
        "pair_count": pair_count,
        "decoded_codebook_dram_bytes": centers.size * 4,
        "pair_table_dram_bytes": pair_count * 8 + page_count * 8 + len(page_pairs) * 8,
    }


def page_exact_values(query: np.ndarray, tokens: np.ndarray, pages: list[np.ndarray]) -> np.ndarray:
    return np.stack([(query @ tokens[page].T).max(axis=1) for page in pages], axis=1)


def page_multiball_upper(
    dot_upper: np.ndarray,
    absolute_upper: np.ndarray,
    qnorms: np.ndarray,
    pairs: list[list[tuple[int, np.float32, int]]],
) -> tuple[np.ndarray, float]:
    tick = time.perf_counter()
    result = np.full((len(qnorms), len(pairs)), -np.inf, dtype=np.float64)
    for page_id, page_pairs in enumerate(pairs):
        labels = np.asarray([item[0] for item in page_pairs], dtype=np.int32)
        radii = np.asarray([float(item[1]) for item in page_pairs], dtype=np.float64)
        cauchy = np.nextafter(qnorms[:, None] * radii[None, :], np.inf)
        absolute_plus = np.nextafter(absolute_upper[:, labels] + cauchy, np.inf)
        serving_error = np.nextafter(G32 * absolute_plus, np.inf)
        combined = np.nextafter(dot_upper[:, labels] + cauchy, np.inf)
        combined = np.nextafter(combined + serving_error, np.inf)
        result[:, page_id] = np.max(combined, axis=1)
    return result, time.perf_counter() - tick


def page_single_ball_upper(query: np.ndarray, tokens: np.ndarray, pages: list[np.ndarray]) -> np.ndarray:
    result = np.empty((len(query), len(pages)), dtype=np.float64)
    for page_id, page in enumerate(pages):
        center = tokens[page].mean(axis=0).astype(np.float32)
        radius = float(residual_radius(tokens[page], center))
        dots, absolutes, qnorms = query_components(query, center[None, :])
        for qi in range(len(query)):
            result[qi, page_id] = pair_upper(dots[qi, 0], qnorms[qi], absolutes[qi, 0], radius)
    return result


def safe_read(
    query: np.ndarray,
    tokens: np.ndarray,
    pages: list[np.ndarray],
    upper: np.ndarray,
    schedule: str,
) -> dict[str, float]:
    lower = np.full(len(query), -np.inf, dtype=np.float32)
    remaining = np.ones(len(pages), dtype=bool)
    order = np.argsort(-upper.max(axis=0), kind="stable") if schedule == "best_upper" else np.arange(len(pages))
    cursor = 0
    reads = 0
    scan_seconds = 0.0
    priority_seconds = 0.0
    while remaining.any():
        unread_max = upper[:, remaining].max(axis=1)
        unresolved = lower.astype(np.float64) < unread_max
        if not unresolved.any():
            break
        tick = time.perf_counter()
        while cursor < len(order) and not remaining[order[cursor]]:
            cursor += 1
        chosen = int(order[cursor])
        cursor += 1
        priority_seconds += time.perf_counter() - tick
        tick = time.perf_counter()
        observed = (query @ tokens[pages[chosen]].T).max(axis=1)
        scan_seconds += time.perf_counter() - tick
        lower = np.maximum(lower, observed)
        remaining[chosen] = False
        reads += 1
    # Use the exact same per-page serving kernel as the observed path. A single
    # whole-object GEMM can differ in the last bit because BLAS chooses a
    # different reduction/tile shape, which is not the serving semantics here.
    exact = np.stack([(query @ tokens[page].T).max(axis=1) for page in pages]).max(axis=0)
    return {
        "pages": reads,
        "scan_seconds": scan_seconds,
        "priority_seconds": priority_seconds,
        "exact": float(np.array_equal(lower, exact)),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    np.random.seed(SEED)
    args.artifacts.mkdir(parents=True, exist_ok=True)
    args.results.mkdir(parents=True, exist_ok=True)
    test_docs, doc_ids, _ = p1.load_ragged(args.test_embeddings / "documents.npz")
    queries, _, _ = p1.load_ragged(args.test_embeddings / "queries.npz")
    train_docs, train_ids, _ = p1.load_ragged(args.train_embeddings / "documents.npz")
    assert set(doc_ids).isdisjoint(train_ids)
    manifest = json.loads((args.test_embeddings / "manifest.json").read_text())
    positive_lookup = {doc_id: i for i, doc_id in enumerate(doc_ids)}
    positives = [positive_lookup[x] for x in manifest["positive_document_ids"]]
    coarse = p1.mean_scores(queries, test_docs)
    candidates: list[np.ndarray] = []
    for qi, scores in enumerate(coarse):
        chosen = np.argsort(-scores)[: args.candidates].tolist()
        if positives[qi] not in chosen:
            chosen[-1] = positives[qi]
        candidates.append(np.asarray(chosen, dtype=np.int32))

    all_rows: list[dict] = []
    model_rows: list[dict] = []
    a0_rows: list[dict] = []
    for rep_name, factor in (("raw_int8", 1), ("light_f9_int8", 9)):
        print(json.dumps({"stage": "representation", "representation": rep_name}), flush=True)
        train_rep = serving_representation(train_docs, factor)
        test_rep = serving_representation(test_docs, factor)
        train_matrix = np.concatenate(train_rep).astype(np.float32)
        # Re-materialize actual data objects for stable bytes/page counts.
        rep_spec = next(rep for rep in p1.REPRESENTATIONS if rep.name == rep_name)
        _, serialized = p1.materialize_representation(args.p0_p1_artifacts / "objects", rep_spec, test_rep)
        data_bytes = sum(int(row["actual_serialized_bytes"]) for row in serialized)
        row_bytes = int(serialized[0]["row_bytes"])
        for k in args.ks:
            model_path = args.artifacts / "codebooks" / f"{rep_name}_k{k}.npz"
            model_path.parent.mkdir(parents=True, exist_ok=True)
            tick = time.perf_counter()
            if model_path.exists():
                centers = np.load(model_path)["centers"].astype(np.float16).astype(np.float32)
                fit_seconds = 0.0
                inertia = float(np.load(model_path)["inertia"])
                iterations = int(np.load(model_path)["iterations"])
            else:
                km = KMeans(
                    n_clusters=k,
                    random_state=SEED,
                    n_init=args.kmeans_n_init,
                    max_iter=args.kmeans_max_iter,
                    tol=1e-4,
                    algorithm="lloyd",
                    verbose=0,
                ).fit(train_matrix)
                centers = km.cluster_centers_.astype(np.float16).astype(np.float32)
                fit_seconds = time.perf_counter() - tick
                inertia = float(km.inertia_)
                iterations = int(km.n_iter_)
                np.savez(model_path, centers=centers.astype(np.float16), inertia=inertia, iterations=iterations)
            train_labels = assign(train_matrix, centers)
            occupancy = np.bincount(train_labels, minlength=k)
            train_residual = np.linalg.norm(train_matrix - centers[train_labels], axis=1)
            test_labels = [assign(document, centers) for document in test_rep]
            test_residual = np.concatenate([
                np.linalg.norm(document - centers[labels], axis=1)
                for document, labels in zip(test_rep, test_labels, strict=True)
            ])
            pages_by_doc = [pack_pages(labels, row_bytes) for labels in test_labels]
            base_model_row = {
                "representation": rep_name,
                "k": k,
                "fit_seconds": fit_seconds,
                "iterations": iterations,
                "inertia": inertia,
                "decoded_inertia": float(np.sum(train_residual.astype(np.float64) ** 2)),
                "empty_codewords": int(np.sum(occupancy == 0)),
                "singleton_codewords": int(np.sum(occupancy == 1)),
                "occupancy_min": int(occupancy.min()),
                "occupancy_p50": float(np.median(occupancy)),
                "occupancy_max": int(occupancy.max()),
                "train_residual_p50": float(np.percentile(train_residual, 50)),
                "train_residual_p95": float(np.percentile(train_residual, 95)),
                "test_residual_p50": float(np.percentile(test_residual, 50)),
                "test_residual_p95": float(np.percentile(test_residual, 95)),
                "data_bytes": data_bytes,
            }
            if args.phase == "a0":
                model_rows.append(base_model_row)
                for qi, candidate_ids in enumerate(candidates):
                    local_docs = [test_rep[int(doc)] for doc in candidate_ids]
                    cells = p1.maxsim_cells(queries[qi], local_docs)
                    reveal, _ = p1.col_bandit(cells, args.top_k, 0.2, SEED + qi)
                    full_pages = 0
                    exact_pages_read = 0
                    oracle_pages = 0
                    for local_doc, global_doc in enumerate(candidate_ids):
                        active = np.flatnonzero(reveal[local_doc])
                        if len(active) == 0:
                            continue
                        query = queries[qi][active].astype(np.float32)
                        tokens = test_rep[int(global_doc)]
                        pages = pages_by_doc[int(global_doc)]
                        exact_pages = page_exact_values(query, tokens, pages)
                        result = safe_read(query, tokens, pages, exact_pages.astype(np.float64), "best_upper")
                        assert result["exact"] == 1.0
                        full_pages += len(pages)
                        exact_pages_read += int(result["pages"])
                        oracle_pages += len(set(np.argmax(exact_pages, axis=1).tolist()))
                    a0_rows.append({
                        "representation": rep_name,
                        "k": k,
                        "query": qi,
                        "full_pages": full_pages,
                        "exact_envelope_pages": exact_pages_read,
                        "page_oracle_pages": oracle_pages,
                        "exact_fraction": exact_pages_read / full_pages,
                    })
                print(json.dumps({"stage": "a0", "representation": rep_name, "k": k}), flush=True)
                continue
            pairs_by_doc = [
                build_page_pairs(document, labels, pages, centers)
                for document, labels, pages in zip(test_rep, test_labels, pages_by_doc, strict=True)
            ]
            control = serialize_control_plane(
                args.artifacts / "control_plane" / f"{rep_name}_k{k}.bin", centers, pairs_by_doc
            )
            model_rows.append({**base_model_row, **control})
            print(json.dumps({"stage": "codebook", "representation": rep_name, "k": k, "fit_seconds": fit_seconds, **control}), flush=True)

            for qi, candidate_ids in enumerate(candidates):
                component_tick = time.perf_counter()
                full_dot_upper, full_absolute_upper, full_qnorms = query_components(queries[qi], centers)
                component_seconds = time.perf_counter() - component_tick
                local_docs = [test_rep[int(doc)] for doc in candidate_ids]
                cells = p1.maxsim_cells(queries[qi], local_docs)
                reveal, outer_top = p1.col_bandit(cells, args.top_k, 0.2, SEED + qi)
                true_top = set(np.argsort(-cells.sum(axis=1))[: args.top_k].tolist())
                outer_overlap = len(true_top & set(outer_top.tolist())) / args.top_k
                totals = {
                    schedule: {
                        "full_pages": 0,
                        "oracle_pages": 0,
                        "a0_pages": 0,
                        "a1_pages": 0,
                        "single_pages": 0,
                        "violations": 0,
                        "multi_slack": [],
                        "single_slack": [],
                        "false_threats": [],
                        "certificate_margins": [],
                        "bound_seconds": 0.0,
                        "scan_seconds": 0.0,
                        "priority_seconds": 0.0,
                    }
                    for schedule in ("sequential", "best_upper")
                }
                query_state_bytes = len(queries[qi]) * k * 8
                for local_doc, global_doc in enumerate(candidate_ids):
                    active = np.flatnonzero(reveal[local_doc])
                    if len(active) == 0:
                        continue
                    query = queries[qi][active].astype(np.float32)
                    tokens = test_rep[int(global_doc)]
                    pages = pages_by_doc[int(global_doc)]
                    pairs = pairs_by_doc[int(global_doc)]
                    exact_pages = page_exact_values(query, tokens, pages)
                    multi_upper, materialize_seconds = page_multiball_upper(
                        full_dot_upper[active], full_absolute_upper[active], full_qnorms[active], pairs
                    )
                    bound_seconds = materialize_seconds + component_seconds / max(len(candidate_ids), 1)
                    single_upper = page_single_ball_upper(query, tokens, pages)
                    violations = int(np.sum(multi_upper + 0.0 < exact_pages.astype(np.float64)))
                    maxima_pages = np.argmax(exact_pages, axis=1)
                    oracle_pages = len(set(maxima_pages.tolist()))
                    false_threats = [
                        int(np.sum(multi_upper[cell] > exact_pages[cell, maxima_pages[cell]]))
                        for cell in range(len(query))
                    ]
                    query_state_bytes += len(query) * 16 + len(pages) * 16
                    for schedule in totals:
                        exact_result = safe_read(query, tokens, pages, exact_pages.astype(np.float64), schedule)
                        multi_result = safe_read(query, tokens, pages, multi_upper, schedule)
                        single_result = safe_read(query, tokens, pages, single_upper, schedule)
                        assert exact_result["exact"] == 1.0
                        assert multi_result["exact"] == 1.0
                        assert single_result["exact"] == 1.0
                        state = totals[schedule]
                        state["full_pages"] += len(pages)
                        state["oracle_pages"] += oracle_pages
                        state["a0_pages"] += int(exact_result["pages"])
                        state["a1_pages"] += int(multi_result["pages"])
                        state["single_pages"] += int(single_result["pages"])
                        state["violations"] += violations
                        state["multi_slack"].extend((multi_upper - exact_pages).ravel().tolist())
                        state["single_slack"].extend((single_upper - exact_pages).ravel().tolist())
                        state["false_threats"].extend(false_threats)
                        state["certificate_margins"].extend((multi_upper - exact_pages).ravel().tolist())
                        state["bound_seconds"] += bound_seconds
                        state["scan_seconds"] += float(multi_result["scan_seconds"])
                        state["priority_seconds"] += float(multi_result["priority_seconds"])
                for schedule, state in totals.items():
                    online_cpu_ms = 1000.0 * (state["bound_seconds"] + state["scan_seconds"] + state["priority_seconds"])
                    all_rows.append({
                        "representation": rep_name,
                        "k": k,
                        "query": qi,
                        "schedule": schedule,
                        "full_pages": state["full_pages"],
                        "single_ball_pages": state["single_pages"],
                        "exact_envelope_pages": state["a0_pages"],
                        "page_oracle_pages": state["oracle_pages"],
                        "multiball_pages": state["a1_pages"],
                        "multiball_fraction": state["a1_pages"] / state["full_pages"],
                        "pages_saved": state["full_pages"] - state["a1_pages"],
                        "certificate_violations": state["violations"],
                        "min_certificate_margin": float(np.min(state["certificate_margins"])),
                        "single_slack_mean": float(np.mean(state["single_slack"])),
                        "multi_slack_mean": float(np.mean(state["multi_slack"])),
                        "multi_slack_p95": float(np.percentile(state["multi_slack"], 95)),
                        "false_threatening_pages_mean": float(np.mean(state["false_threats"])),
                        "bound_cpu_ms": 1000.0 * state["bound_seconds"],
                        "scan_cpu_ms": 1000.0 * state["scan_seconds"],
                        "priority_cpu_ms": 1000.0 * state["priority_seconds"],
                        "online_cpu_ms": online_cpu_ms,
                        "persistent_synopsis_bytes": control["persistent_bytes"],
                        "dram_control_bytes": control["decoded_codebook_dram_bytes"] + control["pair_table_dram_bytes"],
                        "query_state_bytes": query_state_bytes,
                        "outer_topk_overlap": outer_overlap,
                    })
            write_csv(args.results / "stage_a_detail.csv", all_rows)
            write_csv(args.results / "stage_a_models.csv", model_rows)

    if args.phase == "a0":
        write_csv(args.results / "stage_a_a0_detail.csv", a0_rows)
        write_csv(args.results / "stage_a_a0_models.csv", model_rows)
        summaries = []
        for rep in sorted({row["representation"] for row in a0_rows}):
            for k in sorted({int(row["k"]) for row in a0_rows if row["representation"] == rep}):
                selected = [row for row in a0_rows if row["representation"] == rep and int(row["k"]) == k]
                summaries.append({
                    "representation": rep,
                    "k": k,
                    **{key: float(np.mean([float(row[key]) for row in selected])) for key in ("full_pages", "exact_envelope_pages", "page_oracle_pages", "exact_fraction")},
                })
        output = {"seed": SEED, "phase": "a0", "summaries": summaries, "models": model_rows}
        (args.results / "stage_a_a0_summary.json").write_text(json.dumps(output, indent=2) + "\n")
        print(json.dumps(output, indent=2), flush=True)
        return

    summary_rows: list[dict] = []
    for rep in sorted({row["representation"] for row in all_rows}):
        for k in sorted({int(row["k"]) for row in all_rows if row["representation"] == rep}):
            for schedule in ("sequential", "best_upper"):
                selected = [row for row in all_rows if row["representation"] == rep and int(row["k"]) == k and row["schedule"] == schedule]
                summary_rows.append({
                    "representation": rep,
                    "k": k,
                    "schedule": schedule,
                    **{
                        key: float(np.mean([float(row[key]) for row in selected]))
                        for key in (
                            "full_pages", "single_ball_pages", "exact_envelope_pages", "page_oracle_pages",
                            "multiball_pages", "multiball_fraction", "pages_saved", "certificate_violations",
                            "min_certificate_margin",
                            "single_slack_mean", "multi_slack_mean", "multi_slack_p95",
                            "false_threatening_pages_mean", "bound_cpu_ms", "scan_cpu_ms", "priority_cpu_ms",
                            "online_cpu_ms", "persistent_synopsis_bytes", "dram_control_bytes", "query_state_bytes",
                            "outer_topk_overlap",
                        )
                    },
                })
    write_csv(args.results / "stage_a_summary.csv", summary_rows)
    output = {"seed": SEED, "summaries": summary_rows, "models": model_rows}
    (args.results / "stage_a_summary.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2), flush=True)


if __name__ == "__main__":
    main()
