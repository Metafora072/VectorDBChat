#!/usr/bin/env python3
"""Convert validated ordered lifecycle JSONL to timestamp-free Z0BLIFE1."""

from __future__ import annotations

import argparse
import json
import os
import struct
from pathlib import Path


HEADER = struct.Struct("<8sIIQQ")
RECORD = struct.Struct("<QQQQQHHI")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ordered-lifecycle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.ordered_lifecycle.read_text().splitlines() if line.strip()]
    if len(rows) < 2 or rows[0].get("record_type") != "lifecycle_header":
        raise SystemExit("lifecycle header missing")
    if rows[-1].get("record_type") != "lifecycle_trailer" or rows[-1].get("status") != "complete":
        raise SystemExit("lifecycle trailer incomplete")
    header, trailer, events = rows[0], rows[-1], rows[1:-1]
    run_hash = int(header["run_hash"])
    expected_count = int(header.get("record_count", -1))
    if int(header.get("dropped", -1)) != 0 or expected_count != len(events) or int(trailer.get("record_count", -1)) != len(events):
        raise SystemExit("lifecycle count/drop closure failed")
    packed: list[bytes] = []
    sequence: list[int] = []
    for row in events:
        if row.get("record_type") != "lifecycle_event" or row.get("event_kind") != "TRUNCATE":
            raise SystemExit("only ordered TRUNCATE is supported by Z0B")
        if int(row.get("run_hash", -1)) != run_hash or int(row.get("status", -1)) != 0:
            raise SystemExit("lifecycle identity/status closure failed")
        seq = int(row["global_seq"])
        if seq <= 0:
            raise SystemExit("non-positive lifecycle sequence")
        sequence.append(seq)
        new_size = int(row["new_size_bytes"])
        if new_size < 0:
            raise SystemExit("negative truncate size")
        packed.append(
            RECORD.pack(
                seq,
                int(row["object_incarnation"]),
                new_size,
                int(row.get("update_or_replacement_id", 0)),
                int(row.get("batch_id", 0)),
                1,
                int(row.get("file_role", 0)),
                0,
            )
        )
    if sequence != sorted(sequence) or len(sequence) != len(set(sequence)):
        raise SystemExit("lifecycle sequence is not strict")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(args.output, flags, 0o644)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(HEADER.pack(b"Z0BLIFE1", 1, RECORD.size, len(packed), run_hash))
            stream.writelines(packed)
    except BaseException:
        args.output.unlink(missing_ok=True)
        raise
    summary = {
        "schema": "zns-ann-z0b-compact-lifecycle-v1",
        "status": "pass",
        "sequence_only": True,
        "temporal_fields_emitted": False,
        "run_hash": run_hash,
        "event_count": len(events),
        "event_kinds": {"TRUNCATE": len(events)} if events else {},
        "global_sequence_min": min(sequence) if sequence else None,
        "global_sequence_max": max(sequence) if sequence else None,
        "record_bytes": RECORD.size,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    with args.summary.open("x") as stream:
        json.dump(summary, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"status": "pass", "events": len(events)}, sort_keys=True))


if __name__ == "__main__":
    main()
