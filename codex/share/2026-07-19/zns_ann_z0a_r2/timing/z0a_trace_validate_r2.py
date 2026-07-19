#!/usr/bin/env python3
"""Validate a Z0A request trace and normalize successful bytes to 4 KiB pages."""

from __future__ import annotations

import argparse
import ctypes
import json
import struct
from collections import Counter
from pathlib import Path


class Header(ctypes.LittleEndianStructure):
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


class Record(ctypes.LittleEndianStructure):
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


PAGE = 4096
PAGE_STRUCT = struct.Struct("<QQQQQII")


def c_string(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("utf-8")


def inversions(records: list[Record], seq_name: str, timestamp_name: str) -> int:
    ordered = sorted(records, key=lambda row: getattr(row, seq_name))
    return sum(
        getattr(right, timestamp_name) < getattr(left, timestamp_name)
        for left, right in zip(ordered, ordered[1:])
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--pages-output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--accepted-profile", type=Path)
    parser.add_argument("--allow-drops", action="store_true")
    args = parser.parse_args()

    raw = args.trace.read_bytes()
    if len(raw) < ctypes.sizeof(Header):
        raise SystemExit("short trace header")
    header = Header.from_buffer_copy(raw[: ctypes.sizeof(Header)])
    if bytes(header.magic) != b"Z0ATRCE1" or header.version != 1:
        raise SystemExit("trace magic/version mismatch")
    if header.header_bytes != ctypes.sizeof(Header) or header.record_bytes != ctypes.sizeof(Record):
        raise SystemExit("trace ABI size mismatch")
    expected = header.header_bytes + header.record_count * header.record_bytes
    if len(raw) != expected or header.record_count > header.capacity:
        raise SystemExit("trace length/capacity mismatch")
    if header.dropped and not args.allow_drops:
        raise SystemExit(f"dropped events: {header.dropped}")

    records: list[Record] = []
    for index in range(header.record_count):
        begin = header.header_bytes + index * header.record_bytes
        records.append(Record.from_buffer_copy(raw[begin : begin + header.record_bytes]))

    request_ids = [row.request_id for row in records]
    submit_seq = [row.submit_seq for row in records]
    complete_seq = [row.completion_seq for row in records if row.flags & 2]
    closure_errors: list[str] = []
    if len(set(request_ids)) != len(request_ids) or min(request_ids, default=1) <= 0:
        closure_errors.append("request_id uniqueness")
    # WRITE submissions share one R2 global order with lifecycle events, so
    # gaps are expected when a TRUNCATE lies between two writes.
    if len(set(submit_seq)) != len(submit_seq) or any(value <= 0 for value in submit_seq):
        closure_errors.append("submit sequence")
    if len(set(complete_seq)) != len(complete_seq) or sorted(complete_seq) != list(range(1, len(complete_seq) + 1)):
        closure_errors.append("completion sequence")
    if any((row.flags & 3) != 3 for row in records):
        closure_errors.append("accepted/completed flags")
    if any(row.run_hash != header.run_hash for row in records):
        closure_errors.append("run hash")
    if any(row.returned_bytes > int(row.length) for row in records):
        closure_errors.append("returned exceeds requested")

    page_count = 0
    page_bytes_total = 0
    successful_bytes = 0
    page_keys: set[tuple[int, int]] = set()
    object_offset_pairs: set[tuple[int, int]] = set()
    args.pages_output.parent.mkdir(parents=True, exist_ok=True)
    with args.pages_output.open("wb") as output:
        output.write(b"Z0APAGE1")
        output.write(struct.pack("<IIQ", 1, PAGE_STRUCT.size, 0))
        for row in records:
            if row.returned_bytes <= 0:
                continue
            remaining = int(row.returned_bytes)
            successful_bytes += remaining
            position = int(row.offset)
            page_index = 0
            request_page_bytes = 0
            while remaining:
                aligned = position // PAGE * PAGE
                amount = min(remaining, PAGE - (position - aligned))
                output.write(
                    PAGE_STRUCT.pack(
                        row.request_id,
                        row.submit_seq,
                        row.run_hash,
                        row.object_incarnation,
                        aligned,
                        page_index,
                        amount,
                    )
                )
                page_count += 1
                page_bytes_total += amount
                request_page_bytes += amount
                page_keys.add((row.object_incarnation, aligned))
                object_offset_pairs.add((row.object_incarnation, int(row.offset)))
                position += amount
                remaining -= amount
                page_index += 1
            if request_page_bytes != row.returned_bytes:
                closure_errors.append(f"request page closure {row.request_id}")
        output.seek(16)
        output.write(struct.pack("<Q", page_count))

    if page_bytes_total != successful_bytes:
        closure_errors.append("global page byte closure")
    accepted_profile_closure = None
    if args.accepted_profile:
        profile = json.loads(args.accepted_profile.read_text())
        ledgers = profile.get("ledger_totals", {})
        accepted_requests = sum(int(row.get("request_count", 0)) for row in ledgers.values())
        accepted_bytes = sum(int(row.get("requested_bytes", 0)) for row in ledgers.values())
        accepted_phase_bytes = Counter()
        for bucket in profile.get("buckets", []):
            accepted_phase_bytes[str(bucket["phase"])] += int(bucket.get("requested_bytes", 0))
        phase_names = {
            0: "other", 1: "load", 2: "insert_neighbor_repair", 3: "delete",
            4: "visibility", 5: "publish_save", 6: "shadow_copy", 7: "repair", 8: "metadata",
        }
        raw_phase_bytes = Counter()
        for row in records:
            if row.returned_bytes > 0:
                raw_phase_bytes[phase_names.get(int(row.phase), "other")] += int(row.returned_bytes)
        accepted_profile_closure = {
            "profile": str(args.accepted_profile.resolve()),
            "request_count": accepted_requests == len(records),
            "returned_bytes": accepted_bytes == successful_bytes,
            "phase_bytes": dict(accepted_phase_bytes) == dict(raw_phase_bytes),
            "accepted_request_count": accepted_requests,
            "accepted_bytes": accepted_bytes,
            "accepted_phase_bytes": dict(accepted_phase_bytes),
            "raw_phase_bytes": dict(raw_phase_bytes),
        }
        if not all(accepted_profile_closure[key] for key in ("request_count", "returned_bytes", "phase_bytes")):
            closure_errors.append("accepted M0 profile closure")
    if closure_errors:
        raise SystemExit("closure failure: " + ", ".join(closure_errors))

    submit_inversions = inversions(records, "submit_seq", "submit_timestamp_ns")
    completed_records = [row for row in records if row.flags & 2]
    completion_inversions = inversions(completed_records, "completion_seq", "completion_timestamp_ns")
    summary = {
        "schema": "zns-ann-z0a-trace-validation-v1",
        "status": "pass",
        "run_id": c_string(bytes(header.run_id)),
        "system": c_string(bytes(header.system)),
        "record_count": len(records),
        "request_count": len(records),
        "page_event_count": page_count,
        "requested_bytes": sum(row.length for row in records),
        "successful_returned_bytes": successful_bytes,
        "normalized_page_bytes": page_bytes_total,
        "unique_logical_pages": len(page_keys),
        "unique_object_offset_pairs": len(object_offset_pairs),
        "object_count": len({row.object_incarnation for row in records}),
        "dropped_events": header.dropped,
        "buffer_peak_bytes": header.buffer_bytes,
        "submit_timestamp_sequence_inversions": submit_inversions,
        "completion_timestamp_sequence_inversions": completion_inversions,
        "phase_counts": dict(Counter(str(row.phase) for row in records)),
        "role_counts": dict(Counter(str(row.file_role) for row in records)),
        "source_counts": dict(Counter(str(row.source_entrypoint) for row in records)),
        "failed_requests": sum(row.returned_bytes < 0 or row.completion_status != 0 for row in records),
        "request_to_page_byte_closure": True,
        "accepted_m0_profile_closure": accepted_profile_closure,
        "stable_page_key": "(run_hash,object_incarnation,aligned_page_offset)",
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
