#!/usr/bin/env python3
"""Independent scan-based reference for the bounded Z0B cycle tests.

It intentionally imports no primary-simulator code and keeps no incremental
logical-page map.  Every lookup is reconstructed from physical slots, so GC
relocations cannot leave an external fast map stale as they did in the R2
short-trace validator.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any


class ReferenceError(RuntimeError):
    pass


def event_coord(event: dict[str, Any]) -> tuple[int, int]:
    return int(event["global_seq"]), int(event.get("page_index_within_request", -1))


def frac(numerator: int, denominator: int) -> str:
    value = Fraction(numerator, denominator)
    return f"{value.numerator}/{value.denominator}"


class BoundedReference:
    def __init__(self, spec: dict[str, Any], policy: str) -> None:
        if policy not in {"GreedyValidFraction", "OracleMinCopy"}:
            raise ReferenceError("bad policy")
        cfg = spec["config"]
        self.cap = int(cfg["zone_capacity_blocks"])
        self.count = int(cfg["number_of_zones"])
        self.h = int(cfg["host_spare_zones"])
        self.bs = int(cfg.get("logical_block_size_bytes", 4096))
        if self.bs != 4096 or not 2 <= self.h < self.count:
            raise ReferenceError("bad bounded geometry")
        self.policy = policy
        self.zones = [{"state": "EMPTY", "slots": []} for _ in range(self.count)]
        self.cur: int | None = None
        self.initial = self.user = self.copied = self.erased = self.resets = 0
        self.appbytes = self.fragmentbytes = self.rmwbytes = self.zerobytes = 0
        self.victims: list[int] = []
        self.cycles: list[dict[str, Any]] = []
        self.ordinal = 0
        self.previous: tuple[int, int] | None = None
        self.pending = self.empty_pending()
        occupied: set[int] = set()
        heads = []
        for row in spec.get("initial_zones", []):
            zid = int(row["zone_id"])
            if zid in occupied or not 0 <= zid < self.count:
                raise ReferenceError("bad initial zone")
            occupied.add(zid)
            for page in row.get("pages", []):
                if len(self.zones[zid]["slots"]) >= self.cap:
                    raise ReferenceError("initial overflow")
                self.zones[zid]["slots"].append(
                    [str(page["key"]), 0, True, "INITIAL", str(page["role"])]
                )
                self.initial += 1
            if not self.zones[zid]["slots"]:
                raise ReferenceError("empty initial zone")
            expected = "FULL" if len(self.zones[zid]["slots"]) == self.cap else "CLOSED"
            if row.get("state", expected) != expected:
                raise ReferenceError("bad initial state")
            self.zones[zid]["state"] = expected
            if row.get("append_head", False):
                if expected != "CLOSED":
                    raise ReferenceError("bad initial head")
                heads.append(zid)
        if len(heads) > 1 or len(occupied) + self.h != self.count:
            raise ReferenceError("bad initial layout")
        self.cur = heads[0] if heads else None
        self.check(initial=True)

    @staticmethod
    def empty_pending() -> dict[str, Any]:
        return {
            "start": None,
            "last": None,
            "new_blocks": 0,
            "application_bytes": 0,
            "update_ids": set(),
            "batch_ids": set(),
        }

    def free(self) -> list[int]:
        return [zid for zid, zone in enumerate(self.zones) if zone["state"] == "EMPTY"]

    def live(self, zid: int) -> int:
        return sum(bool(slot[2]) for slot in self.zones[zid]["slots"])

    def locations(self) -> dict[str, tuple[int, int, int, str]]:
        result: dict[str, tuple[int, int, int, str]] = {}
        for zid, zone in enumerate(self.zones):
            for sid, slot in enumerate(zone["slots"]):
                if slot[2]:
                    if slot[0] in result:
                        raise ReferenceError("duplicate live key")
                    result[str(slot[0])] = (int(slot[1]), zid, sid, str(slot[4]))
        return result

    def open_zone(self, zid: int) -> None:
        if self.zones[zid]["state"] not in {"EMPTY", "CLOSED"}:
            raise ReferenceError("not openable")
        self.zones[zid]["state"] = "OPEN"
        self.cur = zid

    def finish(self, zid: int) -> None:
        if len(self.zones[zid]["slots"]) == self.cap:
            self.zones[zid]["state"] = "FULL"
            if self.cur == zid:
                self.cur = None

    def choose(self, destination: int) -> int:
        choices = [
            zid
            for zid, zone in enumerate(self.zones)
            if zone["state"] == "FULL" and zid != destination and zid != self.cur
        ]
        if not choices:
            raise ReferenceError("no victim")
        if self.policy == "GreedyValidFraction":
            return min(choices, key=lambda zid: (Fraction(self.live(zid), self.cap), zid))
        return min(choices, key=lambda zid: (self.live(zid), zid))

    def complete_cycle(self, victim: int, destination: int, trigger: dict[str, Any], moved: int) -> None:
        new = int(self.pending["new_blocks"])
        if new <= 0:
            raise ReferenceError("empty cycle")
        self.cycles.append(
            {
                "cycle_index": len(self.cycles) + 1,
                "start": self.pending["start"],
                "last_append_before_gc": self.pending["last"],
                "gc_trigger": {
                    "event_ordinal": self.ordinal,
                    "global_seq": event_coord(trigger)[0],
                    "page_index_within_request": event_coord(trigger)[1],
                },
                "allocated_new_blocks": new,
                "relocated_blocks": moved,
                "host_wa_fraction": frac(new + moved, new),
                "victim_zone": victim,
                "relocation_destination": destination,
                "victim_valid_fraction": frac(moved, self.cap),
                "update_ids": sorted(self.pending["update_ids"]),
                "batch_ids": sorted(self.pending["batch_ids"]),
            }
        )
        self.pending = self.empty_pending()

    def collect(self, trigger: dict[str, Any]) -> None:
        free = self.free()
        if len(free) != 1:
            raise ReferenceError("GC without unique reserve")
        destination = free[0]
        source = self.choose(destination)
        moved = self.live(source)
        if moved >= self.cap:
            raise ReferenceError("no reclaimable block")
        self.open_zone(destination)
        # Scan-based truth is refreshed before every move; there is no stale
        # fast map to repair after collection.
        for sid, slot in enumerate(list(self.zones[source]["slots"])):
            if not slot[2]:
                continue
            if self.locations().get(str(slot[0])) != (int(slot[1]), source, sid, str(slot[4])):
                raise ReferenceError("stale source")
            self.zones[destination]["slots"].append(
                [str(slot[0]), int(slot[1]), True, "RELOC", str(slot[4])]
            )
            slot[2] = False
            self.copied += 1
        if self.live(source):
            raise ReferenceError("reset live zone")
        old_wp = len(self.zones[source]["slots"])
        self.zones[source] = {"state": "EMPTY", "slots": []}
        self.erased += old_wp
        self.resets += 1
        self.victims.append(source)
        self.finish(destination)
        if self.cur is None:
            raise ReferenceError("relocation overflow")
        self.complete_cycle(source, destination, trigger, moved)
        self.check()

    def room(self, trigger: dict[str, Any]) -> int:
        if self.cur is not None:
            zone = self.zones[self.cur]
            if zone["state"] == "CLOSED":
                self.open_zone(self.cur)
            if zone["state"] == "OPEN" and len(zone["slots"]) < self.cap:
                return int(self.cur)
        free = self.free()
        if len(free) >= 2:
            self.open_zone(free[0])
            return free[0]
        if len(free) == 1:
            self.collect(trigger)
            if self.cur is None:
                raise ReferenceError("no room after GC")
            return int(self.cur)
        raise ReferenceError("no reserve")

    def note(self, event: dict[str, Any], append: bool) -> None:
        marker = {
            "event_ordinal": self.ordinal,
            "global_seq": event_coord(event)[0],
            "page_index_within_request": event_coord(event)[1],
        }
        if append and self.pending["start"] is None:
            self.pending["start"] = marker
        if self.pending["start"] is not None:
            self.pending["last"] = marker
            update = int(event.get("update_or_replacement_id", 0))
            batch = int(event.get("batch_id", 0))
            if update:
                self.pending["update_ids"].add(update)
            if batch:
                self.pending["batch_ids"].add(batch)

    def write(self, event: dict[str, Any]) -> None:
        key, role = str(event["key"]), str(event["role"])
        amount = int(event.get("page_bytes", self.bs))
        if not 0 < amount <= self.bs:
            raise ReferenceError("bad fragment")
        destination = self.room(event)
        old = self.locations().get(key)
        if old is not None and old[3] != role:
            raise ReferenceError("role mismatch")
        version = 1 if old is None else old[0] + 1
        self.zones[destination]["slots"].append([key, version, True, "NEW", role])
        if old is not None:
            self.zones[old[1]]["slots"][old[2]][2] = False
            self.rmwbytes += self.bs - amount
        else:
            self.zerobytes += self.bs - amount
        self.user += 1
        self.appbytes += amount
        self.fragmentbytes += amount
        self.note(event, True)
        self.pending["new_blocks"] += 1
        self.pending["application_bytes"] += amount
        self.finish(destination)

    def truncate(self, event: dict[str, Any]) -> None:
        keys = [str(key) for key in event.get("invalidated_keys", [])]
        if len(keys) != len(set(keys)):
            raise ReferenceError("duplicate truncate")
        locations = self.locations()
        for key in keys:
            if key not in locations:
                raise ReferenceError("missing truncate key")
            old = locations[key]
            self.zones[old[1]]["slots"][old[2]][2] = False
        self.note(event, False)

    def apply(self, event: dict[str, Any]) -> None:
        self.ordinal += 1
        now = event_coord(event)
        if now[0] <= 0 or (self.previous is not None and now <= self.previous):
            raise ReferenceError("bad order")
        self.previous = now
        if event["op"] == "write":
            self.write(event)
        elif event["op"] == "truncate":
            self.truncate(event)
        else:
            raise ReferenceError("bad event")
        self.check()

    def check(self, initial: bool = False) -> None:
        occupied = 0
        open_count = 0
        for zone in self.zones:
            wp = len(zone["slots"])
            if not 0 <= wp <= self.cap:
                raise ReferenceError("bad WP")
            if zone["state"] == "EMPTY" and wp:
                raise ReferenceError("dirty EMPTY")
            if zone["state"] == "FULL" and wp != self.cap:
                raise ReferenceError("short FULL")
            open_count += zone["state"] == "OPEN"
            occupied += wp
        self.locations()
        if occupied != self.initial + self.user + self.copied - self.erased:
            raise ReferenceError("block account")
        if open_count > 1:
            raise ReferenceError("open limit")
        if self.cur is not None and self.zones[self.cur]["state"] not in {"OPEN", "CLOSED"}:
            raise ReferenceError("bad current")
        if initial and len(self.free()) != self.h:
            raise ReferenceError("initial free count")
        if not initial and len(self.free()) < 1:
            raise ReferenceError("reserve consumed")

    def tail(self) -> dict[str, Any]:
        return {
            "complete_cycle": False,
            "start": self.pending["start"],
            "last": self.pending["last"],
            "allocated_new_blocks": self.pending["new_blocks"],
            "application_bytes": self.pending["application_bytes"],
        }

    def state_view(self) -> dict[str, Any]:
        locations = self.locations()
        return {
            "zones": [
                {
                    "id": zid,
                    "state": zone["state"],
                    "slots": [list(slot) for slot in zone["slots"]],
                }
                for zid, zone in enumerate(self.zones)
            ],
            "mapping": [[key, *locations[key]] for key in sorted(locations)],
            "current": self.cur,
            "free": self.free(),
            "counters": {
                "initial": self.initial,
                "new": self.user,
                "relocated": self.copied,
                "erased": self.erased,
                "resets": self.resets,
                "application_bytes": self.appbytes,
                "normalized_fragment_bytes": self.fragmentbytes,
                "replacement_rmw_read_bytes": self.rmwbytes,
                "new_page_zero_fill_bytes": self.zerobytes,
            },
            "victims": list(self.victims),
            "cycles": list(self.cycles),
            "tail": self.tail(),
        }
