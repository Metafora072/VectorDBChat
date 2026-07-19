#!/usr/bin/env python3
"""Sequence-only audit for Z0A FULL traces.

The audit deliberately uses no wall-clock timestamp.  A page-version event is
ordered by ``(submit_seq, page_index_within_request)``.  Control runs without a
raw trace are retained as aggregate-only observations; the script never claims
that SHIM/NATIVE have an unobserved request order.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import itertools
import json
import math
import statistics
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


PAGE = 4096
UINT64_MAX = (1 << 64) - 1
PAGE_RECORD = struct.Struct("<QQQQQII")


class RawHeader(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("magic", ctypes.c_char * 8),
        ("version", ctypes.c_uint32),
        ("header_bytes", ctypes.c_uint32),
        ("record_bytes", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
        ("record_count", ctypes.c_uint64),
        ("capacity", ctypes.c_uint64),
        ("dropped", ctypes.c_uint64),
        ("buffer_bytes", ctypes.c_uint64),
        ("run_hash", ctypes.c_uint64),
        ("run_id", ctypes.c_char * 96),
        ("system", ctypes.c_char * 16),
    ]


class RawRecord(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("request_id", ctypes.c_uint64),
        ("submit_seq", ctypes.c_uint64),
        ("completion_seq", ctypes.c_uint64),
        ("thread_seq", ctypes.c_uint64),
        ("thread_id", ctypes.c_uint64),
        ("submit_timestamp_ns", ctypes.c_uint64),
        ("completion_timestamp_ns", ctypes.c_uint64),
        ("run_hash", ctypes.c_uint64),
        ("object_incarnation", ctypes.c_uint64),
        ("device_id", ctypes.c_uint64),
        ("inode", ctypes.c_uint64),
        ("offset", ctypes.c_uint64),
        ("length", ctypes.c_uint64),
        ("returned_bytes", ctypes.c_int64),
        ("completion_status", ctypes.c_int64),
        ("update_or_replacement_id", ctypes.c_uint64),
        ("batch_id", ctypes.c_uint64),
        ("path_hash", ctypes.c_uint64),
        ("flags", ctypes.c_uint32),
        ("system", ctypes.c_uint16),
        ("phase", ctypes.c_uint16),
        ("source_entrypoint", ctypes.c_uint16),
        ("file_role", ctypes.c_uint16),
    ]


def c_string(value: bytes) -> str:
    return value.split(b"\0", 1)[0].decode("utf-8")


def quantiles(values: Iterable[int | float]) -> dict[str, float | int | None]:
    rows = sorted(values)
    if not rows:
        return {key: None for key in ("min", "p25", "p50", "p75", "p90", "p95", "p99", "max", "mean")}

    def linear(q: float) -> float:
        position = (len(rows) - 1) * q
        lo = math.floor(position)
        hi = math.ceil(position)
        if lo == hi:
            return float(rows[lo])
        return float(rows[lo]) * (hi - position) + float(rows[hi]) * (position - lo)

    return {
        "min": rows[0],
        "p25": linear(0.25),
        "p50": linear(0.50),
        "p75": linear(0.75),
        "p90": linear(0.90),
        "p95": linear(0.95),
        "p99": linear(0.99),
        "max": rows[-1],
        "mean": statistics.fmean(rows),
    }


def histogram(values: Iterable[int]) -> dict[str, int]:
    counts = Counter(values)
    return {str(key): counts[key] for key in sorted(counts)}


def distribution(values: list[int]) -> dict[str, Any]:
    return {
        "population": len(values),
        "summary": quantiles(values),
        "histogram": histogram(values),
    }


def semantic_objects(meta_path: Path) -> dict[int, tuple[int, str]]:
    meta = json.loads(meta_path.read_text())
    result: dict[int, tuple[int, str]] = {}
    for item in meta.get("objects", []):
        # Basename plus role is independent of the randomized clone/run path.
        result[int(item["incarnation"])] = (
            int(item.get("initial_role", 0)), Path(item["path"]).name
        )
    return result


def read_raw(path: Path) -> tuple[RawHeader, list[RawRecord]]:
    raw = path.read_bytes()
    header_size = ctypes.sizeof(RawHeader)
    record_size = ctypes.sizeof(RawRecord)
    if len(raw) < header_size:
        raise ValueError(f"{path}: short raw header")
    header = RawHeader.from_buffer_copy(raw[:header_size])
    if bytes(header.magic) != b"Z0ATRCE1" or header.version != 1:
        raise ValueError(f"{path}: unsupported raw magic/version")
    if header.header_bytes != header_size or header.record_bytes != record_size:
        raise ValueError(f"{path}: raw ABI size mismatch")
    expected = header.header_bytes + header.record_count * header.record_bytes
    if len(raw) != expected:
        raise ValueError(f"{path}: raw length mismatch, {len(raw)} != {expected}")
    records = []
    for index in range(header.record_count):
        begin = header.header_bytes + index * header.record_bytes
        records.append(RawRecord.from_buffer_copy(raw[begin : begin + record_size]))
    return header, records


def read_pages(path: Path) -> list[tuple[int, int, int, int, int, int, int]]:
    raw = path.read_bytes()
    if len(raw) < 24 or raw[:8] != b"Z0APAGE1":
        raise ValueError(f"{path}: bad normalized page header")
    version, record_bytes, count = struct.unpack_from("<IIQ", raw, 8)
    if version != 1 or record_bytes != PAGE_RECORD.size:
        raise ValueError(f"{path}: normalized page ABI mismatch")
    if len(raw) != 24 + count * record_bytes:
        raise ValueError(f"{path}: normalized page length mismatch")
    return [PAGE_RECORD.unpack_from(raw, 24 + i * record_bytes) for i in range(count)]


def accepted_aggregate(run_dir: Path) -> dict[str, Any]:
    profile_path = run_dir / "accepted_m0_profile.json"
    if not profile_path.exists():
        return {"available": False}
    profile = json.loads(profile_path.read_text())
    accepted_summary_path = run_dir / "accepted_summary.json"
    accepted_summary = json.loads(accepted_summary_path.read_text()) if accepted_summary_path.exists() else {}
    active_path = run_dir / "active_audit.json"
    active = json.loads(active_path.read_text()) if active_path.exists() else {}
    ledgers = profile.get("ledger_totals", {})
    buckets = profile.get("buckets", [])
    return {
        "available": True,
        "application_bytes": sum(int(row.get("requested_bytes", 0)) for row in ledgers.values()),
        "request_count": sum(int(row.get("request_count", 0)) for row in ledgers.values()),
        "page_event_count": sum(int(row.get("page_write_touches", 0)) for row in buckets),
        "unique_pages_sum_by_phase_bucket": sum(int(row.get("unique_4k_pages", 0)) for row in buckets),
        "phase_request_touches": dict(sorted(Counter({
            str(phase): sum(int(row.get("request_touches", 0)) for row in buckets if str(row.get("phase")) == str(phase))
            for phase in {row.get("phase") for row in buckets}
        }).items())),
        "phase_bytes": dict(sorted(Counter({
            str(phase): sum(int(row.get("requested_bytes", 0)) for row in buckets if str(row.get("phase")) == str(phase))
            for phase in {row.get("phase") for row in buckets}
        }).items())),
        "accepted_phase_counts": accepted_summary.get("phase_counts"),
        "accepted_role_counts": accepted_summary.get("role_counts"),
        "active_set": {
            "count": active.get("actual_count"),
            "sorted_sha256": active.get("actual_sorted_sha256"),
            "exact_match_to_workload_oracle": active.get("exact_match"),
        } if active else None,
    }


def infer_identity(run_dir: Path) -> tuple[str, str]:
    name = run_dir.name.lower()
    system = "DGAI" if "dgai" in name else "OdinANN" if "odin" in name else "unknown"
    if any(token in name for token in ("full", "-on-")):
        mode = "FULL"
    elif "shim" in name:
        mode = "SHIM-CONTROL"
    elif "native" in name:
        mode = "NATIVE"
    elif "-off-" in name:
        mode = "CONTROL-UNSPECIFIED"
    else:
        mode = "unknown"
    return system, mode


def audit_full(run_dir: Path, label: str, system: str, mode: str) -> dict[str, Any]:
    raw_path = run_dir / "raw_trace.bin"
    pages_path = run_dir / "normalized_pages.bin"
    meta_path = run_dir / "trace_meta.json"
    header, records = read_raw(raw_path)
    pages = read_pages(pages_path)
    request_map = {int(row.request_id): row for row in records}
    if len(request_map) != len(records):
        raise ValueError(f"{label}: duplicate request id")
    objects = semantic_objects(meta_path)
    if header.dropped:
        raise ValueError(f"{label}: dropped events={header.dropped}")

    observed_order = [(int(row[1]), int(row[5])) for row in pages]
    sorted_order = sorted(observed_order)
    order_matches_file = observed_order == sorted_order
    if len(set(observed_order)) != len(observed_order):
        raise ValueError(f"{label}: duplicate (submit_seq,page_index) event order")
    pages = sorted(pages, key=lambda row: (row[1], row[5]))

    versions: Counter[tuple[int, str, int]] = Counter()
    positions: defaultdict[tuple[int, str, int], list[int]] = defaultdict(list)
    phase_pages: defaultdict[int, Counter[tuple[int, str, int]]] = defaultdict(Counter)
    update_pages: defaultdict[int, list[tuple[int, str, int]]] = defaultdict(list)
    update_requests: defaultdict[int, set[int]] = defaultdict(set)
    update_bytes: Counter[int] = Counter()
    canonical = hashlib.sha256()
    normalized_bytes = 0
    full_page_events = 0
    missing_objects: set[int] = set()

    for ordinal, page in enumerate(pages):
        request_id, submit_seq, run_hash, incarnation, offset, page_index, page_bytes = map(int, page)
        record = request_map.get(request_id)
        if record is None:
            raise ValueError(f"{label}: normalized request {request_id} missing from raw trace")
        if submit_seq != record.submit_seq or run_hash != header.run_hash or incarnation != record.object_incarnation:
            raise ValueError(f"{label}: raw/normalized identity mismatch for request {request_id}")
        if incarnation not in objects:
            missing_objects.add(incarnation)
            semantic_role, semantic_name = int(record.file_role), f"incarnation-{incarnation}"
        else:
            semantic_role, semantic_name = objects[incarnation]
        key = (semantic_role, semantic_name, offset)
        versions[key] += 1
        positions[key].append(ordinal)
        phase_pages[int(record.phase)][key] += 1
        normalized_bytes += page_bytes
        full_page_events += int(page_bytes == PAGE)
        update_id = int(record.update_or_replacement_id)
        if update_id != UINT64_MAX:
            update_pages[update_id].append(key)
            update_requests[update_id].add(request_id)
            update_bytes[update_id] += page_bytes
        canonical.update(json.dumps([
            semantic_role, semantic_name, offset, page_index, page_bytes,
            int(record.phase), int(record.source_entrypoint), int(record.file_role),
            None if update_id == UINT64_MAX else update_id,
            None if int(record.batch_id) == UINT64_MAX else int(record.batch_id),
        ], separators=(",", ":")).encode())
        canonical.update(b"\n")

    successful_bytes = sum(max(0, int(row.returned_bytes)) for row in records)
    if successful_bytes != normalized_bytes:
        raise ValueError(f"{label}: raw/normalized byte closure failed")

    version_values = list(versions.values())
    reuse_gaps = [
        right - left - 1
        for page_positions in positions.values()
        for left, right in zip(page_positions, page_positions[1:])
    ]
    repeated_spans = [row[-1] - row[0] for row in positions.values() if len(row) > 1]
    all_spans = [row[-1] - row[0] for row in positions.values()]
    fanout_unique = [len(set(keys)) for keys in update_pages.values()]
    fanout_events = [len(keys) for keys in update_pages.values()]
    fanout_requests = [len(update_requests[key]) for key in update_pages]

    phase_concentration: dict[str, Any] = {}
    for phase, counts in sorted(phase_pages.items()):
        total = sum(counts.values())
        ordered = sorted(counts.values(), reverse=True)
        top_one_percent_n = max(1, math.ceil(len(ordered) * 0.01))
        phase_concentration[str(phase)] = {
            "page_events": total,
            "unique_pages": len(counts),
            "repeat_fraction": 1.0 - len(counts) / total,
            "hhi": sum((value / total) ** 2 for value in ordered),
            "top1_share": ordered[0] / total,
            "top10_share": sum(ordered[:10]) / total,
            "top1pct_share": sum(ordered[:top_one_percent_n]) / total,
        }

    app = accepted_aggregate(run_dir)
    allocated = len(pages) * PAGE
    result = {
        "label": label,
        "run_dir": str(run_dir.resolve()),
        "system": system,
        "mode": mode,
        "trace_available": True,
        "ordering": {
            "definition": "lexicographic (submit_seq, page_index_within_request)",
            "normalized_file_already_in_definition_order": order_matches_file,
            "timestamps_used": False,
        },
        "closure": {
            "raw_requests": len(records),
            "page_events": len(pages),
            "application_returned_bytes": successful_bytes,
            "normalized_mutation_bytes": normalized_bytes,
            "accepted_aggregate": app,
            "raw_normalized_byte_closure": successful_bytes == normalized_bytes,
            "raw_accepted_byte_closure": not app.get("available") or successful_bytes == app["application_bytes"],
            "missing_semantic_objects": sorted(missing_objects),
        },
        "materialization_4k": {
            "semantic": "one reconstructed complete 4096-byte logical page image per normalized page event",
            "application_mutation_bytes": normalized_bytes,
            "allocated_append_bytes": allocated,
            "unchanged_bytes_reconstructed": allocated - normalized_bytes,
            "full_page_events": full_page_events,
            "partial_page_events": len(pages) - full_page_events,
            "host_write_amplification_over_application_bytes": allocated / normalized_bytes if normalized_bytes else None,
            "accounting_warning": "application mutation bytes are not logical append bytes; partial events require merge with the current page image before append",
        },
        "sequence_fingerprint_sha256": canonical.hexdigest(),
        "metrics": {
            "versions_per_page": distribution(version_values),
            "sequence_reuse_distance_events_between_versions": distribution(reuse_gaps),
            "per_update_unique_page_fanout": distribution(fanout_unique),
            "per_update_page_event_fanout": distribution(fanout_events),
            "per_update_request_fanout": distribution(fanout_requests),
            "updates_with_explicit_id": len(update_pages),
            "explicit_update_mutation_bytes": sum(update_bytes.values()),
            "phase_local_page_concentration": phase_concentration,
            "first_last_version_sequence_span_repeated_pages": distribution(repeated_spans),
            "first_last_version_sequence_span_all_pages": distribution(all_spans),
        },
    }
    return result


def audit_run(spec: str) -> dict[str, Any]:
    # LABEL[:SYSTEM:MODE]=DIRECTORY.  The short DIRECTORY-only form infers all fields.
    if "=" in spec:
        identity, directory = spec.split("=", 1)
        parts = identity.split(":")
        label = parts[0]
        run_dir = Path(directory)
        inferred_system, inferred_mode = infer_identity(run_dir)
        system = parts[1] if len(parts) > 1 and parts[1] else inferred_system
        mode = parts[2] if len(parts) > 2 and parts[2] else inferred_mode
    else:
        run_dir = Path(spec)
        label = run_dir.name
        system, mode = infer_identity(run_dir)
    if not run_dir.is_dir():
        raise ValueError(f"{label}: no run directory {run_dir}")
    if (run_dir / "raw_trace.bin").exists():
        for required in ("normalized_pages.bin", "trace_meta.json"):
            if not (run_dir / required).exists():
                raise ValueError(f"{label}: FULL trace lacks {required}")
        return audit_full(run_dir, label, system, mode)
    return {
        "label": label,
        "run_dir": str(run_dir.resolve()),
        "system": system,
        "mode": mode,
        "trace_available": False,
        "accepted_aggregate": accepted_aggregate(run_dir),
        "sequence_claim_permitted": False,
        "reason": "control has no append records; only aggregate FULL/control structure may be compared",
    }


def total_variation(left: dict[str, int], right: dict[str, int]) -> float | None:
    left_total, right_total = sum(left.values()), sum(right.values())
    if not left_total or not right_total:
        return None
    keys = set(left) | set(right)
    return 0.5 * sum(abs(left.get(key, 0) / left_total - right.get(key, 0) / right_total) for key in keys)


def ordinal_distances(left: dict[str, int], right: dict[str, int]) -> dict[str, float | None]:
    """Distribution distances for integer-valued metrics, without a pass threshold."""
    left_total, right_total = sum(left.values()), sum(right.values())
    if not left_total or not right_total:
        return {"total_variation": None, "ks": None, "wasserstein1": None, "wasserstein1_over_pooled_mean": None}
    left_int = {int(key): value for key, value in left.items()}
    right_int = {int(key): value for key, value in right.items()}
    keys = sorted(set(left_int) | set(right_int))
    left_cdf = right_cdf = 0.0
    ks = 0.0
    w1 = 0.0
    last = keys[0]
    for key in keys:
        w1 += abs(left_cdf - right_cdf) * (key - last)
        left_cdf += left_int.get(key, 0) / left_total
        right_cdf += right_int.get(key, 0) / right_total
        ks = max(ks, abs(left_cdf - right_cdf))
        last = key
    left_mean = sum(key * value for key, value in left_int.items()) / left_total
    right_mean = sum(key * value for key, value in right_int.items()) / right_total
    pooled_mean = (left_mean + right_mean) / 2
    return {
        "total_variation": total_variation(left, right),
        "ks": ks,
        "wasserstein1": w1,
        "wasserstein1_over_pooled_mean": w1 / pooled_mean if pooled_mean else None,
    }


def compare_full(runs: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        if run.get("trace_available"):
            groups[run["system"]].append(run)
    metric_names = (
        "versions_per_page",
        "sequence_reuse_distance_events_between_versions",
        "per_update_unique_page_fanout",
        "per_update_page_event_fanout",
        "first_last_version_sequence_span_repeated_pages",
    )
    output: dict[str, Any] = {}
    for system, rows in sorted(groups.items()):
        fingerprints = {row["sequence_fingerprint_sha256"] for row in rows}
        pairwise: dict[str, list[dict[str, Any]]] = {name: [] for name in metric_names}
        for left, right in itertools.combinations(rows, 2):
            for name in metric_names:
                distances = ordinal_distances(
                    left["metrics"][name]["histogram"], right["metrics"][name]["histogram"]
                )
                pairwise[name].append({"left": left["label"], "right": right["label"], **distances})
        phase_pairs = []
        for left, right in itertools.combinations(rows, 2):
            left_phases = left["metrics"]["phase_local_page_concentration"]
            right_phases = right["metrics"]["phase_local_page_concentration"]
            shared_phases = sorted(set(left_phases) & set(right_phases))
            phase_pairs.append({
                "left": left["label"], "right": right["label"],
                "phase_absolute_deltas": {
                    phase: {
                        field: abs(float(left_phases[phase][field]) - float(right_phases[phase][field]))
                        for field in ("repeat_fraction", "hhi", "top1_share", "top10_share", "top1pct_share")
                    }
                    for phase in shared_phases
                },
                "phase_sets_equal": set(left_phases) == set(right_phases),
            })
        output[system] = {
            "full_run_count": len(rows),
            "all_sequence_fingerprints_equal": len(fingerprints) <= 1,
            "distinct_sequence_fingerprint_count": len(fingerprints),
            "pairwise_distribution_distance": pairwise,
            "pairwise_phase_local_concentration_delta": phase_pairs,
            "interpretation": (
                "DGAI may use exact equality; OdinANN distances describe natural FULL-run variability and have no invented pass threshold."
            ),
        }
    return output


def compare_aggregates(runs: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for run in runs:
        aggregate = run.get("closure", {}).get("accepted_aggregate") if run.get("trace_available") else run.get("accepted_aggregate")
        if aggregate and aggregate.get("available"):
            rows.append({
                "label": run["label"], "system": run["system"], "mode": run["mode"],
                **{key: aggregate[key] for key in (
                    "application_bytes", "request_count", "page_event_count",
                    "unique_pages_sum_by_phase_bucket", "phase_request_touches", "phase_bytes",
                    "accepted_phase_counts", "accepted_role_counts", "active_set"
                )},
            })
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["system"]].append(row)
    result = {}
    for system, system_rows in sorted(groups.items()):
        signatures = {
            json.dumps({key: row[key] for key in (
                "application_bytes", "request_count", "page_event_count",
                "unique_pages_sum_by_phase_bucket", "phase_request_touches", "phase_bytes",
                "accepted_phase_counts", "accepted_role_counts", "active_set"
            )}, sort_keys=True)
            for row in system_rows
        }
        result[system] = {
            "runs": system_rows,
            "all_accepted_aggregate_signatures_equal": len(signatures) <= 1,
            "distinct_accepted_aggregate_signature_count": len(signatures),
            "scope_warning": "this establishes aggregate structure only, never an unrecorded SHIM/NATIVE order",
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", action="append", required=True,
        help="DIRECTORY or LABEL[:SYSTEM:MODE]=DIRECTORY; repeat for every FULL/control run",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runs = [audit_run(spec) for spec in args.run]
    report = {
        "schema": "zns-ann-z0a-sequence-structure-audit-v1",
        "decision_scope": "sequence-only structural audit; no wall-clock timing, GC, simulator state, or age claim",
        "runs": runs,
        "aggregate_full_control_comparison": compare_aggregates(runs),
        "full_trace_sequence_comparison": compare_full(runs),
        "claim_boundary": {
            "permitted": [
                "accepted aggregate comparison across FULL/SHIM/NATIVE",
                "submit-sequence distributions and exact fingerprints across repeated FULL traces",
                "full-page materialization byte accounting",
            ],
            "not_permitted": [
                "SHIM/NATIVE sequence equality when those controls record no requests",
                "wall-clock age, timestamp, timing, GC, relocation, or lifetime claim",
                "Z0B authorization",
            ],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(args.output),
        "runs": len(runs),
        "full_runs": sum(bool(row.get("trace_available")) for row in runs),
        "systems": sorted({row["system"] for row in runs}),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
