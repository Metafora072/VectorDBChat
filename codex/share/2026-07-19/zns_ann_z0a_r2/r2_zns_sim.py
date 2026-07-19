#!/usr/bin/env python3
"""Minimal host-managed ZNS reclamation simulator for the Z0A gate.

This model intentionally has one append stream, fixed-size logical blocks, real
zone counts, and rotating empty host spare zones.  OracleMinCopy means exactly
"minimum current live bytes among the current eligible victims".  It has no
future knowledge.  With equal-capacity, FULL-only candidates it must choose the
same victim as GreedyValidFraction; it is only an implementation sanity check.
"""

from __future__ import annotations

import copy
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class SimError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass
class Slot:
    key: str
    version: int
    valid: bool
    kind: str


@dataclass
class Zone:
    zone_id: int
    capacity: int
    state: str = "EMPTY"
    slots: list[Slot] = field(default_factory=list)

    @property
    def wp(self) -> int:
        return len(self.slots)

    @property
    def live(self) -> int:
        return sum(1 for slot in self.slots if slot.valid)


class ZNSSimulator:
    """Incremental simulator with an explicit logical-to-physical map."""

    POLICIES = {"GreedyValidFraction", "OracleMinCopy"}

    def __init__(self, case: dict[str, Any], policy: str) -> None:
        if policy not in self.POLICIES:
            raise SimError("BAD_POLICY", policy)
        cfg = case["config"]
        self.capacity = int(cfg["zone_capacity_blocks"])
        self.zone_size = int(cfg.get("zone_size_blocks", self.capacity))
        self.block_bytes = int(cfg.get("logical_block_size_bytes", 4096))
        self.n = int(cfg["number_of_zones"])
        self.max_open = int(cfg["max_open_zones"])
        self.max_active = int(cfg["max_active_zones"])
        self.h = int(cfg["host_spare_zones"])
        if not (0 < self.capacity <= self.zone_size):
            raise SimError("BAD_CONFIG", "capacity must be in (0, zone_size]")
        if not (1 <= self.h < self.n):
            raise SimError("BAD_CONFIG", "host_spare_zones must be in [1,N)")
        if self.max_open < 1 or self.max_active < 1 or self.max_open > self.max_active:
            raise SimError("BAD_CONFIG", "require 1 <= max_open <= max_active")

        self.policy = policy
        self.zones = [Zone(i, self.capacity) for i in range(self.n)]
        self.spares = set(range(self.n - self.h, self.n))
        self.current: int | None = None
        self.mapping: dict[str, tuple[int, int, int]] = {}
        self.initial_blocks = 0
        self.new_blocks = 0
        self.relocated_blocks = 0
        self.reset_erased_blocks = 0
        self.reset_count = 0
        self.application_bytes = 0
        self.victim_sequence: list[int] = []
        self.relocation_sequence: list[str] = []
        self.error_codes: list[str] = []
        self._pack_initial([str(x) for x in case.get("initial_live", [])])
        self.assert_invariants()

    def _open_count(self) -> int:
        return sum(zone.state == "OPEN" for zone in self.zones)

    def _active_count(self) -> int:
        return sum(zone.state in {"OPEN", "CLOSED"} for zone in self.zones)

    def _pack_initial(self, keys: list[str]) -> None:
        ordinary = [i for i in range(self.n) if i not in self.spares]
        if len(keys) > len(ordinary) * self.capacity:
            raise SimError("INITIAL_IMAGE_TOO_LARGE")
        for index, key in enumerate(keys):
            if key in self.mapping:
                raise SimError("DUPLICATE_INITIAL_KEY", key)
            zid = ordinary[index // self.capacity]
            zone = self.zones[zid]
            slot_idx = zone.wp
            zone.slots.append(Slot(key, 0, True, "INITIAL"))
            zone.state = "FULL" if zone.wp == self.capacity else "CLOSED"
            self.mapping[key] = (0, zid, slot_idx)
            self.initial_blocks += 1
        if keys and len(keys) % self.capacity:
            self.current = ordinary[(len(keys) - 1) // self.capacity]
        if self._active_count() > self.max_active:
            raise SimError("INITIAL_ACTIVE_LIMIT")

    def _open_zone(self, zid: int, make_current: bool = True) -> None:
        zone = self.zones[zid]
        if zone.state == "OPEN":
            if make_current:
                self.current = zid
            return
        if zone.state not in {"EMPTY", "CLOSED"}:
            raise SimError("ZONE_NOT_OPENABLE", f"z{zid}:{zone.state}")
        if self._open_count() + 1 > self.max_open:
            raise SimError("OPEN_LIMIT")
        if zone.state == "EMPTY" and self._active_count() + 1 > self.max_active:
            raise SimError("ACTIVE_LIMIT")
        zone.state = "OPEN"
        if make_current:
            self.current = zid

    def _close_current(self) -> None:
        if self.current is None or self.zones[self.current].state != "OPEN":
            raise SimError("NO_OPEN_CURRENT")
        self.zones[self.current].state = "CLOSED"

    def _finish_if_full(self, zid: int) -> None:
        zone = self.zones[zid]
        if zone.wp == self.capacity:
            zone.state = "FULL"
            if self.current == zid:
                self.current = None

    def _ordinary_empty(self) -> int | None:
        for zone in self.zones:
            if zone.zone_id not in self.spares and zone.state == "EMPTY":
                return zone.zone_id
        return None

    def _eligible_victims(self, relocation_zid: int) -> list[int]:
        return [
            zone.zone_id
            for zone in self.zones
            if zone.state == "FULL"
            and zone.zone_id not in self.spares
            and zone.zone_id != relocation_zid
            and zone.zone_id != self.current
        ]

    def _choose_victim(self, candidates: list[int]) -> int:
        if not candidates:
            raise SimError("NO_VICTIM")
        if self.policy == "GreedyValidFraction":
            # Denominator is fixed writable capacity, not bytes written.
            return min(candidates, key=lambda zid: (self.zones[zid].live / self.capacity, zid))
        # One-step exact current-copy oracle only.  No lookahead is used.
        return min(candidates, key=lambda zid: (self.zones[zid].live, zid))

    def _gc_once(self, action: dict[str, Any]) -> None:
        empty_spares = sorted(zid for zid in self.spares if self.zones[zid].state == "EMPTY")
        if not empty_spares:
            raise SimError("NO_EMPTY_SPARE")
        dest_id = empty_spares[0]
        victim_id = self._choose_victim(self._eligible_victims(dest_id))
        victim = self.zones[victim_id]
        if victim.live >= self.capacity:
            # Copying a fully-live victim releases no block for the triggering append.
            raise SimError("NO_SPACE_NO_RECLAIMABLE_BYTES")

        self._open_zone(dest_id)
        dest = self.zones[dest_id]
        relocated_keys: list[str] = []
        for source_idx, source in enumerate(victim.slots):
            if not source.valid:
                continue
            if dest.wp >= self.capacity:
                raise SimError("RELOCATION_OVERFLOW")
            old = self.mapping.get(source.key)
            if old != (source.version, victim_id, source_idx):
                raise SimError("STALE_LIVE_SOURCE", source.key)
            dest_idx = dest.wp
            dest.slots.append(Slot(source.key, source.version, True, "RELOC"))
            source.valid = False
            self.mapping[source.key] = (source.version, dest_id, dest_idx)
            self.relocated_blocks += 1
            relocated_keys.append(source.key)
            self.relocation_sequence.append(source.key)
            self._finish_if_full(dest_id)
            self.assert_invariants(allow_spare_rotation=True)

        if victim.live != 0:
            raise SimError("RESET_WITH_LIVE_DATA")
        if victim.state == "OPEN":
            raise SimError("RESET_OPEN_ZONE")
        erased = victim.wp
        victim.slots.clear()
        victim.state = "EMPTY"
        self.reset_erased_blocks += erased
        self.reset_count += 1
        self.spares.remove(dest_id)
        self.spares.add(victim_id)
        if dest.state == "OPEN":
            self.current = dest_id
        self.victim_sequence.append(victim_id)
        action.setdefault("victims", []).append(victim_id)
        action.setdefault("relocated", []).append(relocated_keys)

    def _ensure_append_space(self, action: dict[str, Any]) -> int:
        if self.current is not None:
            zone = self.zones[self.current]
            if zone.state == "CLOSED" and zone.wp < self.capacity:
                self._open_zone(self.current)
            if zone.state == "OPEN" and zone.wp < self.capacity:
                return self.current

        empty = self._ordinary_empty()
        if empty is not None:
            try:
                self._open_zone(empty)
                return empty
            except SimError as exc:
                if exc.code not in {"OPEN_LIMIT", "ACTIVE_LIMIT"}:
                    raise
        self._gc_once(action)
        if self.current is None:
            raise SimError("NO_SPACE_AFTER_GC")
        zone = self.zones[self.current]
        if zone.state != "OPEN" or zone.wp >= self.capacity:
            raise SimError("NO_SPACE_AFTER_GC")
        return self.current

    def _write(self, event: dict[str, Any], action: dict[str, Any]) -> None:
        key = str(event["key"])
        zid = self._ensure_append_space(action)
        zone = self.zones[zid]
        old = self.mapping.get(key)
        version = 1 if old is None else old[0] + 1
        idx = zone.wp
        zone.slots.append(Slot(key, version, True, "NEW"))
        if old is not None:
            old_ver, old_zid, old_idx = old
            old_slot = self.zones[old_zid].slots[old_idx]
            if not old_slot.valid or old_slot.version != old_ver:
                raise SimError("BAD_OLD_MAPPING", key)
            old_slot.valid = False
        self.mapping[key] = (version, zid, idx)
        self.new_blocks += 1
        self.application_bytes += int(event.get("page_bytes", self.block_bytes))
        self._finish_if_full(zid)

    def _truncate(self, event: dict[str, Any], action: dict[str, Any]) -> None:
        keys = [str(key) for key in event.get("invalidated_keys", [])]
        if len(keys) != len(set(keys)):
            raise SimError("DUPLICATE_TRUNCATE_KEY")
        for key in keys:
            old = self.mapping.get(key)
            if old is None:
                raise SimError("TRUNCATE_MISSING_KEY", key)
            version, zid, idx = old
            slot = self.zones[zid].slots[idx]
            if not slot.valid or slot.version != version:
                raise SimError("TRUNCATE_STALE_MAPPING", key)
            slot.valid = False
            del self.mapping[key]
        action["invalidated_keys"] = keys

    def apply_event(self, event: dict[str, Any]) -> dict[str, Any]:
        action: dict[str, Any] = {"op": event["op"]}
        if event["op"] == "write":
            self._write(event, action)
        elif event["op"] == "truncate":
            self._truncate(event, action)
        elif event["op"] == "close_current":
            self._close_current()
        elif event["op"] == "open_zone":
            self._open_zone(int(event["zone_id"]))
        else:
            raise SimError("BAD_EVENT", str(event["op"]))
        self.assert_invariants()
        return action

    def assert_invariants(self, allow_spare_rotation: bool = False) -> None:
        valid_locations: dict[str, tuple[int, int, int]] = {}
        occupied = 0
        for zone in self.zones:
            if not (0 <= zone.wp <= self.capacity):
                raise SimError("WP_OUT_OF_RANGE", str(zone.zone_id))
            if zone.state == "EMPTY" and zone.wp != 0:
                raise SimError("NONEMPTY_EMPTY_ZONE", str(zone.zone_id))
            if zone.state == "FULL" and zone.wp != self.capacity:
                raise SimError("NONFULL_FULL_ZONE", str(zone.zone_id))
            occupied += zone.wp
            for idx, slot in enumerate(zone.slots):
                if slot.valid:
                    if slot.key in valid_locations:
                        raise SimError("MULTIPLE_CURRENT_VERSIONS", slot.key)
                    valid_locations[slot.key] = (slot.version, zone.zone_id, idx)
        if valid_locations != self.mapping:
            raise SimError("MAP_LIVE_SET_MISMATCH")
        expected_occupied = (
            self.initial_blocks + self.new_blocks + self.relocated_blocks - self.reset_erased_blocks
        )
        if occupied != expected_occupied:
            raise SimError("PHYSICAL_BYTE_ACCOUNT_MISMATCH")
        if self._open_count() > self.max_open:
            raise SimError("OPEN_LIMIT_VIOLATION")
        if self._active_count() > self.max_active:
            raise SimError("ACTIVE_LIMIT_VIOLATION")
        if not allow_spare_rotation:
            if len(self.spares) != self.h:
                raise SimError("SPARE_COUNT_MISMATCH")
            if any(self.zones[zid].state != "EMPTY" for zid in self.spares):
                raise SimError("SPARE_NOT_EMPTY")
        if self.current is not None and self.zones[self.current].state not in {"OPEN", "CLOSED"}:
            raise SimError("BAD_CURRENT_ZONE")

    def snapshot(self, action: dict[str, Any], error: str | None = None) -> dict[str, Any]:
        zones = []
        for zone in self.zones:
            zones.append(
                {
                    "id": zone.zone_id,
                    "state": zone.state,
                    "wp": zone.wp,
                    "live": zone.live,
                    "invalid": zone.wp - zone.live,
                    "slots": [
                        [slot.key, slot.version, "V" if slot.valid else "I", slot.kind]
                        for slot in zone.slots
                    ],
                }
            )
        return {
            "action": action,
            "error": error,
            "zones": zones,
            "mapping": [[key, *self.mapping[key]] for key in sorted(self.mapping)],
            "spares": sorted(self.spares),
            "current": self.current,
            "open": self._open_count(),
            "active": self._active_count(),
            "counters": {
                "initial": self.initial_blocks,
                "new": self.new_blocks,
                "relocated": self.relocated_blocks,
                "reset_erased": self.reset_erased_blocks,
                "resets": self.reset_count,
                "application_bytes": self.application_bytes,
            },
        }

    def summary(self) -> dict[str, Any]:
        numerator = self.new_blocks + self.relocated_blocks
        denominator = self.new_blocks
        return {
            "new_logical_blocks": self.new_blocks,
            "relocated_blocks": self.relocated_blocks,
            "reset_count": self.reset_count,
            "host_wa_fraction": f"{numerator}/{denominator}" if denominator else "NA",
            "application_bytes": self.application_bytes,
            "live_keys": sorted(self.mapping),
            "victim_sequence": self.victim_sequence,
            "relocation_sequence": self.relocation_sequence,
            "error_codes": self.error_codes,
            "open_count": self._open_count(),
            "active_count": self._active_count(),
        }


def run_case(case: dict[str, Any], policy: str) -> dict[str, Any]:
    sim = ZNSSimulator(case, policy)
    journal: list[dict[str, Any]] = []
    for event_index, event in enumerate(case["events"]):
        before = copy.deepcopy(sim)
        expected_error = event.get("expect_error")
        try:
            action = sim.apply_event(event)
            if expected_error:
                raise AssertionError(f"event {event_index} expected {expected_error}, but succeeded")
            journal.append(sim.snapshot(action))
        except SimError as exc:
            if exc.code != expected_error:
                raise
            # Every expected rejection is fail-closed and leaves state untouched.
            sim = before
            sim.error_codes.append(exc.code)
            sim.assert_invariants()
            journal.append(sim.snapshot({"op": event["op"]}, error=exc.code))
    return {"journal": journal, "summary": sim.summary()}


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        print(f"usage: {Path(sys.argv[0]).name} CASE.json [POLICY]", file=sys.stderr)
        return 2
    case = json.loads(Path(sys.argv[1]).read_text())
    policy = sys.argv[2] if len(sys.argv) == 3 else "GreedyValidFraction"
    print(json.dumps(run_case(case, policy), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
