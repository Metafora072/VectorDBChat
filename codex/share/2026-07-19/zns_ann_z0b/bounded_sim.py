#!/usr/bin/env python3
"""Bounded, sequence-only Z0B simulator used only by cycle-positive tests.

This is deliberately not a long-trace runner.  It fixes the two R2 gaps that
must be exercised before endpoint work: host spares are an initial EMPTY free
pool (not a permanently reserved set), and completed reclamation cycles are
first-class state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any


class SimError(RuntimeError):
    pass


@dataclass
class Slot:
    key: str
    version: int
    valid: bool
    kind: str
    role: str


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
        return sum(slot.valid for slot in self.slots)


def coord(event: dict[str, Any]) -> tuple[int, int]:
    return int(event["global_seq"]), int(event.get("page_index_within_request", -1))


def fraction_text(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        raise SimError("zero cycle denominator")
    value = Fraction(numerator, denominator)
    return f"{value.numerator}/{value.denominator}"


class BoundedSimulator:
    POLICIES = {"GreedyValidFraction", "OracleMinCopy"}

    def __init__(self, spec: dict[str, Any], policy: str) -> None:
        if policy not in self.POLICIES:
            raise SimError(f"bad policy: {policy}")
        cfg = spec["config"]
        self.capacity = int(cfg["zone_capacity_blocks"])
        self.n = int(cfg["number_of_zones"])
        self.initial_spares = int(cfg["host_spare_zones"])
        self.block_bytes = int(cfg.get("logical_block_size_bytes", 4096))
        if self.block_bytes != 4096 or self.capacity <= 0:
            raise SimError("bounded tests require positive 4 KiB geometry")
        if not 2 <= self.initial_spares < self.n:
            raise SimError("bounded tests require at least two initial free zones")

        self.policy = policy
        self.zones = [Zone(index, self.capacity) for index in range(self.n)]
        self.current: int | None = None
        self.mapping: dict[str, tuple[int, int, int, str]] = {}
        self.initial_blocks = 0
        self.new_blocks = 0
        self.relocated_blocks = 0
        self.erased_blocks = 0
        self.reset_count = 0
        self.application_bytes = 0
        self.normalized_fragment_bytes = 0
        self.replacement_rmw_read_bytes = 0
        self.new_page_zero_fill_bytes = 0
        self.victim_sequence: list[int] = []
        self.cycles: list[dict[str, Any]] = []
        self.event_ordinal = 0
        self.last_coord: tuple[int, int] | None = None
        self.pending: dict[str, Any] = self._empty_pending()
        self._load_initial(spec.get("initial_zones", []))
        self.assert_invariants(expect_initial_free=True)

    @staticmethod
    def _empty_pending() -> dict[str, Any]:
        return {
            "start": None,
            "last": None,
            "new_blocks": 0,
            "application_bytes": 0,
            "update_ids": set(),
            "batch_ids": set(),
        }

    def _load_initial(self, rows: list[dict[str, Any]]) -> None:
        seen_zones: set[int] = set()
        heads: list[int] = []
        for row in rows:
            zid = int(row["zone_id"])
            if zid in seen_zones or not 0 <= zid < self.n:
                raise SimError("bad/duplicate initial zone")
            seen_zones.add(zid)
            zone = self.zones[zid]
            pages = row.get("pages", [])
            if not pages:
                raise SimError("initial zone must contain at least one page")
            for page in pages:
                key, role = str(page["key"]), str(page["role"])
                if key in self.mapping:
                    raise SimError(f"duplicate initial key: {key}")
                if zone.wp >= self.capacity:
                    raise SimError("initial zone overflow")
                slot = zone.wp
                zone.slots.append(Slot(key, 0, True, "INITIAL", role))
                self.mapping[key] = (0, zid, slot, role)
                self.initial_blocks += 1
            expected = "FULL" if zone.wp == self.capacity else "CLOSED"
            if row.get("state", expected) != expected:
                raise SimError("initial zone state does not match write pointer")
            zone.state = expected
            if bool(row.get("append_head", False)):
                if zone.state != "CLOSED":
                    raise SimError("only a partial CLOSED zone can be the initial append head")
                heads.append(zid)
        if len(heads) > 1:
            raise SimError("multiple initial append heads")
        self.current = heads[0] if heads else None
        if len(seen_zones) + self.initial_spares != self.n:
            raise SimError("total zones must equal occupied initial zones plus host spares")

    def free_ids(self) -> list[int]:
        return [zone.zone_id for zone in self.zones if zone.state == "EMPTY"]

    def _open(self, zid: int) -> None:
        zone = self.zones[zid]
        if zone.state not in {"EMPTY", "CLOSED"}:
            raise SimError("zone is not openable")
        zone.state = "OPEN"
        self.current = zid

    def _finish_if_full(self, zid: int) -> None:
        zone = self.zones[zid]
        if zone.wp == self.capacity:
            zone.state = "FULL"
            if self.current == zid:
                self.current = None

    def _eligible(self, destination: int) -> list[int]:
        return [
            zone.zone_id
            for zone in self.zones
            if zone.state == "FULL" and zone.zone_id != destination and zone.zone_id != self.current
        ]

    def _victim(self, destination: int) -> int:
        candidates = self._eligible(destination)
        if not candidates:
            raise SimError("no FULL victim")
        # Equal capacities make both approved cleaners intentionally identical.
        if self.policy == "GreedyValidFraction":
            return min(candidates, key=lambda zid: (Fraction(self.zones[zid].live, self.capacity), zid))
        return min(candidates, key=lambda zid: (self.zones[zid].live, zid))

    def _close_cycle(self, victim: Zone, destination: int, trigger: dict[str, Any], relocated: int) -> None:
        if self.pending["new_blocks"] <= 0:
            raise SimError("GC cannot close an empty fill window")
        new_blocks = int(self.pending["new_blocks"])
        record = {
            "cycle_index": len(self.cycles) + 1,
            "start": self.pending["start"],
            "last_append_before_gc": self.pending["last"],
            "gc_trigger": {
                "event_ordinal": self.event_ordinal,
                "global_seq": coord(trigger)[0],
                "page_index_within_request": coord(trigger)[1],
            },
            "allocated_new_blocks": new_blocks,
            "relocated_blocks": relocated,
            "host_wa_fraction": fraction_text(new_blocks + relocated, new_blocks),
            "victim_zone": victim.zone_id,
            "relocation_destination": destination,
            "victim_valid_fraction": fraction_text(relocated, self.capacity),
            "update_ids": sorted(self.pending["update_ids"]),
            "batch_ids": sorted(self.pending["batch_ids"]),
        }
        self.cycles.append(record)
        self.pending = self._empty_pending()

    def _gc(self, trigger: dict[str, Any]) -> None:
        free = self.free_ids()
        if len(free) != 1:
            raise SimError("GC requires exactly one relocation-reserve zone")
        destination = free[0]
        victim_id = self._victim(destination)
        victim = self.zones[victim_id]
        live_before = victim.live
        if live_before >= self.capacity:
            raise SimError("victim has no reclaimable block")
        self._open(destination)
        dest = self.zones[destination]
        for source_index, source in enumerate(victim.slots):
            if not source.valid:
                continue
            expected = (source.version, victim_id, source_index, source.role)
            if self.mapping.get(source.key) != expected:
                raise SimError("stale relocation source")
            dest_index = dest.wp
            dest.slots.append(Slot(source.key, source.version, True, "RELOC", source.role))
            source.valid = False
            self.mapping[source.key] = (source.version, destination, dest_index, source.role)
            self.relocated_blocks += 1
        if victim.live:
            raise SimError("reset with live data")
        erased = victim.wp
        victim.slots.clear()
        victim.state = "EMPTY"
        self.erased_blocks += erased
        self.reset_count += 1
        self.victim_sequence.append(victim_id)
        self._finish_if_full(destination)
        if self.current is None:
            raise SimError("relocation left no room for triggering append")
        self._close_cycle(victim, destination, trigger, live_before)
        self.assert_invariants()

    def _room(self, trigger: dict[str, Any]) -> int:
        if self.current is not None:
            zone = self.zones[self.current]
            if zone.state == "CLOSED":
                self._open(self.current)
            if zone.state == "OPEN" and zone.wp < self.capacity:
                return self.current
        free = self.free_ids()
        if len(free) >= 2:
            self._open(free[0])
            return free[0]
        if len(free) == 1:
            self._gc(trigger)
            if self.current is None:
                raise SimError("no room after GC")
            return self.current
        raise SimError("no free relocation reserve")

    def _pending_event(self, event: dict[str, Any], is_append: bool) -> None:
        marker = {
            "event_ordinal": self.event_ordinal,
            "global_seq": coord(event)[0],
            "page_index_within_request": coord(event)[1],
        }
        if is_append and self.pending["start"] is None:
            self.pending["start"] = marker
        if self.pending["start"] is not None:
            self.pending["last"] = marker
            update = int(event.get("update_or_replacement_id", 0))
            batch = int(event.get("batch_id", 0))
            if update:
                self.pending["update_ids"].add(update)
            if batch:
                self.pending["batch_ids"].add(batch)

    def _write(self, event: dict[str, Any]) -> None:
        key, role = str(event["key"]), str(event["role"])
        fragment = int(event.get("page_bytes", self.block_bytes))
        if not 0 < fragment <= self.block_bytes:
            raise SimError("bad fragment size")
        destination = self._room(event)
        old = self.mapping.get(key)
        if old is not None and old[3] != role:
            raise SimError("role changed across page versions")
        version = 1 if old is None else old[0] + 1
        slot_index = self.zones[destination].wp
        self.zones[destination].slots.append(Slot(key, version, True, "NEW", role))
        if old is not None:
            old_slot = self.zones[old[1]].slots[old[2]]
            if not old_slot.valid or old_slot.version != old[0]:
                raise SimError("stale old mapping")
            old_slot.valid = False
            self.replacement_rmw_read_bytes += self.block_bytes - fragment
        else:
            self.new_page_zero_fill_bytes += self.block_bytes - fragment
        self.mapping[key] = (version, destination, slot_index, role)
        self.new_blocks += 1
        self.application_bytes += fragment
        self.normalized_fragment_bytes += fragment
        self._pending_event(event, True)
        self.pending["new_blocks"] += 1
        self.pending["application_bytes"] += fragment
        self._finish_if_full(destination)

    def _truncate(self, event: dict[str, Any]) -> None:
        keys = [str(key) for key in event.get("invalidated_keys", [])]
        if len(keys) != len(set(keys)):
            raise SimError("duplicate truncate key")
        for key in keys:
            old = self.mapping.pop(key, None)
            if old is None:
                raise SimError("truncate missing key")
            slot = self.zones[old[1]].slots[old[2]]
            if not slot.valid or slot.version != old[0]:
                raise SimError("truncate stale mapping")
            slot.valid = False
        self._pending_event(event, False)

    def apply(self, event: dict[str, Any]) -> None:
        self.event_ordinal += 1
        current_coord = coord(event)
        if current_coord[0] <= 0 or (self.last_coord is not None and current_coord <= self.last_coord):
            raise SimError("event order is not strictly lexicographic")
        self.last_coord = current_coord
        if event["op"] == "write":
            self._write(event)
        elif event["op"] == "truncate":
            self._truncate(event)
        else:
            raise SimError("unsupported bounded event")
        self.assert_invariants()

    def assert_invariants(self, expect_initial_free: bool = False) -> None:
        scanned: dict[str, tuple[int, int, int, str]] = {}
        occupied = 0
        open_count = 0
        for zone in self.zones:
            if not 0 <= zone.wp <= self.capacity:
                raise SimError("write pointer out of range")
            if zone.state == "EMPTY" and zone.wp:
                raise SimError("EMPTY zone contains slots")
            if zone.state == "FULL" and zone.wp != self.capacity:
                raise SimError("FULL zone is not full")
            if zone.state == "OPEN":
                open_count += 1
            occupied += zone.wp
            for index, slot in enumerate(zone.slots):
                if slot.valid:
                    if slot.key in scanned:
                        raise SimError("multiple live versions")
                    scanned[slot.key] = (slot.version, zone.zone_id, index, slot.role)
        if scanned != self.mapping:
            raise SimError("mapping/live-set mismatch")
        if occupied != self.initial_blocks + self.new_blocks + self.relocated_blocks - self.erased_blocks:
            raise SimError("physical block account mismatch")
        if open_count > 1:
            raise SimError("single append-head limit violated")
        if self.current is not None and self.zones[self.current].state not in {"OPEN", "CLOSED"}:
            raise SimError("bad current append head")
        if expect_initial_free and len(self.free_ids()) != self.initial_spares:
            raise SimError("initial free-pool size mismatch")
        if not expect_initial_free and len(self.free_ids()) < 1:
            raise SimError("relocation reserve was consumed")

    def tail(self) -> dict[str, Any]:
        return {
            "complete_cycle": False,
            "start": self.pending["start"],
            "last": self.pending["last"],
            "allocated_new_blocks": self.pending["new_blocks"],
            "application_bytes": self.pending["application_bytes"],
        }

    def state_view(self) -> dict[str, Any]:
        return {
            "zones": [
                {
                    "id": zone.zone_id,
                    "state": zone.state,
                    "slots": [
                        [slot.key, slot.version, slot.valid, slot.kind, slot.role]
                        for slot in zone.slots
                    ],
                }
                for zone in self.zones
            ],
            "mapping": [[key, *self.mapping[key]] for key in sorted(self.mapping)],
            "current": self.current,
            "free": self.free_ids(),
            "counters": {
                "initial": self.initial_blocks,
                "new": self.new_blocks,
                "relocated": self.relocated_blocks,
                "erased": self.erased_blocks,
                "resets": self.reset_count,
                "application_bytes": self.application_bytes,
                "normalized_fragment_bytes": self.normalized_fragment_bytes,
                "replacement_rmw_read_bytes": self.replacement_rmw_read_bytes,
                "new_page_zero_fill_bytes": self.new_page_zero_fill_bytes,
            },
            "victims": list(self.victim_sequence),
            "cycles": list(self.cycles),
            "tail": self.tail(),
        }
