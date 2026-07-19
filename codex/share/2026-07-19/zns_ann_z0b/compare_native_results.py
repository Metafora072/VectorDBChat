#!/usr/bin/env python3
"""Fail-closed exact comparison of main and independent native Z0B results."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


CYCLE_FIELDS = (
    "cycle_index", "start", "last_append_before_gc", "gc_trigger",
    "allocated_new_blocks", "allocated_new_append_bytes", "application_returned_bytes",
    "relocated_pages", "relocation_allocated_bytes", "host_wa_fraction",
    "victim_zone", "relocation_destination", "victim_valid_fraction",
    "free_zones_before_gc", "free_zones_after_reset", "victim_role_pages",
    "update_id_ranges", "batch_id_ranges",
)


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def projection(payload: dict) -> dict:
    required = {
        "status", "sequence_only", "temporal_fields_used", "placement", "random_seed",
        "cleaner", "initial_image", "bytes", "host_wa_fraction", "reset_count",
        "complete_cycle_count", "tail", "victim_sequence", "cycles", "final_state_sha256",
        "transition_rolling_sha256",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"result missing fields: {missing}")
    if payload["status"] != "pass" or payload["sequence_only"] is not True or payload["temporal_fields_used"] is not False:
        raise ValueError("result status/sequence-only contract failure")
    cycles = payload["cycles"]
    if not isinstance(cycles, list) or len(cycles) != payload["complete_cycle_count"]:
        raise ValueError("cycle count closure failure")
    projected_cycles = []
    for index, row in enumerate(cycles, 1):
        missing_cycle = [field for field in CYCLE_FIELDS if field not in row]
        if missing_cycle:
            raise ValueError(f"cycle {index} missing fields: {missing_cycle}")
        projected_cycles.append({field: row[field] for field in CYCLE_FIELDS})
    return {
        "status": payload["status"], "sequence_only": payload["sequence_only"],
        "temporal_fields_used": payload["temporal_fields_used"],
        "placement": payload["placement"], "random_seed": payload["random_seed"],
        "cleaner": payload["cleaner"], "initial_image": payload["initial_image"],
        "bytes": payload["bytes"], "host_wa_fraction": payload["host_wa_fraction"],
        "reset_count": payload["reset_count"],
        "complete_cycle_count": payload["complete_cycle_count"], "tail": payload["tail"],
        "victim_sequence": payload["victim_sequence"], "cycles": projected_cycles,
        "final_state_sha256": payload["final_state_sha256"],
        "transition_rolling_sha256": payload["transition_rolling_sha256"],
    }


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    if path.exists() or temporary.exists():
        raise ValueError(f"refusing output reuse: {path}")
    with temporary.open("x") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main_payload = json.loads(args.main.read_text())
    reference_payload = json.loads(args.reference.read_text())
    if main_payload.get("schema") != "zns-ann-z0b-native-replay-v1" or main_payload.get("engine") != "main":
        raise ValueError("main schema/engine mismatch")
    if reference_payload.get("schema") != "zns-ann-z0b-native-reference-v1" or reference_payload.get("engine") != "reference":
        raise ValueError("reference schema/engine mismatch")
    primary = projection(main_payload)
    reference = projection(reference_payload)
    if primary != reference:
        for key in primary:
            if primary[key] != reference.get(key):
                raise ValueError(f"native main/reference mismatch at {key}")
        raise ValueError("native main/reference mismatch")
    result = {
        "schema": "zns-ann-z0b-native-exact-comparison-v1", "status": "pass",
        "primary_equals_reference": True, "comparison_semantics": "exact-json-value",
        "main_sha256": sha256_path(args.main), "reference_sha256": sha256_path(args.reference),
        "placement": primary["placement"], "random_seed": primary["random_seed"],
        "cleaner": primary["cleaner"], "complete_cycle_count": primary["complete_cycle_count"],
        "final_state_sha256": primary["final_state_sha256"],
        "transition_rolling_sha256": primary["transition_rolling_sha256"],
    }
    atomic_json(args.output, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"compare_native_results: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
