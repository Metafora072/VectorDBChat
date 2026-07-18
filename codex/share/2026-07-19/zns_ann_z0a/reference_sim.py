#!/usr/bin/env python3
"""Independent, deliberately simple reference for the Z0A ZNS simulator.

It does not import zns_sim, does not maintain an incremental logical map, and
recomputes live locations by scanning all physical slots after every mutation.
The current-candidate OracleMinCopy has no lookahead.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any


class RefFault(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class Reference:
    def __init__(self, spec: dict[str, Any], policy: str) -> None:
        if policy not in ("GreedyValidFraction", "OracleMinCopy"):
            raise RefFault("BAD_POLICY")
        c = spec["config"]
        self.cap = int(c["zone_capacity_blocks"])
        self.size = int(c.get("zone_size_blocks", self.cap))
        self.bs = int(c.get("logical_block_size_bytes", 4096))
        self.count = int(c["number_of_zones"])
        self.mo = int(c["max_open_zones"])
        self.ma = int(c["max_active_zones"])
        self.reserve = int(c["host_spare_zones"])
        if not (0 < self.cap <= self.size):
            raise RefFault("BAD_CONFIG")
        if not (1 <= self.reserve < self.count):
            raise RefFault("BAD_CONFIG")
        if not (1 <= self.mo <= self.ma):
            raise RefFault("BAD_CONFIG")
        self.policy = policy
        self.z = [{"state": "EMPTY", "slots": []} for _ in range(self.count)]
        self.spare = set(range(self.count - self.reserve, self.count))
        self.cur = None
        self.initial = self.user = self.copied = self.erased = self.resets = 0
        self.appbytes = 0
        self.victims: list[int] = []
        self.moved: list[str] = []
        self.errors: list[str] = []
        ordinary = [i for i in range(self.count) if i not in self.spare]
        initial_keys = [str(k) for k in spec.get("initial_live", [])]
        if len(initial_keys) > len(ordinary) * self.cap:
            raise RefFault("INITIAL_IMAGE_TOO_LARGE")
        if len(set(initial_keys)) != len(initial_keys):
            raise RefFault("DUPLICATE_INITIAL_KEY")
        for pos, key in enumerate(initial_keys):
            zid = ordinary[pos // self.cap]
            self.z[zid]["slots"].append([key, 0, True, "INITIAL"])
            self.z[zid]["state"] = "FULL" if len(self.z[zid]["slots"]) == self.cap else "CLOSED"
            self.initial += 1
        if initial_keys and len(initial_keys) % self.cap:
            self.cur = ordinary[(len(initial_keys) - 1) // self.cap]
        if self.active_count() > self.ma:
            raise RefFault("INITIAL_ACTIVE_LIMIT")
        self.check()

    def open_count(self) -> int:
        return sum(q["state"] == "OPEN" for q in self.z)

    def active_count(self) -> int:
        return sum(q["state"] in ("OPEN", "CLOSED") for q in self.z)

    def locations(self) -> dict[str, tuple[int, int, int]]:
        ans: dict[str, tuple[int, int, int]] = {}
        for zid, zone in enumerate(self.z):
            for sid, (key, ver, valid, _kind) in enumerate(zone["slots"]):
                if valid:
                    if key in ans:
                        raise RefFault("MULTIPLE_CURRENT_VERSIONS", key)
                    ans[key] = (int(ver), zid, sid)
        return ans

    def live(self, zid: int) -> int:
        return sum(bool(slot[2]) for slot in self.z[zid]["slots"])

    def open_zone(self, zid: int) -> None:
        state = self.z[zid]["state"]
        if state == "OPEN":
            self.cur = zid
            return
        if state not in ("EMPTY", "CLOSED"):
            raise RefFault("ZONE_NOT_OPENABLE", str(zid))
        if self.open_count() == self.mo:
            raise RefFault("OPEN_LIMIT")
        if state == "EMPTY" and self.active_count() == self.ma:
            raise RefFault("ACTIVE_LIMIT")
        self.z[zid]["state"] = "OPEN"
        self.cur = zid

    def maybe_full(self, zid: int) -> None:
        if len(self.z[zid]["slots"]) == self.cap:
            self.z[zid]["state"] = "FULL"
            if self.cur == zid:
                self.cur = None

    def first_data_empty(self) -> int | None:
        for zid, zone in enumerate(self.z):
            if zid not in self.spare and zone["state"] == "EMPTY":
                return zid
        return None

    def victim(self, dest: int) -> int:
        choices = [
            zid for zid, zone in enumerate(self.z)
            if zone["state"] == "FULL" and zid not in self.spare and zid != dest and zid != self.cur
        ]
        if not choices:
            raise RefFault("NO_VICTIM")
        if self.policy == "GreedyValidFraction":
            return min(choices, key=lambda zid: (self.live(zid) / self.cap, zid))
        return min(choices, key=lambda zid: (self.live(zid), zid))

    def collect(self, action: dict[str, Any]) -> None:
        destinations = [zid for zid in sorted(self.spare) if self.z[zid]["state"] == "EMPTY"]
        if not destinations:
            raise RefFault("NO_EMPTY_SPARE")
        dest = destinations[0]
        source = self.victim(dest)
        if self.live(source) >= self.cap:
            raise RefFault("NO_SPACE_NO_RECLAIMABLE_BYTES")
        self.open_zone(dest)
        moved_now = []
        # Recompute the physical source truth on every iteration rather than
        # consulting a maintained map.
        for sid in range(len(self.z[source]["slots"])):
            slot = self.z[source]["slots"][sid]
            if not slot[2]:
                continue
            if len(self.z[dest]["slots"]) >= self.cap:
                raise RefFault("RELOCATION_OVERFLOW")
            key, ver = str(slot[0]), int(slot[1])
            if self.locations().get(key) != (ver, source, sid):
                raise RefFault("STALE_LIVE_SOURCE", key)
            self.z[dest]["slots"].append([key, ver, True, "RELOC"])
            slot[2] = False
            self.copied += 1
            moved_now.append(key)
            self.moved.append(key)
            self.maybe_full(dest)
            self.check(loose_spare=True)
        if self.live(source):
            raise RefFault("RESET_WITH_LIVE_DATA")
        old_wp = len(self.z[source]["slots"])
        self.z[source] = {"state": "EMPTY", "slots": []}
        self.erased += old_wp
        self.resets += 1
        self.spare.remove(dest)
        self.spare.add(source)
        self.cur = dest if self.z[dest]["state"] == "OPEN" else None
        self.victims.append(source)
        action.setdefault("victims", []).append(source)
        action.setdefault("relocated", []).append(moved_now)

    def room(self, action: dict[str, Any]) -> int:
        if self.cur is not None:
            zone = self.z[self.cur]
            if zone["state"] == "CLOSED" and len(zone["slots"]) < self.cap:
                self.open_zone(self.cur)
            if zone["state"] == "OPEN" and len(zone["slots"]) < self.cap:
                return int(self.cur)
        empty = self.first_data_empty()
        if empty is not None:
            try:
                self.open_zone(empty)
                return empty
            except RefFault as err:
                if err.code not in ("OPEN_LIMIT", "ACTIVE_LIMIT"):
                    raise
        self.collect(action)
        if self.cur is None or self.z[self.cur]["state"] != "OPEN" or len(self.z[self.cur]["slots"]) >= self.cap:
            raise RefFault("NO_SPACE_AFTER_GC")
        return int(self.cur)

    def write(self, event: dict[str, Any], action: dict[str, Any]) -> None:
        key = str(event["key"])
        dest = self.room(action)
        old = self.locations().get(key)
        version = 1 if old is None else old[0] + 1
        self.z[dest]["slots"].append([key, version, True, "NEW"])
        if old is not None:
            self.z[old[1]]["slots"][old[2]][2] = False
        self.user += 1
        self.appbytes += int(event.get("page_bytes", self.bs))
        self.maybe_full(dest)

    def event(self, e: dict[str, Any]) -> dict[str, Any]:
        action: dict[str, Any] = {"op": e["op"]}
        if e["op"] == "write":
            self.write(e, action)
        elif e["op"] == "close_current":
            if self.cur is None or self.z[self.cur]["state"] != "OPEN":
                raise RefFault("NO_OPEN_CURRENT")
            self.z[self.cur]["state"] = "CLOSED"
        elif e["op"] == "open_zone":
            self.open_zone(int(e["zone_id"]))
        else:
            raise RefFault("BAD_EVENT")
        self.check()
        return action

    def check(self, loose_spare: bool = False) -> None:
        occupied = 0
        for zid, zone in enumerate(self.z):
            wp = len(zone["slots"])
            if not 0 <= wp <= self.cap:
                raise RefFault("WP_OUT_OF_RANGE", str(zid))
            if zone["state"] == "EMPTY" and wp:
                raise RefFault("NONEMPTY_EMPTY_ZONE")
            if zone["state"] == "FULL" and wp != self.cap:
                raise RefFault("NONFULL_FULL_ZONE")
            occupied += wp
        self.locations()
        if occupied != self.initial + self.user + self.copied - self.erased:
            raise RefFault("PHYSICAL_BYTE_ACCOUNT_MISMATCH")
        if self.open_count() > self.mo:
            raise RefFault("OPEN_LIMIT_VIOLATION")
        if self.active_count() > self.ma:
            raise RefFault("ACTIVE_LIMIT_VIOLATION")
        if not loose_spare:
            if len(self.spare) != self.reserve:
                raise RefFault("SPARE_COUNT_MISMATCH")
            if any(self.z[zid]["state"] != "EMPTY" for zid in self.spare):
                raise RefFault("SPARE_NOT_EMPTY")
        if self.cur is not None and self.z[self.cur]["state"] not in ("OPEN", "CLOSED"):
            raise RefFault("BAD_CURRENT_ZONE")

    def snap(self, action: dict[str, Any], error: str | None = None) -> dict[str, Any]:
        loc = self.locations()
        zones = []
        for zid, zone in enumerate(self.z):
            live = self.live(zid)
            zones.append({
                "id": zid, "state": zone["state"], "wp": len(zone["slots"]),
                "live": live, "invalid": len(zone["slots"]) - live,
                "slots": [[s[0], s[1], "V" if s[2] else "I", s[3]] for s in zone["slots"]],
            })
        return {
            "action": action, "error": error, "zones": zones,
            "mapping": [[key, *loc[key]] for key in sorted(loc)],
            "spares": sorted(self.spare), "current": self.cur,
            "open": self.open_count(), "active": self.active_count(),
            "counters": {
                "initial": self.initial, "new": self.user, "relocated": self.copied,
                "reset_erased": self.erased, "resets": self.resets,
                "application_bytes": self.appbytes,
            },
        }

    def summary(self) -> dict[str, Any]:
        loc = self.locations()
        return {
            "new_logical_blocks": self.user,
            "relocated_blocks": self.copied,
            "reset_count": self.resets,
            "host_wa_fraction": f"{self.user + self.copied}/{self.user}" if self.user else "NA",
            "application_bytes": self.appbytes,
            "live_keys": sorted(loc),
            "victim_sequence": self.victims,
            "relocation_sequence": self.moved,
            "error_codes": self.errors,
            "open_count": self.open_count(),
            "active_count": self.active_count(),
        }


def replay(spec: dict[str, Any], policy: str) -> dict[str, Any]:
    r = Reference(spec, policy)
    out = []
    for idx, event in enumerate(spec["events"]):
        checkpoint = copy.deepcopy(r)
        wanted = event.get("expect_error")
        try:
            action = r.event(event)
            if wanted:
                raise AssertionError(f"event {idx} expected {wanted}, but succeeded")
            out.append(r.snap(action))
        except RefFault as fault:
            if fault.code != wanted:
                raise
            r = checkpoint
            r.errors.append(fault.code)
            r.check()
            out.append(r.snap({"op": event["op"]}, error=fault.code))
    return {"journal": out, "summary": r.summary()}


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(f"usage: {Path(sys.argv[0]).name} CASE.json [POLICY]", file=sys.stderr)
        return 2
    spec = json.loads(Path(sys.argv[1]).read_text())
    pol = sys.argv[2] if len(sys.argv) == 3 else "GreedyValidFraction"
    print(json.dumps(replay(spec, pol), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
