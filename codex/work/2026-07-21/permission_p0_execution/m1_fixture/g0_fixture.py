#!/usr/bin/env python3
"""Deterministic control-flow witness for stale approximate ACL state.

This is a standalone semantic model.  It is intentionally not linked to, and
does not claim to reproduce the performance of, PipeANN, DGAI, or OdinANN.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, MutableMapping, Sequence


TARGET = "T"
DECOY = "A"
BRIDGE = "B"
ENTRY = "E"

REQUIRED_EVENT_FIELDS = (
    "approx_true",
    "approx_false",
    "false_to_connectivity_pool",
    "bridge_promoted",
    "bridge_rejected",
    "main_pool_read",
    "backend_cache_hit",
    "device_submit",
    "exact_allow",
    "exact_deny",
)


@dataclass(frozen=True)
class Node:
    node_id: str
    approx_distance: float
    exact_allowed: bool
    backend_cached: bool = False


# Four nodes are sufficient.  B is an unauthorized connectivity bridge; T is
# the newly granted true top-1; A is an authorized but farther decoy.
NODES: Mapping[str, Node] = {
    ENTRY: Node(ENTRY, approx_distance=0.0, exact_allowed=False, backend_cached=True),
    BRIDGE: Node(BRIDGE, approx_distance=0.2, exact_allowed=False),
    TARGET: Node(TARGET, approx_distance=0.7, exact_allowed=True),
    DECOY: Node(DECOY, approx_distance=1.0, exact_allowed=True),
}

NEIGHBORS: Mapping[str, Sequence[str]] = {
    ENTRY: (BRIDGE, TARGET, DECOY),
    BRIDGE: (),
    TARGET: (),
    DECOY: (),
}

BRIDGE_DISTANCE_BAND_MAX = 0.5


def _new_result(strategy: str, approximate_state: str) -> Dict[str, object]:
    result: Dict[str, object] = {
        "strategy": strategy,
        "approximate_state": approximate_state,
        "node_count": len(NODES),
        "authorized_top1": TARGET,
        "returned_node": None,
        "termination_reason": None,
        "target_node_event_sequence": [],
        "event_log": [],
    }
    result.update({field: 0 for field in REQUIRED_EVENT_FIELDS})
    return result


def _event(
    result: MutableMapping[str, object],
    event: str,
    node_id: str,
    *,
    detail: str = "",
) -> None:
    event_log = result["event_log"]
    assert isinstance(event_log, list)
    event_log.append({"seq": len(event_log), "event": event, "node": node_id, "detail": detail})
    if event in REQUIRED_EVENT_FIELDS:
        result[event] = int(result[event]) + 1
    if node_id == TARGET:
        target_log = result["target_node_event_sequence"]
        assert isinstance(target_log, list)
        target_log.append(event)


def _read_and_verify(result: MutableMapping[str, object], node_id: str) -> bool:
    """Model a main-pool read and keep cache hits distinct from submissions."""

    node = NODES[node_id]
    _event(result, "main_pool_read", node_id)
    if node.backend_cached:
        _event(result, "backend_cache_hit", node_id)
    else:
        _event(result, "device_submit", node_id)
    if node.exact_allowed:
        _event(result, "exact_allow", node_id)
        return True
    _event(result, "exact_deny", node_id)
    return False


def _terminate(
    result: MutableMapping[str, object], returned_node: str, target_detail: str
) -> None:
    result["returned_node"] = returned_node
    result["termination_reason"] = "l_search_satisfied_after_exact_allow"
    _event(result, "returned", returned_node)
    _event(
        result,
        "termination_l_search_satisfied",
        TARGET,
        detail=target_detail,
    )


def run_in_filter(approximate_state: str) -> Dict[str, object]:
    """Model approximate admission, bounded tunneling, and exact verification."""

    result = _new_result("IN_FILTER", approximate_state)
    _read_and_verify(result, ENTRY)

    main_pool: List[str] = []
    for node_id in NEIGHBORS[ENTRY]:
        approximate_true = node_id == DECOY or (
            node_id == TARGET and approximate_state == "fresh"
        )
        if approximate_true:
            _event(result, "approx_true", node_id)
            _event(result, "main_pool_admit", node_id)
            main_pool.append(node_id)
            continue

        _event(result, "approx_false", node_id)
        _event(result, "false_to_connectivity_pool", node_id)
        if NODES[node_id].approx_distance <= BRIDGE_DISTANCE_BAND_MAX:
            _event(result, "bridge_promoted", node_id)
            _event(result, "main_pool_admit", node_id)
            main_pool.append(node_id)
        else:
            _event(result, "bridge_rejected", node_id)

    for node_id in sorted(main_pool, key=lambda n: NODES[n].approx_distance):
        if _read_and_verify(result, node_id):
            detail = (
                "target returned"
                if node_id == TARGET
                else "target was rejected as a bridge and remained unread"
            )
            _terminate(result, node_id, detail)
            return result
    raise AssertionError("fixture exhausted the main pool without an exact-allowed result")


def run_pre_filter(approximate_state: str) -> Dict[str, object]:
    """Model PRE_FILTER candidate materialization before distance ordering.

    PRE_FILTER does not invoke the IN_FILTER approximate callback, so its
    approx/bridge counters intentionally remain zero.  The stale materialized
    ID set omits T, which leaves no later recovery point.
    """

    result = _new_result("PRE_FILTER", approximate_state)
    materialized = [DECOY]
    if approximate_state == "fresh":
        materialized.append(TARGET)
        _event(result, "pre_filter_include", TARGET)
    else:
        _event(result, "pre_filter_omit", TARGET)

    for node_id in sorted(materialized, key=lambda n: NODES[n].approx_distance):
        _event(result, "main_pool_admit", node_id)
        if _read_and_verify(result, node_id):
            detail = (
                "target materialized and returned"
                if node_id == TARGET
                else "target was absent from the stale materialized ID set"
            )
            _terminate(result, node_id, detail)
            return result
    raise AssertionError("fixture exhausted PRE_FILTER candidates")


def run_post_filter(approximate_state: str) -> Dict[str, object]:
    """Model unfiltered traversal followed by exact authorization.

    The POST_FILTER approximate callback is unconditionally true.  Therefore
    fresh and stale policy-summary states must produce identical control flow.
    """

    result = _new_result("POST_FILTER", approximate_state)
    _read_and_verify(result, ENTRY)

    main_pool: List[str] = []
    for node_id in NEIGHBORS[ENTRY]:
        _event(result, "approx_true", node_id, detail="unconditional POST_FILTER callback")
        _event(result, "main_pool_admit", node_id)
        main_pool.append(node_id)

    for node_id in sorted(main_pool, key=lambda n: NODES[n].approx_distance):
        if _read_and_verify(result, node_id):
            _terminate(result, node_id, "target returned; approximate state was not consulted")
            return result
    raise AssertionError("fixture exhausted POST_FILTER candidates")


def run_case(strategy: str, approximate_state: str) -> Dict[str, object]:
    if approximate_state not in {"fresh", "stale"}:
        raise ValueError(f"unsupported approximate state: {approximate_state}")
    runners = {
        "IN_FILTER": run_in_filter,
        "PRE_FILTER": run_pre_filter,
        "POST_FILTER": run_post_filter,
    }
    try:
        return runners[strategy](approximate_state)
    except KeyError as exc:
        raise ValueError(f"unsupported strategy: {strategy}") from exc


def run_all() -> List[Dict[str, object]]:
    return [
        run_case(strategy, state)
        for strategy in ("IN_FILTER", "PRE_FILTER", "POST_FILTER")
        for state in ("fresh", "stale")
    ]


def _without_state(result: Mapping[str, object]) -> Dict[str, object]:
    return {key: value for key, value in result.items() if key != "approximate_state"}


def assert_contract(results: Iterable[Mapping[str, object]]) -> None:
    by_case = {
        (str(result["strategy"]), str(result["approximate_state"])): result
        for result in results
    }
    assert len(by_case) == 6

    for result in by_case.values():
        assert result["node_count"] <= 12
        assert result["authorized_top1"] == TARGET
        assert result["termination_reason"] == "l_search_satisfied_after_exact_allow"
        for field in REQUIRED_EVENT_FIELDS:
            assert field in result
            assert isinstance(result[field], int)
            assert result[field] >= 0
        assert result["main_pool_read"] == (
            result["backend_cache_hit"] + result["device_submit"]
        )

    in_fresh = by_case[("IN_FILTER", "fresh")]
    in_stale = by_case[("IN_FILTER", "stale")]
    assert in_fresh["returned_node"] == TARGET
    assert in_stale["returned_node"] == DECOY
    assert (
        in_fresh["approx_true"],
        in_fresh["approx_false"],
        in_fresh["false_to_connectivity_pool"],
        in_fresh["bridge_promoted"],
        in_fresh["bridge_rejected"],
    ) == (2, 1, 1, 1, 0)
    assert (
        in_stale["approx_true"],
        in_stale["approx_false"],
        in_stale["false_to_connectivity_pool"],
        in_stale["bridge_promoted"],
        in_stale["bridge_rejected"],
    ) == (1, 2, 2, 1, 1)
    for case in (in_fresh, in_stale):
        assert (
            case["main_pool_read"],
            case["backend_cache_hit"],
            case["device_submit"],
            case["exact_allow"],
            case["exact_deny"],
        ) == (3, 1, 2, 1, 2)
    assert in_fresh["target_node_event_sequence"] == [
        "approx_true",
        "main_pool_admit",
        "main_pool_read",
        "device_submit",
        "exact_allow",
        "returned",
        "termination_l_search_satisfied",
    ]
    assert in_stale["target_node_event_sequence"] == [
        "approx_false",
        "false_to_connectivity_pool",
        "bridge_rejected",
        "termination_l_search_satisfied",
    ]

    pre_fresh = by_case[("PRE_FILTER", "fresh")]
    pre_stale = by_case[("PRE_FILTER", "stale")]
    assert pre_fresh["returned_node"] == TARGET
    assert pre_stale["returned_node"] == DECOY
    assert pre_fresh["target_node_event_sequence"] == [
        "pre_filter_include",
        "main_pool_admit",
        "main_pool_read",
        "device_submit",
        "exact_allow",
        "returned",
        "termination_l_search_satisfied",
    ]
    assert pre_stale["target_node_event_sequence"] == [
        "pre_filter_omit",
        "termination_l_search_satisfied",
    ]
    for case in (pre_fresh, pre_stale):
        assert (
            case["main_pool_read"],
            case["backend_cache_hit"],
            case["device_submit"],
            case["exact_allow"],
            case["exact_deny"],
        ) == (1, 0, 1, 1, 0)
    for field in (
        "approx_true",
        "approx_false",
        "false_to_connectivity_pool",
        "bridge_promoted",
        "bridge_rejected",
    ):
        assert pre_fresh[field] == 0
        assert pre_stale[field] == 0

    post_fresh = by_case[("POST_FILTER", "fresh")]
    post_stale = by_case[("POST_FILTER", "stale")]
    assert post_fresh["returned_node"] == TARGET
    assert post_stale["returned_node"] == TARGET
    for case in (post_fresh, post_stale):
        assert (
            case["approx_true"],
            case["approx_false"],
            case["false_to_connectivity_pool"],
            case["bridge_promoted"],
            case["bridge_rejected"],
        ) == (3, 0, 0, 0, 0)
        assert (
            case["main_pool_read"],
            case["backend_cache_hit"],
            case["device_submit"],
            case["exact_allow"],
            case["exact_deny"],
        ) == (3, 1, 2, 1, 2)
    assert _without_state(post_fresh) == _without_state(post_stale)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pretty", action="store_true", help="emit one indented JSON document instead of JSONL"
    )
    parser.add_argument(
        "--strategy", choices=("IN_FILTER", "PRE_FILTER", "POST_FILTER")
    )
    parser.add_argument("--state", choices=("fresh", "stale"))
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if (args.strategy is None) != (args.state is None):
        raise SystemExit("--strategy and --state must be supplied together")

    results = run_all()
    assert_contract(results)
    selected = (
        [run_case(args.strategy, args.state)]
        if args.strategy is not None
        else results
    )
    if args.pretty:
        print(json.dumps(selected, indent=2, sort_keys=True))
    else:
        for result in selected:
            print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
