#!/usr/bin/env python3
"""Fast, independently cross-checked primary/reference replay for a real R2 trace."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from r2_reference_sim import Reference
from r2_zns_sim import ZNSSimulator


def digest(keys: list[str]) -> str:
    return hashlib.sha256("\n".join(keys).encode()).hexdigest()


def entry_hash(key: str, value: tuple[int, int, int]) -> int:
    raw = f"{key}\0{value[0]}\0{value[1]}\0{value[2]}".encode()
    return int.from_bytes(hashlib.blake2b(raw, digest_size=16).digest(), "little")


def map_fingerprint(mapping: dict[str, tuple[int, int, int]]) -> int:
    value = 0
    for key, location in mapping.items():
        value ^= entry_hash(key, location)
    return value


def update_fingerprint(value: int, key: str, before: tuple[int, int, int] | None,
                       after: tuple[int, int, int] | None) -> int:
    if before is not None:
        value ^= entry_hash(key, before)
    if after is not None:
        value ^= entry_hash(key, after)
    return value


def apply_primary(sim: ZNSSimulator, event: dict) -> dict:
    action: dict = {"op": event["op"]}
    if event["op"] == "write":
        sim._write(event, action)
    elif event["op"] == "truncate":
        sim._truncate(event, action)
    else:
        raise ValueError(f"unsupported formal event: {event['op']}")
    return action


def apply_reference(ref: Reference, event: dict, fast: dict[str, tuple[int, int, int]]) -> dict:
    action: dict = {"op": event["op"]}
    if event["op"] == "write":
        key = str(event["key"])
        destination = ref.room(action)
        old = fast.get(key)
        version = 1 if old is None else old[0] + 1
        ref.z[destination]["slots"].append([key, version, True, "NEW"])
        slot = len(ref.z[destination]["slots"]) - 1
        if old is not None:
            ref.z[old[1]]["slots"][old[2]][2] = False
        fast[key] = (version, destination, slot)
        ref.user += 1
        ref.appbytes += int(event.get("page_bytes", ref.bs))
        ref.maybe_full(destination)
    elif event["op"] == "truncate":
        keys = [str(key) for key in event.get("invalidated_keys", [])]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate truncate key")
        for key in keys:
            old = fast.pop(key)
            ref.z[old[1]]["slots"][old[2]][2] = False
        action["invalidated_keys"] = keys
    else:
        raise ValueError(f"unsupported formal event: {event['op']}")
    return action


def compare_affected_zones(primary: ZNSSimulator, reference: Reference, zone_ids: set[int], event_index: int) -> None:
    for zid in zone_ids:
        p = primary.zones[zid]
        r = reference.z[zid]
        p_slots = [[s.key, s.version, s.valid, s.kind] for s in p.slots]
        if p.state != r["state"] or p_slots != r["slots"]:
            raise ValueError(f"zone state/slot mismatch at event {event_index}, zone {zid}")
        if p.wp != len(r["slots"]) or p.live != reference.live(zid):
            raise ValueError(f"zone WP/live mismatch at event {event_index}, zone {zid}")


def compare_scalars(primary: ZNSSimulator, reference: Reference, event_index: int) -> None:
    pairs = {
        "initial": (primary.initial_blocks, reference.initial),
        "new": (primary.new_blocks, reference.user),
        "relocated": (primary.relocated_blocks, reference.copied),
        "reset_erased": (primary.reset_erased_blocks, reference.erased),
        "reset_count": (primary.reset_count, reference.resets),
        "application_bytes": (primary.application_bytes, reference.appbytes),
        "current": (primary.current, reference.cur),
        "open": (primary._open_count(), reference.open_count()),
        "active": (primary._active_count(), reference.active_count()),
    }
    bad = {name: values for name, values in pairs.items() if values[0] != values[1]}
    if bad or primary.victim_sequence != reference.victims or primary.relocation_sequence != reference.moved:
        raise ValueError(f"counter/victim/relocation mismatch at event {event_index}: {bad}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--final-live", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    final = json.loads(args.final_live.read_text())
    expected = sorted(row["logical_page_key"] for row in final["pages"])
    reports = {}
    for policy in ("GreedyValidFraction", "OracleMinCopy"):
        primary = ZNSSimulator(spec, policy)
        reference = Reference(spec, policy)
        fast = reference.locations()
        primary_fingerprint = map_fingerprint(primary.mapping)
        reference_fingerprint = map_fingerprint(fast)
        checkpoints = 0
        for index, event in enumerate(spec["events"], 1):
            keys = [str(event["key"])] if event["op"] == "write" else [str(key) for key in event.get("invalidated_keys", [])]
            before_primary = {key: primary.mapping.get(key) for key in keys}
            before_reference = {key: fast.get(key) for key in keys}
            primary_action = apply_primary(primary, event)
            reference_action = apply_reference(reference, event, fast)
            if primary_action != reference_action:
                raise ValueError(f"action/victim/relocation mismatch at event {index}")
            relocated = [key for group in primary_action.get("relocated", []) for key in group]
            keys = list(dict.fromkeys(keys + relocated))
            if relocated:
                # GC is absent in this short closure geometry; retain a full
                # fail-closed path if a future fixed trace does reach it.
                primary_fingerprint = map_fingerprint(primary.mapping)
                reference_fingerprint = map_fingerprint(fast)
            else:
                for key in keys:
                    primary_fingerprint = update_fingerprint(primary_fingerprint, key, before_primary.get(key), primary.mapping.get(key))
                    reference_fingerprint = update_fingerprint(reference_fingerprint, key, before_reference.get(key), fast.get(key))
            if primary_fingerprint != reference_fingerprint or len(primary.mapping) != len(fast):
                raise ValueError(f"logical map/version fingerprint mismatch at event {index}")
            zones: set[int] = set()
            for mapping in (before_primary, before_reference):
                zones.update(value[1] for value in mapping.values() if value is not None)
            zones.update(primary.mapping[key][1] for key in keys if key in primary.mapping)
            zones.update(fast[key][1] for key in keys if key in fast)
            zones.update(int(zid) for zid in primary_action.get("victims", []))
            compare_affected_zones(primary, reference, zones, index)
            compare_scalars(primary, reference, index)
            if index % 1024 == 0:
                if reference.locations() != fast or sorted(primary.mapping) != sorted(fast):
                    raise ValueError(f"primary/reference checkpoint mismatch at {index}")
                checkpoints += 1
        primary.assert_invariants()
        reference.check()
        if reference.locations() != fast:
            raise ValueError("reference fast/full scan mismatch")
        p = primary.summary()
        r = reference.summary()
        if p != r:
            raise ValueError(f"primary/reference summary mismatch for {policy}")
        if p["live_keys"] != expected:
            raise ValueError(f"simulator final live set mismatch for {policy}")
        reports[policy] = {
            "event_count": len(spec["events"]), "checkpoint_count": checkpoints,
            "per_event_state_comparisons": len(spec["events"]),
            "live_page_count": len(expected), "live_set_sha256": digest(expected),
            "new_logical_blocks": p["new_logical_blocks"], "relocated_blocks": p["relocated_blocks"],
            "reset_count": p["reset_count"], "host_wa_fraction": p["host_wa_fraction"],
            "primary_equals_reference": True,
        }
    payload = {"schema": "zns-ann-z0a-r2-real-trace-replay-v1", "status": "pass", "policies": reports}
    with args.output.open("x") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"status": "pass", "events": len(spec["events"]), "final_pages": len(expected)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
