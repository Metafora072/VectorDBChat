#!/usr/bin/env python3
"""Streaming/NumPy normalizer for Z0B FULL request traces.

The output deliberately excludes every timestamp.  It retains only sequence,
logical-page identity, phase/role and update/batch grouping required by the
sequence-only gate.  The raw input is memory-mapped; no ctypes object is built
per request and no expanded JSON replay specification is emitted.
"""

from __future__ import annotations

import argparse
import json
import struct
from collections import Counter
from pathlib import Path

import numpy as np


PAGE = 4096
RAW_HEADER = struct.Struct("<8sIIIIQQQQQ96s16s")
NORMAL_HEADER = struct.Struct("<8sIIQQ")
NORMAL_MAGIC = b"Z0BNORM1"

RAW_DTYPE = np.dtype(
    [
        ("request_id", "<u8"),
        ("submit_seq", "<u8"),
        ("completion_seq", "<u8"),
        ("thread_seq", "<u8"),
        ("thread_id", "<u8"),
        ("submit_timestamp_ns", "<u8"),
        ("completion_timestamp_ns", "<u8"),
        ("run_hash", "<u8"),
        ("object_incarnation", "<u8"),
        ("device_id", "<u8"),
        ("inode", "<u8"),
        ("offset", "<u8"),
        ("length", "<u8"),
        ("returned_bytes", "<i8"),
        ("completion_status", "<i8"),
        ("update_id", "<u8"),
        ("batch_id", "<u8"),
        ("path_hash", "<u8"),
        ("flags", "<u4"),
        ("system", "<u2"),
        ("phase", "<u2"),
        ("source", "<u2"),
        ("role", "<u2"),
    ],
    align=False,
)

NORMAL_DTYPE = np.dtype(
    [
        ("global_seq", "<u8"),
        ("request_id", "<u8"),
        ("object_incarnation", "<u8"),
        ("aligned_offset", "<u8"),
        ("update_id", "<u8"),
        ("batch_id", "<u8"),
        ("fragment_bytes", "<u4"),
        ("page_index_within_request", "<u4"),
        ("phase", "<u2"),
        ("role", "<u2"),
        ("source", "<u2"),
        ("reserved", "<u2"),
    ],
    align=False,
)


def cstr(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8")


def require_unique_positive(values: np.ndarray, name: str) -> None:
    if values.size == 0:
        return
    ordered = np.sort(values)
    if ordered[0] == 0 or np.any(ordered[1:] == ordered[:-1]):
        raise SystemExit(f"{name} is not positive/unique")


def validate_lifecycle(path: Path, run_hash: int) -> dict[str, object]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if len(rows) < 2 or rows[0].get("record_type") != "lifecycle_header":
        raise SystemExit("lifecycle header absent")
    if rows[-1].get("record_type") != "lifecycle_trailer" or rows[-1].get("status") != "complete":
        raise SystemExit("lifecycle trailer incomplete")
    header, trailer = rows[0], rows[-1]
    events = rows[1:-1]
    if int(header.get("dropped", -1)) != 0:
        raise SystemExit("lifecycle drop")
    if int(header.get("record_count", -1)) != len(events) or int(trailer.get("record_count", -1)) != len(events):
        raise SystemExit("lifecycle count closure")
    seq = [int(row["global_seq"]) for row in events]
    if len(seq) != len(set(seq)) or any(value <= 0 for value in seq):
        raise SystemExit("lifecycle global sequence invalid")
    for row in events:
        if int(row.get("run_hash", -1)) != run_hash or int(row.get("status", -1)) != 0:
            raise SystemExit("lifecycle identity/status closure")
    return {
        "event_count": len(events),
        "global_sequence_min": min(seq) if seq else None,
        "global_sequence_max": max(seq) if seq else None,
        "event_kinds": dict(Counter(str(row.get("event_kind")) for row in events)),
    }


def accepted_profile_closure(path: Path, raw: np.ndarray) -> dict[str, object]:
    profile = json.loads(path.read_text())
    successful = raw["returned_bytes"] > 0
    returned = int(raw["returned_bytes"][successful].sum(dtype=np.int64))
    if profile.get("schema") == "zns-ann-z0a-trace-ledger-v1":
        if (
            profile.get("status") != "complete"
            or int(profile.get("dropped_events", -1)) != 0
            or int(profile.get("lifecycle_dropped_events", -1)) != 0
            or int(profile.get("failed_requests", -1)) != 0
        ):
            raise SystemExit("trace ledger status/drop/failure closure failed")
        accepted_requests = int(profile.get("accepted_requests", -1))
        completed_requests = int(profile.get("completed_requests", -1))
        accepted_bytes = int(profile.get("returned_bytes", -1))
        if completed_requests != accepted_requests:
            raise SystemExit("trace ledger accepted/completed closure failed")
    else:
        ledgers = profile.get("ledger_totals", {})
        accepted_requests = sum(int(row.get("request_count", 0)) for row in ledgers.values())
        accepted_bytes = sum(int(row.get("requested_bytes", 0)) for row in ledgers.values())
    result = {
        "profile": str(path.resolve()),
        "schema": profile.get("schema"),
        "request_count": accepted_requests == int(raw.size),
        "returned_bytes": accepted_bytes == returned,
        "accepted_request_count": accepted_requests,
        "accepted_bytes": accepted_bytes,
    }
    if not result["request_count"] or not result["returned_bytes"]:
        raise SystemExit("accepted profiler closure failed")
    return result


def expand_chunk(raw: np.ndarray, request_indices: np.ndarray, page_indices: np.ndarray) -> np.ndarray:
    rows = raw[request_indices]
    positions = rows["offset"] + page_indices.astype(np.uint64) * PAGE
    aligned = positions // PAGE * PAGE
    consumed_before = aligned + np.where(page_indices == 0, rows["offset"] - aligned, 0) - rows["offset"]
    remaining = rows["returned_bytes"].astype(np.int64) - consumed_before.astype(np.int64)
    first_room = PAGE - (rows["offset"] - (rows["offset"] // PAGE * PAGE))
    room = np.where(page_indices == 0, first_room, PAGE).astype(np.int64)
    fragments = np.minimum(remaining, room)
    if np.any(fragments <= 0) or np.any(fragments > PAGE):
        raise SystemExit("invalid normalized fragment")
    out = np.empty(rows.size, dtype=NORMAL_DTYPE)
    out["global_seq"] = rows["submit_seq"]
    out["request_id"] = rows["request_id"]
    out["object_incarnation"] = rows["object_incarnation"]
    out["aligned_offset"] = aligned
    out["update_id"] = rows["update_id"]
    out["batch_id"] = rows["batch_id"]
    out["fragment_bytes"] = fragments.astype(np.uint32)
    out["page_index_within_request"] = page_indices.astype(np.uint32)
    out["phase"] = rows["phase"]
    out["role"] = rows["role"]
    out["source"] = rows["source"]
    out["reserved"] = 0
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--lifecycle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--accepted-profile", type=Path)
    parser.add_argument("--chunk-events", type=int, default=2_000_000)
    args = parser.parse_args()

    with args.raw.open("rb") as handle:
        header_bytes = handle.read(RAW_HEADER.size)
    if len(header_bytes) != RAW_HEADER.size:
        raise SystemExit("short raw header")
    (magic, version, header_size, record_size, _reserved, count, capacity, dropped,
     buffer_bytes, run_hash, run_id_raw, system_raw) = RAW_HEADER.unpack(header_bytes)
    if magic != b"Z0ATRCE1" or version != 1 or header_size != RAW_HEADER.size:
        raise SystemExit("raw header ABI mismatch")
    if record_size != RAW_DTYPE.itemsize or count > capacity or dropped:
        raise SystemExit("raw record ABI/count/drop failure")
    expected = header_size + count * record_size
    if args.raw.stat().st_size != expected or buffer_bytes != capacity * record_size:
        raise SystemExit("raw size/capacity closure")

    raw = np.memmap(args.raw, dtype=RAW_DTYPE, mode="r", offset=header_size, shape=(count,))
    if np.any((raw["flags"] & 3) != 3) or np.any(raw["completion_status"] != 0):
        raise SystemExit("accepted/completed/status closure")
    if np.any(raw["run_hash"] != run_hash) or np.any(raw["returned_bytes"] > raw["length"].astype(np.int64)):
        raise SystemExit("raw identity/length closure")
    require_unique_positive(raw["request_id"], "request_id")
    require_unique_positive(raw["submit_seq"], "submit_seq")
    require_unique_positive(raw["completion_seq"], "completion_seq")
    completed_sorted = np.sort(raw["completion_seq"])
    if not np.array_equal(completed_sorted, np.arange(1, count + 1, dtype=np.uint64)):
        raise SystemExit("completion sequence is not closed")

    order = np.argsort(raw["submit_seq"], kind="stable")
    ordered = raw[order]
    positive = ordered["returned_bytes"] > 0
    successful_order = order[positive]
    successful_rows = raw[successful_order]
    offsets_in_page = successful_rows["offset"] % PAGE
    page_counts = ((offsets_in_page + successful_rows["returned_bytes"].astype(np.uint64) + PAGE - 1) // PAGE).astype(np.uint32)
    event_count = int(page_counts.sum(dtype=np.uint64))
    starts = np.cumsum(page_counts, dtype=np.uint64) - page_counts

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as output:
        output.write(NORMAL_HEADER.pack(NORMAL_MAGIC, 1, NORMAL_DTYPE.itemsize, event_count, count))
        output.truncate(NORMAL_HEADER.size + event_count * NORMAL_DTYPE.itemsize)
    normalized = np.memmap(
        args.output, dtype=NORMAL_DTYPE, mode="r+", offset=NORMAL_HEADER.size, shape=(event_count,)
    )
    event_cursor = 0
    request_cursor = 0
    while request_cursor < successful_order.size:
        upper = request_cursor
        pages = 0
        while upper < successful_order.size and (pages == 0 or pages + int(page_counts[upper]) <= args.chunk_events):
            pages += int(page_counts[upper])
            upper += 1
        local_counts = page_counts[request_cursor:upper]
        req = np.repeat(successful_order[request_cursor:upper], local_counts)
        local_starts = np.repeat(starts[request_cursor:upper], local_counts)
        page_index = np.arange(starts[request_cursor], starts[request_cursor] + pages, dtype=np.uint64) - local_starts
        normalized[event_cursor:event_cursor + pages] = expand_chunk(raw, req, page_index)
        event_cursor += pages
        request_cursor = upper
    normalized.flush()
    if event_cursor != event_count:
        raise SystemExit("normalized event count closure")

    normalized_view = np.memmap(
        args.output, dtype=NORMAL_DTYPE, mode="r", offset=NORMAL_HEADER.size, shape=(event_count,)
    )
    fragment_bytes = int(normalized_view["fragment_bytes"].sum(dtype=np.uint64))
    returned_bytes = int(raw["returned_bytes"][raw["returned_bytes"] > 0].sum(dtype=np.int64))
    if fragment_bytes != returned_bytes:
        raise SystemExit("raw to normalized byte closure")
    pair_order_ok = bool(
        np.all(normalized_view["global_seq"][1:] >= normalized_view["global_seq"][:-1])
        and np.all(
            np.where(
                normalized_view["global_seq"][1:] == normalized_view["global_seq"][:-1],
                normalized_view["page_index_within_request"][1:] > normalized_view["page_index_within_request"][:-1],
                True,
            )
        )
    ) if event_count > 1 else True
    if not pair_order_ok:
        raise SystemExit("normalized (global_seq,page_index) order failure")

    lifecycle = validate_lifecycle(args.lifecycle, run_hash)
    lifecycle_rows = [json.loads(line) for line in args.lifecycle.read_text().splitlines()[1:-1]]
    ordered_submit = raw["submit_seq"][order]
    for row in lifecycle_rows:
        lifecycle_seq = np.uint64(int(row["global_seq"]))
        position = int(np.searchsorted(ordered_submit, lifecycle_seq))
        if position < ordered_submit.size and ordered_submit[position] == lifecycle_seq:
            raise SystemExit("write/lifecycle global sequence collision")

    summary: dict[str, object] = {
        "schema": "zns-ann-z0b-stream-normalization-v1",
        "status": "pass",
        "sequence_only": True,
        "temporal_fields_emitted": False,
        "run_id": cstr(run_id_raw),
        "system": cstr(system_raw),
        "raw_request_count": int(count),
        "normalized_page_event_count": event_count,
        "application_returned_bytes": returned_bytes,
        "normalized_fragment_bytes": fragment_bytes,
        "allocated_append_bytes": event_count * PAGE,
        "dropped_events": int(dropped),
        "failed_requests": int(np.count_nonzero(raw["returned_bytes"] < 0)),
        "raw_normalized_byte_closure": True,
        "global_sequence_disjoint_with_lifecycle": True,
        "normalized_pair_order": True,
        "lifecycle": lifecycle,
        "phase_request_counts": {str(k): int(v) for k, v in zip(*np.unique(raw["phase"], return_counts=True))},
        "role_request_counts": {str(k): int(v) for k, v in zip(*np.unique(raw["role"], return_counts=True))},
        "source_request_counts": {str(k): int(v) for k, v in zip(*np.unique(raw["source"], return_counts=True))},
    }
    if args.accepted_profile:
        summary["accepted_profile_closure"] = accepted_profile_closure(args.accepted_profile, raw)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "pass", "requests": int(count), "events": event_count}, sort_keys=True))


if __name__ == "__main__":
    main()
