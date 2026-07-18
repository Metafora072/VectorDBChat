#!/usr/bin/env python3
"""Run the ten hand-computable Z0A traces against both implementations."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from reference_sim import replay
from zns_sim import run_case


HERE = Path(__file__).resolve().parent
CASES = HERE / "cases"
POLICIES = ("GreedyValidFraction", "OracleMinCopy")


def validate_request_closure(case: dict) -> None:
    requests = case.get("requests", {})
    observed: dict[str, int] = {}
    for event in case["events"]:
        if event["op"] != "write" or "request_id" not in event:
            continue
        rid = str(event["request_id"])
        observed[rid] = observed.get(rid, 0) + int(event["page_bytes"])
    if set(observed) != set(requests):
        raise AssertionError(
            f"{case['name']}: request IDs differ: events={sorted(observed)} manifest={sorted(requests)}"
        )
    for rid, total in observed.items():
        returned = int(requests[rid]["returned_bytes"])
        if total != returned:
            raise AssertionError(f"{case['name']}: request {rid}: page_bytes={total}, returned={returned}")


def check_expected(case: dict, summary: dict) -> None:
    for key, wanted in case["expected"].items():
        got = summary.get(key)
        if got != wanted:
            raise AssertionError(f"{case['name']}: expected {key}={wanted!r}, got {got!r}")


def main() -> int:
    paths = sorted(CASES.glob("*.json"))
    if len(paths) != 10:
        raise AssertionError(f"expected exactly 10 hand cases, found {len(paths)}")

    passed = 0
    for path in paths:
        case = json.loads(path.read_text())
        validate_request_closure(case)
        policy_outputs = {}
        for policy in POLICIES:
            primary = run_case(case, policy)
            reference = replay(case, policy)
            if primary != reference:
                p = json.dumps(primary, indent=2, sort_keys=True)
                r = json.dumps(reference, indent=2, sort_keys=True)
                raise AssertionError(f"{case['name']} {policy}: primary/reference mismatch\nPRIMARY\n{p}\nREFERENCE\n{r}")
            check_expected(case, primary["summary"])
            policy_outputs[policy] = primary

        # Equal capacity and FULL-only victim eligibility make the conservative
        # one-step OracleMinCopy exactly equivalent to GreedyValidFraction.
        if policy_outputs[POLICIES[0]] != policy_outputs[POLICIES[1]]:
            raise AssertionError(f"{case['name']}: one-step oracle diverged from greedy")
        passed += 1
        s = policy_outputs[POLICIES[0]]["summary"]
        print(
            f"PASS {path.name}: new={s['new_logical_blocks']} reloc={s['relocated_blocks']} "
            f"resets={s['reset_count']} HostWA={s['host_wa_fraction']} errors={s['error_codes']}"
        )

    print(f"PASS all {passed} hand cases; primary==reference; Greedy==one-step OracleMinCopy")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise
