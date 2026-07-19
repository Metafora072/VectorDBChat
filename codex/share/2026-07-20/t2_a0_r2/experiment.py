#!/usr/bin/env python3
"""Deterministic T2-A0-R2 closed-loop path-dependence experiment.

Standard-library only.  The formal workload and all IDs are materialized before
execution.  See the adjacent prelaunch gate and config.json.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import math
import os
import resource
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "t2-a0-r2-run-v1"
MODELS = ("closed_loop", "open_loop_query", "write_disabled", "transparent_retrieval")
POLICIES = ("LRU", "LFU_RECENCY")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_int(*parts: Any) -> int:
    return int(digest(list(parts)), 16)


def write_json_exclusive(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(canonical_bytes(value) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def read_json(path: Path) -> Any:
    with path.open("rb") as handle:
        return json.load(handle)


def append_jsonl(handle: Any, value: Any) -> None:
    handle.write(canonical_bytes(value) + b"\n")


def allocated_bytes(root: Path) -> int:
    total = 0
    if not root.exists():
        return 0
    for path in root.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_blocks * 512
        except FileNotFoundError:
            pass
    return total


def peak_rss_bytes() -> int:
    # Linux ru_maxrss is KiB.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024


def check_resources(started: float, root: Path, config: dict[str, Any]) -> dict[str, Any]:
    now = time.monotonic()
    usage = {
        "wall_seconds": now - started,
        "peak_rss_bytes": peak_rss_bytes(),
        "allocated_bytes": allocated_bytes(root),
    }
    limits = config["resources"]
    violations = []
    if usage["wall_seconds"] > limits["max_wall_seconds"]:
        violations.append("wall")
    if usage["peak_rss_bytes"] > limits["max_rss_bytes"]:
        violations.append("rss")
    if usage["allocated_bytes"] > limits["max_attempt_bytes"]:
        violations.append("space")
    if violations:
        raise RuntimeError("resource limit exceeded: " + ",".join(violations))
    return usage


def event_schedule(family: str, count: int, instance_id: str, phase: str, k: int) -> list[int]:
    offset = stable_int(instance_id, phase, "offset") % k
    if family in ("cyclic", "sanity-cyclic"):
        sequence = [(offset + i) % k for i in range(count)]
    elif family in ("bursty", "sanity-bursty"):
        sequence = [(offset + i // 3) % k for i in range(count)]
    elif family == "interleaved":
        sequence = [(offset + 5 * i) % k for i in range(count)]
    elif family == "reversal":
        sequence = []
        for i in range(count):
            block, pos = divmod(i, k)
            logical = pos if block % 2 == 0 else k - 1 - pos
            sequence.append((offset + logical) % k)
    else:
        raise ValueError(f"unknown family {family}")

    # The final low-capacity sweep visits every logical memory without changing
    # task semantics.  It ensures the pre-registered witness window is observable
    # rather than selected after outcomes are seen.
    if phase == "low" and count >= k:
        permutation = sorted(range(k), key=lambda mid: digest([instance_id, phase, mid]))
        sequence[-k:] = permutation
    return sequence


def task_operator(family: str) -> dict[str, int]:
    base_family = family.removeprefix("sanity-")
    operators = {
        "cyclic": {"as": 1, "at": 1, "ap": 1, "wa": 3, "wd": 1, "wt": 1, "na": 5, "nd": 7, "nt": 1},
        "bursty": {"as": 2, "at": 1, "ap": 3, "wa": 5, "wd": 2, "wt": 1, "na": 3, "nd": 11, "nt": 2},
        "interleaved": {"as": 1, "at": 3, "ap": 2, "wa": 7, "wd": 1, "wt": 2, "na": 11, "nd": 5, "nt": 1},
        "reversal": {"as": 3, "at": 2, "ap": 1, "wa": 2, "wd": 5, "wt": 3, "na": 7, "nd": 3, "nt": 5},
    }
    if base_family not in operators:
        raise ValueError(f"no task operator for {family}")
    return operators[base_family]


def make_events(instance_id: str, family: str, phase: str, count: int, k: int) -> list[dict[str, Any]]:
    events = []
    for index, memory_number in enumerate(event_schedule(family, count, instance_id, phase, k)):
        base = [SCHEMA, instance_id, family, phase, index, memory_number]
        event = {
            "phase": phase,
            "index": index,
            "logical_memory_id": f"m{memory_number:02d}",
            "signal": stable_int(base, "signal") % 257,
            "delta": stable_int(base, "delta") % 257,
            "target": stable_int(base, "target") % 257,
            "open_loop_token": stable_int(base, "open-loop-token") % 257,
            "task_operator": task_operator(family),
        }
        event["event_id"] = digest(["event", base, event])
        event["event_hash"] = digest(event)
        events.append(event)
    return events


def family_of(instance_id: str) -> str:
    return instance_id.rsplit("-", 1)[0]


def make_workloads(config: dict[str, Any], sanity: bool) -> dict[str, Any]:
    section = config["sanity" if sanity else "formal"]
    k = config["cache"]["logical_memories"]
    workloads = []
    for instance_id in section["instances"]:
        family = family_of(instance_id)
        workloads.append(
            {
                "instance_id": instance_id,
                "family": family,
                "prefix": make_events(instance_id, family, "prefix", section["prefix_steps"], k),
                "low": make_events(instance_id, family, "low", section["low_steps"], k),
                "evaluation": make_events(
                    instance_id, family, "evaluation", section["evaluation_steps"], k
                ),
            }
        )
    result = {
        "schema": "t2-a0-r2-workload-v1",
        "sanity": sanity,
        "instances": workloads,
    }
    result["content_sha256"] = digest(result)
    return result


def top_c(state: dict[str, Any]) -> list[str]:
    capacity = state["capacity"]
    policy = state["policy"]
    metadata = state["policy_meta"]
    if policy == "LRU":
        key = lambda mid: (metadata[mid]["last_request"], mid)
    elif policy == "LFU_RECENCY":
        key = lambda mid: (metadata[mid]["frequency"], metadata[mid]["last_request"], mid)
    else:
        raise ValueError(policy)
    ranked = sorted(metadata, key=key, reverse=True)
    return sorted(ranked[:capacity])


def resize(state: dict[str, Any], capacity: int) -> dict[str, Any]:
    before_capacity = state["capacity"]
    before = set(state["active"])
    state["capacity"] = capacity
    state["active"] = top_c(state)
    after = set(state["active"])
    return {
        "before_capacity": before_capacity,
        "after_capacity": capacity,
        "before_active": sorted(before),
        "after_active": sorted(after),
        "evicted": sorted(before - after),
        "admitted": sorted(after - before),
        "policy_meta_hash": digest(state["policy_meta"]),
        "durable_live_hash": digest(live_durable_view(state)),
    }


def initial_state(instance_id: str, policy: str, config: dict[str, Any]) -> dict[str, Any]:
    k = config["cache"]["logical_memories"]
    versions: dict[str, Any] = {}
    latest: dict[str, str] = {}
    head: dict[str, Any] = {}
    metadata: dict[str, Any] = {}
    for number in range(k):
        mid = f"m{number:02d}"
        payload = stable_int(SCHEMA, instance_id, mid, "initial-payload") % 257
        token = stable_int(SCHEMA, instance_id, mid, "initial-token") % 257
        version = {
            "logical_memory_id": mid,
            "parent_version_id": None,
            "payload": payload,
            "next_token": token,
            "created_by_action": None,
            "event_id": "INITIAL",
        }
        version_id = digest(["version", instance_id, version])
        version["version_id"] = version_id
        versions[version_id] = version
        latest[mid] = version_id
        head[mid] = {
            "source_version_id": version_id,
            "semantic_token": token,
            "dependency_action_id": None,
        }
        metadata[mid] = {"frequency": 1, "last_request": number - k}
    state = {
        "schema": "t2-a0-r2-state-v1",
        "instance_id": instance_id,
        "policy": policy,
        "event_cursor": 0,
        "logical_clock": 0,
        "versions": versions,
        "latest": latest,
        "head": head,
        "active": sorted(metadata),
        "policy_meta": metadata,
        "capacity": k,
        "last_action": None,
        "action_history_hash": digest([]),
        "semantic_action_history_hash": digest([]),
        "cumulative_outcome_numerator": 0,
    }
    return state


def live_durable_view(state: dict[str, Any]) -> dict[str, Any]:
    return {
        mid: {
            "payload": state["versions"][state["latest"][mid]]["payload"],
            "next_token": state["versions"][state["latest"][mid]]["next_token"],
        }
        for mid in sorted(state["latest"])
    }


def semantic_query_state(state: dict[str, Any]) -> dict[str, int]:
    return {mid: state["head"][mid]["semantic_token"] for mid in sorted(state["head"])}


def semantic_action_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "last_action_value": None if state["last_action"] is None else state["last_action"]["value"],
    }


def state_hash(state: dict[str, Any]) -> str:
    return digest(state)


def query_for(state: dict[str, Any], event: dict[str, Any], model: str) -> dict[str, Any]:
    mid = event["logical_memory_id"]
    if model == "open_loop_query":
        token = event["open_loop_token"]
        source = None
        dependency_action = None
    else:
        token = state["head"][mid]["semantic_token"]
        source = state["head"][mid]["source_version_id"]
        dependency_action = state["head"][mid]["dependency_action_id"]
    semantic = {"logical_memory_id": mid, "semantic_token": token}
    return {
        **semantic,
        "semantic_hash": digest(semantic),
        "source_version_id": source,
        "dependency_action_id": dependency_action,
    }


def circular_distance(a: int, b: int, modulus: int) -> int:
    raw = abs(a - b)
    return min(raw, modulus - raw)


def execute_step(
    state: dict[str, Any], event: dict[str, Any], model: str, branch: str, fork_hash: str
) -> dict[str, Any]:
    pre_hash = state_hash(state)
    pre_durable_live_hash = digest(live_durable_view(state))
    pre_semantic_query_state_hash = digest(semantic_query_state(state))
    pre_semantic_action_state_hash = digest(semantic_action_state(state))
    mid = event["logical_memory_id"]
    query = query_for(state, event, model)
    version_id = state["latest"][mid]
    durable_payload = state["versions"][version_id]["payload"]
    resident_before = mid in state["active"]
    if resident_before:
        visible_payload = durable_payload
        miss_class = "HIT"
    elif model == "transparent_retrieval":
        visible_payload = durable_payload
        miss_class = "TRANSPARENT_CAPACITY_MISS"
    else:
        visible_payload = None
        miss_class = "CAPACITY_MISS"

    operator = event["task_operator"]
    action_value = (
        operator["as"] * event["signal"]
        + operator["at"] * query["semantic_token"]
        + operator["ap"] * (visible_payload or 0)
    ) % 257
    action_basis = {
        "instance_id": state["instance_id"],
        "event_id": event["event_id"],
        "query_semantic_hash": query["semantic_hash"],
        "visible_payload": visible_payload,
        "action_value": action_value,
    }
    action = {
        "action_id": digest(["action", action_basis]),
        "semantic_hash": digest({"value": action_value}),
        "value": action_value,
    }

    write_record = None
    new_payload = (
        operator["wa"] * action_value
        + operator["wd"] * event["delta"]
        + operator["wt"] * query["semantic_token"]
    ) % 257
    next_token = (
        operator["na"] * action_value
        + operator["nd"] * event["delta"]
        + operator["nt"] * query["semantic_token"]
    ) % 257
    if model != "write_disabled":
        parent_id = state["latest"][mid]
        version = {
            "logical_memory_id": mid,
            "parent_version_id": parent_id,
            "payload": new_payload,
            "next_token": next_token,
            "created_by_action": action["action_id"],
            "event_id": event["event_id"],
        }
        new_version_id = digest(["version", state["instance_id"], version])
        version["version_id"] = new_version_id
        state["versions"][new_version_id] = version
        state["latest"][mid] = new_version_id
        state["head"][mid] = {
            "source_version_id": new_version_id,
            "semantic_token": next_token,
            "dependency_action_id": action["action_id"],
        }
        write_record = version
    else:
        # Preserve action -> future-query feedback while disabling only the
        # durable write/latest-version edge.
        state["head"][mid] = {
            "source_version_id": None,
            "semantic_token": next_token,
            "dependency_action_id": action["action_id"],
        }

    state["logical_clock"] += 1
    state["event_cursor"] += 1
    state["policy_meta"][mid]["frequency"] += 1
    state["policy_meta"][mid]["last_request"] = state["logical_clock"]
    active_before = set(state["active"])
    state["active"] = top_c(state)
    evicted = sorted(active_before - set(state["active"]))
    admitted = sorted(set(state["active"]) - active_before)
    outcome = 128 - circular_distance(action_value, event["target"], 257)
    state["cumulative_outcome_numerator"] += outcome
    state["last_action"] = action
    state["action_history_hash"] = digest([state["action_history_hash"], action["action_id"]])
    state["semantic_action_history_hash"] = digest(
        [state["semantic_action_history_hash"], action_value]
    )

    log = {
        "schema": "t2-a0-r2-step-v1",
        "branch": branch,
        "model": model,
        "policy": state["policy"],
        "phase": event["phase"],
        "step_index": event["index"],
        "event_id": event["event_id"],
        "event_hash": event["event_hash"],
        "capacity": state["capacity"],
        "fork_hash": fork_hash,
        "pre_state_hash": pre_hash,
        "pre_durable_live_hash": pre_durable_live_hash,
        "pre_semantic_query_state_hash": pre_semantic_query_state_hash,
        "pre_semantic_action_state_hash": pre_semantic_action_state_hash,
        "post_state_hash": state_hash(state),
        "query": query,
        "retrieved_memory_ids": [version_id] if visible_payload is not None else [],
        "referenced_durable_version_id": version_id,
        "visible_payload": visible_payload,
        "miss_classification": miss_class,
        "action": action,
        "memory_reads": [version_id] if visible_payload is not None else [],
        "memory_writes": [] if write_record is None else [write_record],
        "memory_deletes": [],
        "durable_live_hash": digest(live_durable_view(state)),
        "durable_audit_hash": digest(state["versions"]),
        "query_state_hash": digest(state["head"]),
        "semantic_query_state_hash": digest(semantic_query_state(state)),
        "semantic_action_state_hash": digest(semantic_action_state(state)),
        "policy_state_hash": digest(
            {"active": state["active"], "metadata": state["policy_meta"], "capacity": state["capacity"]}
        ),
        "active_memory_ids": state["active"],
        "resident_before": resident_before,
        "admitted_memory_ids": admitted,
        "evicted_memory_ids": evicted,
        "outcome_contribution_numerator": outcome,
        "outcome_contribution_normalized": outcome / 128,
        "cumulative_outcome_numerator": state["cumulative_outcome_numerator"],
    }
    return log


def run_prefix(
    instance: dict[str, Any], policy: str, config: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = initial_state(instance["instance_id"], policy, config)
    logs = []
    for event in instance["prefix"]:
        logs.append(execute_step(state, event, "closed_loop", "COMMON", "PREFIX"))
    return state, logs


def semantic_log_view(logs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = (
        "phase",
        "step_index",
        "event_id",
        "capacity",
        "query",
        "miss_classification",
        "action",
        "memory_writes",
        "durable_live_hash",
        "query_state_hash",
        "policy_state_hash",
        "outcome_contribution_numerator",
    )
    return [{key: row[key] for key in keys} for row in logs]


def run_branch(
    fork_bytes: bytes,
    model: str,
    branch: str,
    capacity_low: int,
    capacity_restore: int,
    low_events: list[dict[str, Any]],
    evaluation_events: list[dict[str, Any]],
    fork_hash: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    state = json.loads(fork_bytes)
    low_resize = resize(state, capacity_low)
    low_resize["phase"] = "LOW_ENTRY"
    low_resize["branch"] = branch
    logs = [execute_step(state, event, model, branch, fork_hash) for event in low_events]
    restore_resize = resize(state, capacity_restore)
    restore_resize["phase"] = "RESTORE_ENTRY"
    restore_resize["branch"] = branch
    if len(state["active"]) != capacity_restore:
        raise RuntimeError("restore occupancy closure failed")
    logs.extend(execute_step(state, event, model, branch, fork_hash) for event in evaluation_events)
    return state, logs, [low_resize, restore_resize]


def divergence_metrics(
    logs_a: list[dict[str, Any]], logs_b: list[dict[str, Any]], evaluation_steps: int
) -> dict[str, Any]:
    eval_a = [row for row in logs_a if row["phase"] == "evaluation"]
    eval_b = [row for row in logs_b if row["phase"] == "evaluation"]
    if len(eval_a) != evaluation_steps or len(eval_b) != evaluation_steps:
        raise RuntimeError("evaluation length mismatch")
    flags = {"Q": [], "A": [], "M": [], "Y": [], "P": [], "QS": [], "AS": []}
    for left, right in zip(eval_a, eval_b, strict=True):
        if left["event_id"] != right["event_id"]:
            raise RuntimeError("exogenous stream mismatch")
        flags["Q"].append(left["query"]["semantic_hash"] != right["query"]["semantic_hash"])
        flags["A"].append(left["action"]["value"] != right["action"]["value"])
        flags["M"].append(left["durable_live_hash"] != right["durable_live_hash"])
        flags["Y"].append(
            left["outcome_contribution_numerator"] != right["outcome_contribution_numerator"]
        )
        flags["P"].append(left["policy_state_hash"] != right["policy_state_hash"])
        flags["QS"].append(
            left["semantic_query_state_hash"] != right["semantic_query_state_hash"]
        )
        flags["AS"].append(
            left["semantic_action_state_hash"] != right["semantic_action_state_hash"]
        )
    metrics = {key: sum(values) / evaluation_steps for key, values in flags.items()}
    metrics["D"] = sum(metrics[key] for key in ("Q", "A", "M", "Y")) / 4
    metrics["B"] = (metrics["A"] + metrics["Y"]) / 2
    evaluation_delta = (
        sum(row["outcome_contribution_numerator"] for row in eval_a)
        - sum(row["outcome_contribution_numerator"] for row in eval_b)
    ) / 128
    total_delta = (
        eval_a[-1]["cumulative_outcome_numerator"] - eval_b[-1]["cumulative_outcome_numerator"]
    ) / 128
    metrics["evaluation_cumulative_outcome_delta_signed"] = evaluation_delta
    metrics["evaluation_cumulative_outcome_delta_abs"] = abs(evaluation_delta)
    metrics["total_cumulative_outcome_delta_signed"] = total_delta
    metrics["low_window_cumulative_outcome_delta_signed"] = total_delta - evaluation_delta
    metrics["end_joint"] = bool(flags["Q"][-1] and flags["A"][-1] and flags["M"][-1])

    def tau(include_state: bool) -> int:
        for index in range(evaluation_steps):
            fields = ("Q", "A", "Y", "M", "P", "QS", "AS") if include_state else ("Q", "A", "Y")
            if all(not any(flags[field][index:]) for field in fields):
                return index + 1
        return evaluation_steps + 1

    metrics["tau_behavior"] = tau(False)
    metrics["tau_state"] = tau(True)
    return metrics


def reconstruct_witness(
    logs_a: list[dict[str, Any]], logs_b: list[dict[str, Any]]
) -> dict[str, Any] | None:
    low_a = [row for row in logs_a if row["phase"] == "low"]
    low_b = [row for row in logs_b if row["phase"] == "low"]
    eval_a = [row for row in logs_a if row["phase"] == "evaluation"]
    eval_b = [row for row in logs_b if row["phase"] == "evaluation"]
    versions_a = {
        version["version_id"]: version for row in logs_a for version in row["memory_writes"]
    }
    versions_b = {
        version["version_id"]: version for row in logs_b for version in row["memory_writes"]
    }

    def ancestry_path(descendant: str, ancestor: str, versions: dict[str, Any]) -> list[str] | None:
        path = [descendant]
        cursor = descendant
        seen = set()
        while cursor != ancestor and cursor not in seen and cursor in versions:
            seen.add(cursor)
            parent = versions[cursor]["parent_version_id"]
            if parent is None:
                return None
            path.append(parent)
            cursor = parent
        return path if cursor == ancestor else None
    candidates = []
    for left, right in zip(low_a, low_b, strict=True):
        if (
            left["pre_durable_live_hash"] == right["pre_durable_live_hash"]
            and left["pre_semantic_query_state_hash"]
            == right["pre_semantic_query_state_hash"]
            and left["query"]["semantic_hash"] == right["query"]["semantic_hash"]
            and left["miss_classification"] == "CAPACITY_MISS"
            and right["miss_classification"] == "HIT"
            and left["visible_payload"] is None
            and right["visible_payload"] is not None
            and left["action"]["value"] != right["action"]["value"]
            and left["memory_writes"]
            and right["memory_writes"]
        ):
            candidates.append((left, right))
    for low_left, low_right in reversed(candidates):
        version_a = low_left["memory_writes"][0]
        version_b = low_right["memory_writes"][0]
        candidate_index = low_left["step_index"]
        later_a = [row for row in logs_a if row["phase"] != "low" or row["step_index"] > candidate_index]
        later_b = [row for row in logs_b if row["phase"] != "low" or row["step_index"] > candidate_index]
        direct_use_a = next(
            (
                row
                for row in later_a
                if row["query"]["source_version_id"] == version_a["version_id"]
                and row["query"]["dependency_action_id"] == low_left["action"]["action_id"]
                and row["query"]["semantic_token"] == version_a["next_token"]
            ),
            None,
        )
        direct_use_b = next(
            (
                row
                for row in later_b
                if row["query"]["source_version_id"] == version_b["version_id"]
                and row["query"]["dependency_action_id"] == low_right["action"]["action_id"]
                and row["query"]["semantic_token"] == version_b["next_token"]
            ),
            None,
        )
        if direct_use_a is None or direct_use_b is None:
            continue
        for eval_left, eval_right in zip(eval_a, eval_b, strict=True):
            source_a = eval_left["query"]["source_version_id"]
            source_b = eval_right["query"]["source_version_id"]
            path_a = None if source_a is None else ancestry_path(source_a, version_a["version_id"], versions_a)
            path_b = None if source_b is None else ancestry_path(source_b, version_b["version_id"], versions_b)
            closes_a = bool(
                path_a
                and len(path_a) >= 2
                and version_a["created_by_action"] == low_left["action"]["action_id"]
                and eval_left["referenced_durable_version_id"] == source_a
                and source_a in eval_left["retrieved_memory_ids"]
                and source_a in eval_left["memory_reads"]
                and eval_left["miss_classification"] == "HIT"
            )
            closes_b = bool(
                path_b
                and len(path_b) >= 2
                and version_b["created_by_action"] == low_right["action"]["action_id"]
                and eval_right["referenced_durable_version_id"] == source_b
                and source_b in eval_right["retrieved_memory_ids"]
                and source_b in eval_right["memory_reads"]
                and eval_right["miss_classification"] == "HIT"
            )
            query_diverged = eval_left["query"]["semantic_hash"] != eval_right["query"]["semantic_hash"]
            action_diverged = eval_left["action"]["value"] != eval_right["action"]["value"]
            outcome_diverged = (
                eval_left["outcome_contribution_numerator"]
                != eval_right["outcome_contribution_numerator"]
            )
            direct_a_before = direct_use_a["phase"] == "low" or (
                direct_use_a["phase"] == "evaluation"
                and direct_use_a["step_index"] < eval_left["step_index"]
            )
            direct_b_before = direct_use_b["phase"] == "low" or (
                direct_use_b["phase"] == "evaluation"
                and direct_use_b["step_index"] < eval_right["step_index"]
            )
            if (
                closes_a
                and closes_b
                and direct_a_before
                and direct_b_before
                and query_diverged
                and action_diverged
                and outcome_diverged
            ):
                return {
                    "low_event_id": low_left["event_id"],
                    "action_a": low_left["action"]["action_id"],
                    "action_b": low_right["action"]["action_id"],
                    "version_a": version_a["version_id"],
                    "version_b": version_b["version_id"],
                    "future_event_id": eval_left["event_id"],
                    "future_query_a": eval_left["query"]["semantic_hash"],
                    "future_query_b": eval_right["query"]["semantic_hash"],
                    "direct_use_event_a": direct_use_a["event_id"],
                    "direct_use_event_b": direct_use_b["event_id"],
                    "direct_use_semantics": "query-token-use",
                    "lineage_path_a": path_a,
                    "lineage_path_b": path_b,
                    "future_referenced_version_a": eval_left["referenced_durable_version_id"],
                    "future_referenced_version_b": eval_right["referenced_durable_version_id"],
                    "downstream_action_diverged": action_diverged,
                    "downstream_outcome_diverged": outcome_diverged,
                }
    return None


def cell_id(policy: str, triplet: list[int], instance_id: str, model: str) -> str:
    return digest([policy, triplet, instance_id, model])[:24]


def run_one_cell(
    prefix_state: dict[str, Any],
    instance: dict[str, Any],
    policy: str,
    triplet: list[int],
    model: str,
    evaluation_steps: int,
    check_order: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    fork_bytes = canonical_bytes(prefix_state)
    fork_hash = hashlib.sha256(fork_bytes).hexdigest()
    state_a_probe = json.loads(fork_bytes)
    state_b_probe = json.loads(fork_bytes)
    state_a_probe["capacity"] = -1
    if canonical_bytes(state_b_probe) != fork_bytes:
        raise RuntimeError("fork deep-copy isolation failed")
    mid, low, restored = triplet
    if prefix_state["capacity"] != mid:
        raise RuntimeError("prefix capacity mismatch")
    end_a, logs_a, resize_a = run_branch(
        fork_bytes, model, "A", low, restored, instance["low"], instance["evaluation"], fork_hash
    )
    end_b, logs_b, resize_b = run_branch(
        fork_bytes, model, "B", mid, restored, instance["low"], instance["evaluation"], fork_hash
    )
    if check_order:
        _, reverse_b, reverse_resize_b = run_branch(
            fork_bytes, model, "B", mid, restored, instance["low"], instance["evaluation"], fork_hash
        )
        _, reverse_a, reverse_resize_a = run_branch(
            fork_bytes, model, "A", low, restored, instance["low"], instance["evaluation"], fork_hash
        )
        if semantic_log_view(logs_a) != semantic_log_view(reverse_a):
            raise RuntimeError("A branch order invariance failed")
        if semantic_log_view(logs_b) != semantic_log_view(reverse_b):
            raise RuntimeError("B branch order invariance failed")
        if resize_a != reverse_resize_a or resize_b != reverse_resize_b:
            raise RuntimeError("resize order invariance failed")
    metrics = divergence_metrics(logs_a, logs_b, evaluation_steps)
    witness = reconstruct_witness(logs_a, logs_b) if model == "closed_loop" else None
    summary = {
        "cell_id": cell_id(policy, triplet, instance["instance_id"], model),
        "policy": policy,
        "triplet": triplet,
        "instance_id": instance["instance_id"],
        "family": instance["family"],
        "model": model,
        "fork_hash": fork_hash,
        "fork_bytes_sha256_a": fork_hash,
        "fork_bytes_sha256_b": fork_hash,
        "metrics": metrics,
        "witness": witness,
        "resize_transitions": {"A": resize_a, "B": resize_b},
        "final_state_hash_a": state_hash(end_a),
        "final_state_hash_b": state_hash(end_b),
        "final_durable_live_hash_a": digest(live_durable_view(end_a)),
        "final_durable_live_hash_b": digest(live_durable_view(end_b)),
    }
    for row in logs_a + logs_b:
        row["cell_id"] = summary["cell_id"]
        row["instance_id"] = instance["instance_id"]
        row["family"] = instance["family"]
        row["triplet"] = triplet
    return summary, logs_a, logs_b


def stratified_bootstrap_ci(
    rows: list[dict[str, Any]], value_key: str, seed_material: Any, replicates: int = 2000
) -> tuple[float, float]:
    if not rows:
        return (0.0, 0.0)
    families = sorted({row["family"] for row in rows})
    strata = {family: [row[value_key] for row in rows if row["family"] == family] for family in families}
    means = []
    for rep in range(replicates):
        sample = []
        for family in families:
            values = strata[family]
            sample.extend(
                values[stable_int(seed_material, family, rep, j) % len(values)]
                for j in range(len(values))
            )
        means.append(sum(sample) / len(sample))
    means.sort()
    return means[math.floor(0.025 * (replicates - 1))], means[math.ceil(0.975 * (replicates - 1))]


def classify(pairs: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[tuple[str, tuple[int, ...], str], dict[str, dict[str, Any]]] = {}
    for pair in pairs:
        key = (pair["policy"], tuple(pair["triplet"]), pair["instance_id"])
        grouped.setdefault(key, {})[pair["model"]] = pair
    instance_rows = []
    for (policy, triplet, instance_id), models in sorted(grouped.items()):
        if set(models) != set(MODELS):
            raise RuntimeError("incomplete four-model group")
        closed = models["closed_loop"]
        controls = [models[name] for name in MODELS if name != "closed_loop"]
        cm = closed["metrics"]
        control_behavior = {row["model"]: row["metrics"]["B"] for row in controls}
        control_full = {row["model"]: row["metrics"]["D"] for row in controls}
        behavior_margin = cm["B"] - max(control_behavior.values())
        full_margin = cm["D"] - max(control_full.values())
        qualifies = bool(
            all(cm[key] > 0 for key in ("Q", "A", "M", "Y"))
            and cm["end_joint"]
            and cm["evaluation_cumulative_outcome_delta_abs"] > 0
            and cm["tau_state"] == config["formal"]["evaluation_steps"] + 1
            and closed["witness"] is not None
            and closed["witness"]["downstream_action_diverged"]
            and closed["witness"]["downstream_outcome_diverged"]
            and models["open_loop_query"]["metrics"]["Q"] == 0
            and models["write_disabled"]["metrics"]["M"] == 0
            and models["transparent_retrieval"]["metrics"]["D"] == 0
            and behavior_margin > 0
            and full_margin > 0
        )
        instance_rows.append(
            {
                "policy": policy,
                "triplet": list(triplet),
                "instance_id": instance_id,
                "family": closed["family"],
                "qualifies": qualifies,
                "behavior_margin": behavior_margin,
                "full_margin": full_margin,
                "closed_metrics": cm,
                "control_behavior": control_behavior,
                "control_full": control_full,
                "witness": closed["witness"],
            }
        )

    cells = []
    for policy in POLICIES:
        for triplet_list in config["capacity_triplets"]:
            rows = [
                row
                for row in instance_rows
                if row["policy"] == policy and row["triplet"] == triplet_list
            ]
            behavior_ci = stratified_bootstrap_ci(
                rows, "behavior_margin", [policy, triplet_list, "behavior-margin"]
            )
            full_ci = stratified_bootstrap_ci(
                rows, "full_margin", [policy, triplet_list, "full-margin"]
            )
            family_counts = {
                family: sum(row["qualifies"] for row in rows if row["family"] == family)
                for family in config["formal"]["workload_families"]
            }
            supported = bool(
                len(rows) == 20
                and sum(row["qualifies"] for row in rows)
                >= config["classifier"]["cell_min_qualifying_instances"]
                and behavior_ci[0]
                > config["classifier"]["require_cell_bootstrap_behavior_margin_ci_lower_gt"]
                and full_ci[0] > 0
                and all(
                    count >= config["classifier"]["families_min_positives_per_supported_cell"]
                    for count in family_counts.values()
                )
            )
            cells.append(
                {
                    "policy": policy,
                    "triplet": triplet_list,
                    "qualifying_instances": sum(row["qualifies"] for row in rows),
                    "behavior_margin_ci95": list(behavior_ci),
                    "full_margin_ci95": list(full_ci),
                    "family_qualifying_counts": family_counts,
                    "supported": supported,
                }
            )
    supported_by_policy = {
        policy: [row["triplet"] for row in cells if row["policy"] == policy and row["supported"]]
        for policy in POLICIES
    }
    common = [
        triplet
        for triplet in supported_by_policy["LRU"]
        if triplet in supported_by_policy["LFU_RECENCY"]
    ]
    passed = bool(
        all(
            len(supported_by_policy[policy]) >= config["classifier"]["policy_min_supported_triplets"]
            for policy in POLICIES
        )
        and len(common) >= config["classifier"]["common_triplets_min"]
    )
    return {
        "outcome": "PASS-ENDOGENOUS-PATH-DEPENDENCE"
        if passed
        else "KILL-NO-CLOSED-LOOP-SEPARATION",
        "instance_rows": instance_rows,
        "cells": cells,
        "supported_triplets_by_policy": supported_by_policy,
        "common_supported_triplets": common,
    }


def source_tree_manifest(source_dir: Path) -> dict[str, str]:
    return {
        str(path.relative_to(source_dir)): file_digest(path)
        for path in sorted(source_dir.rglob("*"))
        if path.is_file()
    }


def mount_info(path: Path) -> dict[str, str]:
    resolved = str(path.resolve())
    candidates = []
    with Path("/proc/self/mountinfo").open("r", encoding="utf-8") as handle:
        for line in handle:
            fields = line.rstrip("\n").split()
            separator = fields.index("-")
            mountpoint = fields[4].replace("\\040", " ")
            if resolved == mountpoint or resolved.startswith(mountpoint.rstrip("/") + "/"):
                candidates.append(
                    (
                        len(mountpoint),
                        {
                            "mountpoint": mountpoint,
                            "major_minor": fields[2],
                            "fstype": fields[separator + 1],
                            "source": fields[separator + 2],
                            "options": fields[5],
                        },
                    )
                )
    if not candidates:
        raise RuntimeError(f"no mountinfo entry for {path}")
    return max(candidates, key=lambda item: item[0])[1]


def validate_config(config: dict[str, Any], attempt: Path, gate_path: Path) -> dict[str, Any]:
    expected_outcomes = {
        "PASS-ENDOGENOUS-PATH-DEPENDENCE",
        "KILL-NO-CLOSED-LOOP-SEPARATION",
        "FAIL-PROTOCOL-CLOSURE",
    }
    checks = {
        "schema": config.get("schema") == "t2-a0-r2-config-v1",
        "attempt_path": attempt == Path(config["attempt_root"]).resolve(),
        "attempt_basename": attempt.name == config["attempt_id"],
        "gate_exists": gate_path.is_file(),
        "gate_hash": gate_path.is_file() and file_digest(gate_path) == config["gate_sha256"],
        "models": tuple(config["models"]) == MODELS,
        "policies": tuple(config["cache"]["policies"]) == POLICIES,
        "triplets": len(config["capacity_triplets"]) == 5
        and all(len(t) == 3 and t[0] == 12 and t[2] == 12 and 0 < t[1] < 12 for t in config["capacity_triplets"]),
        "formal_instances": len(config["formal"]["instances"]) == 20
        and len(set(config["formal"]["instances"])) == 20,
        "sanity_disjoint": not set(config["formal"]["instances"])
        & set(config["sanity"]["instances"]),
        "horizons": (
            config["formal"]["prefix_steps"],
            config["formal"]["low_steps"],
            config["formal"]["evaluation_steps"],
        )
        == (48, 36, 96),
        "matrix": len(POLICIES)
        * len(config["capacity_triplets"])
        * len(config["formal"]["instances"])
        * len(MODELS)
        == config["formal"]["expected_paired_cells"]
        == 800,
        "zero_external": config["resources"]["llm_api_calls"] == 0
        and config["resources"]["gpu"] == 0
        and config["resources"]["external_agent_frameworks"] == 0,
        "resource_upper_bounds": config["resources"]["max_wall_seconds"] <= 7200
        and config["resources"]["max_rss_bytes"] <= 8 * 1024**3
        and config["resources"]["max_attempt_bytes"] <= 5 * 1024**3,
        "outcomes": set(config["allowed_outcomes"]) == expected_outcomes,
        "classifier": config["classifier"]["cell_min_qualifying_instances"] == 17
        and config["classifier"]["policy_min_supported_triplets"] == 3
        and config["classifier"]["common_triplets_min"] == 2
        and config["classifier"]["require_behavior_margin_over_each_control"] is True
        and config["classifier"]["require_full_divergence_margin_over_each_control"] is True,
    }
    storage_root = Path("/home/ubuntu/pz/VectorDB/data").resolve()
    storage_mount = mount_info(storage_root)
    checks["dedicated_nvme_path"] = attempt.is_relative_to(storage_root)
    checks["dedicated_nvme_device"] = storage_mount["source"] == "/dev/nvme8n1"
    checks["dedicated_nvme_fstype"] = storage_mount["fstype"] == "ext4"
    checks["dedicated_nvme_writable"] = os.access(storage_root, os.W_OK)
    if not all(checks.values()):
        raise RuntimeError(f"configuration closure failed: {checks}")
    return {"checks": checks, "mount": storage_mount}


def prepare(args: argparse.Namespace) -> None:
    prepare_started = time.monotonic()
    config_path = Path(args.config).resolve()
    gate_path = Path(args.gate).resolve()
    attempt = Path(args.attempt_root).resolve()
    config = read_json(config_path)
    config_validation = validate_config(config, attempt, gate_path)
    source_path = Path(__file__).resolve()
    test_path = source_path.with_name("test_protocol.py")
    prelaunch_gate_path = source_path.parent.parent / "t2_a0_r2_closed_loop_path_dependence_gate_0720.md"
    if not test_path.is_file() or not prelaunch_gate_path.is_file():
        raise RuntimeError("required source/test/prelaunch artifact missing")
    attempt.mkdir(parents=True, exist_ok=False)
    for directory in ("frozen/source", "prelaunch", "sanity", "formal", "postrun", "logs", "tmp", "pycache"):
        (attempt / directory).mkdir(parents=True, exist_ok=False)
    shutil.copy2(source_path, attempt / "frozen/source/experiment.py")
    shutil.copy2(test_path, attempt / "frozen/source/test_protocol.py")
    shutil.copy2(config_path, attempt / "frozen/config.json")
    shutil.copy2(gate_path, attempt / "frozen/authorizing_gate.md")
    shutil.copy2(prelaunch_gate_path, attempt / "frozen/prelaunch_gate.md")
    formal_workloads = make_workloads(config, sanity=False)
    sanity_workloads = make_workloads(config, sanity=True)
    write_json_exclusive(attempt / "frozen/formal_workloads.json", formal_workloads)
    write_json_exclusive(attempt / "frozen/sanity_workloads.json", sanity_workloads)
    frozen_hashes = source_tree_manifest(attempt / "frozen")
    statvfs = os.statvfs(attempt)
    manifest = {
        "schema": "t2-a0-r2-prelaunch-manifest-v1",
        "attempt_id": config["attempt_id"],
        "status": "PREPARED",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "created_epoch_seconds": time.time(),
        "attempt_root": str(attempt),
        "gate_sha256": file_digest(attempt / "frozen/authorizing_gate.md"),
        "config_sha256": file_digest(attempt / "frozen/config.json"),
        "formal_workload_sha256": file_digest(attempt / "frozen/formal_workloads.json"),
        "sanity_workload_sha256": file_digest(attempt / "frozen/sanity_workloads.json"),
        "source_tree": frozen_hashes,
        "source_tree_sha256": digest(frozen_hashes),
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": sys.version,
        "python_executable_sha256": file_digest(Path(sys.executable).resolve()),
        "filesystem_device": os.stat(attempt).st_dev,
        "mount": config_validation["mount"],
        "config_closure_checks": config_validation["checks"],
        "initial_free_bytes": statvfs.f_bavail * statvfs.f_frsize,
        "resources": config["resources"],
        "expected_formal_paired_cells": config["formal"]["expected_paired_cells"],
        "allowed_outcomes": config["allowed_outcomes"],
    }
    try:
        manifest["chat_git_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=source_path.parent, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        manifest["chat_git_commit"] = "UNAVAILABLE"
    write_json_exclusive(attempt / "prelaunch/manifest.json", manifest)
    validate_frozen(attempt)
    test_env = os.environ.copy()
    test_env["PYTHONDONTWRITEBYTECODE"] = "1"
    test_env["PYTHONPYCACHEPREFIX"] = str(attempt / "pycache")
    test_result = subprocess.run(
        [manifest["python_executable"], str(attempt / "frozen/source/test_protocol.py"), "-v"],
        cwd=attempt / "frozen/source",
        env=test_env,
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    test_record = {
        "command": [manifest["python_executable"], "frozen/source/test_protocol.py", "-v"],
        "exit_code": test_result.returncode,
        "stdout": test_result.stdout,
        "stderr": test_result.stderr,
        "stdout_sha256": hashlib.sha256(test_result.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(test_result.stderr.encode()).hexdigest(),
    }
    write_json_exclusive(attempt / "prelaunch/tests.json", test_record)
    if test_result.returncode != 0:
        write_json_exclusive(
            attempt / "prelaunch/FAILED.json",
            {"outcome": "FAIL-PROTOCOL-CLOSURE", "reason": "frozen protocol tests failed"},
        )
        raise RuntimeError("frozen protocol tests failed")
    write_json_exclusive(
        attempt / "prelaunch/validation.json",
        {
            "schema": "t2-a0-r2-prelaunch-validation-v1",
            "passed": True,
            "manifest_sha256": file_digest(attempt / "prelaunch/manifest.json"),
            "tests_sha256": file_digest(attempt / "prelaunch/tests.json"),
            "config_checks": config_validation["checks"],
            "prepare_and_test_wall_seconds": time.monotonic() - prepare_started,
        },
    )
    lock = {
        "schema": "t2-a0-r2-prelaunch-lock-v1",
        "manifest_sha256": file_digest(attempt / "prelaunch/manifest.json"),
        "validation_sha256": file_digest(attempt / "prelaunch/validation.json"),
        "tests_sha256": file_digest(attempt / "prelaunch/tests.json"),
        "source_tree_sha256": manifest["source_tree_sha256"],
        "config_sha256": manifest["config_sha256"],
        "gate_sha256": manifest["gate_sha256"],
    }
    write_json_exclusive(attempt / "prelaunch/PRELAUNCH_LOCK.json", lock)
    for path in list((attempt / "frozen").rglob("*")) + list((attempt / "prelaunch").glob("*.json")):
        if path.is_file():
            path.chmod(0o444)
    validate_prelaunch_lock(attempt)
    print(canonical_bytes({"prepared": str(attempt), "manifest": manifest}).decode())


def validate_frozen(attempt: Path) -> dict[str, Any]:
    manifest = read_json(attempt / "prelaunch/manifest.json")
    checks = {
        "gate": file_digest(attempt / "frozen/authorizing_gate.md") == manifest["gate_sha256"],
        "config": file_digest(attempt / "frozen/config.json") == manifest["config_sha256"],
        "formal_workload": file_digest(attempt / "frozen/formal_workloads.json")
        == manifest["formal_workload_sha256"],
        "sanity_workload": file_digest(attempt / "frozen/sanity_workloads.json")
        == manifest["sanity_workload_sha256"],
        "source_tree": digest(source_tree_manifest(attempt / "frozen")) == manifest["source_tree_sha256"],
        "python": file_digest(Path(manifest["python_executable"])) == manifest["python_executable_sha256"],
    }
    if not all(checks.values()):
        raise RuntimeError(f"frozen provenance closure failed: {checks}")
    return checks


def validate_prelaunch_lock(attempt: Path) -> dict[str, Any]:
    lock = read_json(attempt / "prelaunch/PRELAUNCH_LOCK.json")
    manifest = read_json(attempt / "prelaunch/manifest.json")
    validation = read_json(attempt / "prelaunch/validation.json")
    checks = {
        "manifest": file_digest(attempt / "prelaunch/manifest.json") == lock["manifest_sha256"],
        "validation": file_digest(attempt / "prelaunch/validation.json")
        == lock["validation_sha256"],
        "tests": file_digest(attempt / "prelaunch/tests.json") == lock["tests_sha256"],
        "validation_passed": validation["passed"] is True,
        "validation_manifest": validation["manifest_sha256"] == lock["manifest_sha256"],
        "source_tree": manifest["source_tree_sha256"] == lock["source_tree_sha256"],
        "config": manifest["config_sha256"] == lock["config_sha256"],
        "gate": manifest["gate_sha256"] == lock["gate_sha256"],
        "device": os.stat(attempt).st_dev == manifest["filesystem_device"],
        "mount": mount_info(attempt) == manifest["mount"],
    }
    if not all(checks.values()):
        raise RuntimeError(f"prelaunch lock closure failed: {checks}")
    return checks


def assert_frozen_entrypoint(attempt: Path) -> None:
    expected = attempt / "frozen/source/experiment.py"
    if Path(__file__).resolve() != expected.resolve():
        raise RuntimeError("run/validate must execute the frozen experiment.py entrypoint")
    manifest = read_json(attempt / "prelaunch/manifest.json")
    if file_digest(Path(__file__).resolve()) != manifest["source_tree"]["source/experiment.py"]:
        raise RuntimeError("executing source hash is not the frozen source hash")


def validate_sanity_lock(attempt: Path) -> dict[str, Any]:
    lock = read_json(attempt / "sanity/SANITY_LOCK.json")
    checks = {
        name: file_digest(attempt / f"sanity/{name}") == expected
        for name, expected in lock["files"].items()
    }
    checks["file_set"] = digest(lock["files"]) == lock["files_sha256"]
    checks["prelaunch_lock"] = file_digest(attempt / "prelaunch/PRELAUNCH_LOCK.json") == lock[
        "prelaunch_lock_sha256"
    ]
    checks["validation_passed"] = read_json(attempt / "sanity/validation.json")["passed"] is True
    if not all(checks.values()):
        raise RuntimeError(f"sanity lock closure failed: {checks}")
    return checks


def run_phase(args: argparse.Namespace) -> None:
    attempt = Path(args.attempt_root).resolve()
    if (attempt / "FAILED.json").exists():
        raise RuntimeError("failed attempt cannot be reused")
    assert_frozen_entrypoint(attempt)
    validate_frozen(attempt)
    validate_prelaunch_lock(attempt)
    config = read_json(attempt / "frozen/config.json")
    if attempt != Path(config["attempt_root"]).resolve():
        raise RuntimeError("attempt root differs from frozen config")
    sanity = args.phase == "sanity"
    if not sanity:
        validate_sanity_lock(attempt)
        sanity_validation = read_json(attempt / "sanity/validation.json")
        if sanity_validation.get("passed") is not True or not sanity_validation.get("negative_tests"):
            raise RuntimeError("formal blocked: sanity validation/negative tests not sealed")
        sanity_summary = read_json(attempt / "sanity/summary.json")
        if file_digest(attempt / "sanity/raw_steps.jsonl.gz") != sanity_summary["raw_sha256"]:
            raise RuntimeError("formal blocked: sanity raw hash mismatch")
        if file_digest(attempt / "sanity/pairs.jsonl") != sanity_summary["pairs_sha256"]:
            raise RuntimeError("formal blocked: sanity pairs hash mismatch")
    section = config["sanity" if sanity else "formal"]
    workloads = read_json(attempt / f"frozen/{'sanity' if sanity else 'formal'}_workloads.json")
    triplets = [section["capacity_triplet"]] if sanity else config["capacity_triplets"]
    expected_cells = len(POLICIES) * len(triplets) * len(workloads["instances"]) * len(MODELS)
    output_dir = attempt / args.phase
    raw_path = output_dir / "raw_steps.jsonl.gz"
    pairs_path = output_dir / "pairs.jsonl"
    prefix_path = output_dir / "prefix_states.jsonl.gz"
    if raw_path.exists() or pairs_path.exists() or prefix_path.exists():
        raise FileExistsError("phase output already exists")
    write_json_exclusive(
        output_dir / "RUNNING.json",
        {"phase": args.phase, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
    )
    started = time.monotonic()
    all_pairs = []
    prefix_cache: dict[tuple[str, str], tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    with prefix_path.open("xb") as prefix_file, gzip.GzipFile(
        filename="prefix_states.jsonl", mode="wb", fileobj=prefix_file, mtime=0
    ) as prefix_handle:
        for policy in POLICIES:
            for instance in workloads["instances"]:
                state, prefix_logs = run_prefix(instance, policy, config)
                prefix_cache[(policy, instance["instance_id"])] = (state, prefix_logs)
                append_jsonl(
                    prefix_handle,
                    {
                        "policy": policy,
                        "instance_id": instance["instance_id"],
                        "fork_state": state,
                        "fork_bytes_sha256": hashlib.sha256(canonical_bytes(state)).hexdigest(),
                        "prefix_logs": prefix_logs,
                    },
                )
    with raw_path.open("xb") as raw_file, gzip.GzipFile(
        filename="raw_steps.jsonl", mode="wb", fileobj=raw_file, mtime=0
    ) as raw_handle, pairs_path.open("xb") as pairs_handle:
        for policy in POLICIES:
            for triplet in triplets:
                for instance in workloads["instances"]:
                    prefix_state, _ = prefix_cache[(policy, instance["instance_id"])]
                    for model in MODELS:
                        pair, logs_a, logs_b = run_one_cell(
                            prefix_state,
                            instance,
                            policy,
                            triplet,
                            model,
                            section["evaluation_steps"],
                            check_order=sanity,
                        )
                        all_pairs.append(pair)
                        append_jsonl(pairs_handle, pair)
                        for row in logs_a + logs_b:
                            append_jsonl(raw_handle, row)
                        check_resources(started, attempt, config)
    if len(all_pairs) != expected_cells:
        raise RuntimeError(f"cell count {len(all_pairs)} != {expected_cells}")
    run_usage = check_resources(started, attempt, config)
    prior_wall = read_json(attempt / "prelaunch/validation.json")["prepare_and_test_wall_seconds"]
    if not sanity:
        prior_wall += read_json(attempt / "sanity/summary.json")["resources"]["wall_seconds"]
        prior_wall += read_json(attempt / "sanity/validation.json")["resources"]["wall_seconds"]
    cumulative_wall = prior_wall + run_usage["wall_seconds"]
    if cumulative_wall > config["resources"]["max_wall_seconds"]:
        raise RuntimeError("cumulative attempt wall limit exceeded")
    summary = {
        "schema": "t2-a0-r2-phase-summary-v1",
        "phase": args.phase,
        "paired_cells": len(all_pairs),
        "raw_rows": sum(
            2 * (len(instance["low"]) + len(instance["evaluation"]))
            for _policy in POLICIES
            for _triplet in triplets
            for instance in workloads["instances"]
            for _model in MODELS
        ),
        "resources": run_usage,
        "attempt_cumulative_wall_seconds": cumulative_wall,
        "raw_sha256": file_digest(raw_path),
        "pairs_sha256": file_digest(pairs_path),
        "prefix_states_sha256": file_digest(prefix_path),
    }
    if not sanity:
        summary["sanity_validation_sha256"] = file_digest(attempt / "sanity/validation.json")
        summary["sanity_summary_sha256"] = file_digest(attempt / "sanity/summary.json")
    if not sanity:
        summary["classifier"] = classify(all_pairs, config)
    write_json_exclusive(output_dir / "summary.json", summary)
    check_resources(started, attempt, config)
    print(canonical_bytes(summary).decode())


def iter_jsonl_gz(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rb") as handle:
        for line in handle:
            yield json.loads(line)


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("rb") as handle:
        for line in handle:
            yield json.loads(line)


def validate_phase(args: argparse.Namespace) -> None:
    attempt = Path(args.attempt_root).resolve()
    if (attempt / "FAILED.json").exists():
        raise RuntimeError("failed attempt cannot be validated/reused")
    assert_frozen_entrypoint(attempt)
    validation_started = time.monotonic()
    frozen_checks = validate_frozen(attempt)
    lock_checks = validate_prelaunch_lock(attempt)
    config = read_json(attempt / "frozen/config.json")
    if attempt != Path(config["attempt_root"]).resolve():
        raise RuntimeError("attempt root differs from frozen config")
    sanity = args.phase == "sanity"
    section = config["sanity" if sanity else "formal"]
    workload_document = read_json(attempt / f"frozen/{'sanity' if sanity else 'formal'}_workloads.json")
    instances = {item["instance_id"]: item for item in workload_document["instances"]}
    triplets = [section["capacity_triplet"]] if sanity else config["capacity_triplets"]
    expected_cells = len(POLICIES) * len(triplets) * len(section["instances"]) * len(MODELS)
    expected_rows = expected_cells * 2 * (section["low_steps"] + section["evaluation_steps"])
    phase_dir = attempt / args.phase
    summary = read_json(phase_dir / "summary.json")
    pairs = list(iter_jsonl(phase_dir / "pairs.jsonl"))
    expected_universe = {
        (policy, tuple(triplet), instance_id, model)
        for policy in POLICIES
        for triplet in triplets
        for instance_id in section["instances"]
        for model in MODELS
    }
    actual_universe = {
        (pair["policy"], tuple(pair["triplet"]), pair["instance_id"], pair["model"])
        for pair in pairs
    }

    prefix_records = list(iter_jsonl_gz(phase_dir / "prefix_states.jsonl.gz"))
    expected_prefix_count = len(POLICIES) * len(section["instances"])
    prefix_map: dict[tuple[str, str], dict[str, Any]] = {}
    prefix_replay_ok = len(prefix_records) == expected_prefix_count
    for record in prefix_records:
        key = (record["policy"], record["instance_id"])
        if key in prefix_map or record["instance_id"] not in instances:
            prefix_replay_ok = False
            continue
        replay_state, replay_logs = run_prefix(instances[record["instance_id"]], record["policy"], config)
        expected_record = {
            "policy": record["policy"],
            "instance_id": record["instance_id"],
            "fork_state": replay_state,
            "fork_bytes_sha256": hashlib.sha256(canonical_bytes(replay_state)).hexdigest(),
            "prefix_logs": replay_logs,
        }
        if canonical_bytes(record) != canonical_bytes(expected_record):
            prefix_replay_ok = False
        prefix_map[key] = record

    replay_pairs = []
    replay_ok = True
    raw_count = 0
    first_actual_row = None
    first_expected_row = None
    closed_loop_edge_cells = 0
    raw_iter = iter(iter_jsonl_gz(phase_dir / "raw_steps.jsonl.gz"))
    rows_per_branch = section["low_steps"] + section["evaluation_steps"]
    for actual_pair in pairs:
        key = (
            actual_pair["policy"],
            tuple(actual_pair["triplet"]),
            actual_pair["instance_id"],
            actual_pair["model"],
        )
        if key not in expected_universe:
            replay_ok = False
            continue
        prefix_record = prefix_map[(actual_pair["policy"], actual_pair["instance_id"])]
        expected_pair, expected_a, expected_b = run_one_cell(
            prefix_record["fork_state"],
            instances[actual_pair["instance_id"]],
            actual_pair["policy"],
            actual_pair["triplet"],
            actual_pair["model"],
            section["evaluation_steps"],
            check_order=False,
        )
        expected_rows_for_cell = expected_a + expected_b
        if actual_pair["model"] == "closed_loop":
            by_branch_edge = {
                branch: any(
                    row["phase"] == "evaluation"
                    and row["query"]["dependency_action_id"] is not None
                    and row["query"]["source_version_id"] in row["retrieved_memory_ids"]
                    and row["query"]["source_version_id"] in row["memory_reads"]
                    for row in expected_rows_for_cell
                    if row["branch"] == branch
                )
                for branch in ("A", "B")
            }
            if all(by_branch_edge.values()):
                closed_loop_edge_cells += 1
        actual_rows_for_cell = []
        for _ in range(2 * rows_per_branch):
            try:
                actual_rows_for_cell.append(next(raw_iter))
                raw_count += 1
            except StopIteration:
                replay_ok = False
                break
        if len(actual_rows_for_cell) != len(expected_rows_for_cell):
            replay_ok = False
        else:
            for actual_row, expected_row in zip(actual_rows_for_cell, expected_rows_for_cell, strict=True):
                if first_actual_row is None:
                    first_actual_row = copy.deepcopy(actual_row)
                    first_expected_row = copy.deepcopy(expected_row)
                if canonical_bytes(actual_row) != canonical_bytes(expected_row):
                    replay_ok = False
                    break
        if canonical_bytes(actual_pair) != canonical_bytes(expected_pair):
            replay_ok = False
        replay_pairs.append(expected_pair)
        check_resources(validation_started, attempt, config)
    try:
        next(raw_iter)
        replay_ok = False
    except StopIteration:
        pass

    replay_classifier = None if sanity else classify(replay_pairs, config)
    checks: dict[str, Any] = {
        "frozen": all(frozen_checks.values()),
        "prelaunch_lock": all(lock_checks.values()),
        "pair_count": len(pairs) == expected_cells == summary["paired_cells"],
        "raw_count": raw_count == expected_rows == summary["raw_rows"],
        "raw_hash": file_digest(phase_dir / "raw_steps.jsonl.gz") == summary["raw_sha256"],
        "pairs_hash": file_digest(phase_dir / "pairs.jsonl") == summary["pairs_sha256"],
        "prefix_hash": file_digest(phase_dir / "prefix_states.jsonl.gz")
        == summary["prefix_states_sha256"],
        "prefix_replay": prefix_replay_ok,
        "unique_cells": len({row["cell_id"] for row in pairs}) == expected_cells,
        "exact_universe": actual_universe == expected_universe,
        "streaming_transition_replay": replay_ok,
        "runner_pair_recomputed": replay_ok,
        "classifier_recomputed": sanity
        or canonical_bytes(replay_classifier) == canonical_bytes(summary["classifier"]),
        "closed_loop_action_write_future_query_edge": closed_loop_edge_cells
        == len(POLICIES) * len(triplets) * len(section["instances"]),
    }
    model_pairs: dict[str, list[dict[str, Any]]] = {model: [] for model in MODELS}
    for pair in replay_pairs:
        model_pairs[pair["model"]].append(pair)
    checks["open_loop_query_control"] = all(
        pair["metrics"]["Q"] == 0 for pair in model_pairs["open_loop_query"]
    )
    checks["write_disabled_control"] = all(
        pair["metrics"]["M"] == 0 for pair in model_pairs["write_disabled"]
    )
    checks["transparent_control"] = all(
        pair["metrics"]["D"] == 0 for pair in model_pairs["transparent_retrieval"]
    )
    checks["resource_bounds"] = (
        summary["resources"]["wall_seconds"] <= config["resources"]["max_wall_seconds"]
        and summary["resources"]["peak_rss_bytes"] <= config["resources"]["max_rss_bytes"]
        and summary["resources"]["allocated_bytes"] <= config["resources"]["max_attempt_bytes"]
    )
    negative_tests = {}
    if sanity:
        assert first_actual_row is not None and first_expected_row is not None
        sample = copy.deepcopy(first_actual_row)
        sample["fork_hash"] = "0" * 64
        negative_tests["fork_hash_tamper_rejected"] = canonical_bytes(sample) != canonical_bytes(first_expected_row)
        sample = copy.deepcopy(first_actual_row)
        sample["event_id"] = "0" * 64
        negative_tests["event_id_tamper_rejected"] = canonical_bytes(sample) != canonical_bytes(first_expected_row)
        sample_pair = copy.deepcopy(pairs[0])
        sample_pair["metrics"]["Q"] = 999
        negative_tests["pair_metric_tamper_rejected"] = canonical_bytes(sample_pair) != canonical_bytes(replay_pairs[0])
        sample_pair = copy.deepcopy(next(pair for pair in pairs if pair["model"] == "closed_loop"))
        expected_pair = next(pair for pair in replay_pairs if pair["cell_id"] == sample_pair["cell_id"])
        sample_pair["witness"] = {"forged": True}
        negative_tests["witness_tamper_rejected"] = canonical_bytes(sample_pair) != canonical_bytes(expected_pair)
        manifest_copy = copy.deepcopy(read_json(attempt / "prelaunch/manifest.json"))
        manifest_copy["source_tree_sha256"] = "0" * 64
        negative_tests["source_hash_tamper_rejected"] = manifest_copy["source_tree_sha256"] != read_json(
            attempt / "prelaunch/PRELAUNCH_LOCK.json"
        )["source_tree_sha256"]
        negative_tests["raw_hash_tamper_rejected"] = ("0" * 64) != summary["raw_sha256"]
        checks["negative_tests"] = all(negative_tests.values())
        checks["sanity_witness_pipeline"] = any(
            pair["witness"] is not None for pair in model_pairs["closed_loop"]
        )
    validation_usage = check_resources(validation_started, attempt, config)
    attempt_cumulative_wall = summary["attempt_cumulative_wall_seconds"] + validation_usage["wall_seconds"]
    checks["validation_resource_bounds"] = (
        attempt_cumulative_wall <= config["resources"]["max_wall_seconds"]
    )
    passed = all(bool(value) for value in checks.values())
    validation = {
        "schema": "t2-a0-r2-validation-v1",
        "phase": args.phase,
        "passed": passed,
        "checks": checks,
        "negative_tests": negative_tests,
        "resources": validation_usage,
        "attempt_cumulative_wall_seconds": attempt_cumulative_wall,
        "validated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if not passed:
        validation["outcome"] = "FAIL-PROTOCOL-CLOSURE"
    write_json_exclusive(phase_dir / "validation.json", validation)
    if not passed:
        raise RuntimeError("protocol validation failed")
    if sanity:
        sanity_files = {
            name: file_digest(attempt / f"sanity/{name}")
            for name in (
                "summary.json",
                "validation.json",
                "raw_steps.jsonl.gz",
                "pairs.jsonl",
                "prefix_states.jsonl.gz",
                "RUNNING.json",
            )
        }
        write_json_exclusive(
            attempt / "sanity/SANITY_LOCK.json",
            {
                "schema": "t2-a0-r2-sanity-lock-v1",
                "files": sanity_files,
                "files_sha256": digest(sanity_files),
                "prelaunch_lock_sha256": file_digest(attempt / "prelaunch/PRELAUNCH_LOCK.json"),
            },
        )
        validate_sanity_lock(attempt)
    else:
        write_json_exclusive(
            attempt / "formal/COMPLETE.json",
            {"outcome": replay_classifier["outcome"], "validation_sha256": file_digest(phase_dir / "validation.json")},
        )
        postrun_files = {}
        for directory in ("frozen", "prelaunch", "sanity", "formal"):
            for path in sorted((attempt / directory).rglob("*")):
                if path.is_file():
                    postrun_files[str(path.relative_to(attempt))] = file_digest(path)
        postrun = {
            "schema": "t2-a0-r2-postrun-manifest-v1",
            "attempt_id": config["attempt_id"],
            "prelaunch_manifest_sha256": file_digest(attempt / "prelaunch/manifest.json"),
            "files": postrun_files,
            "files_sha256": digest(postrun_files),
            "outcome": replay_classifier["outcome"],
            "resources": summary["resources"],
            "validation_resources": validation_usage,
            "attempt_cumulative_wall_seconds": attempt_cumulative_wall,
            "completed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        write_json_exclusive(attempt / "postrun/manifest.json", postrun)
    print(canonical_bytes(validation).decode())


def inspect(args: argparse.Namespace) -> None:
    attempt = Path(args.attempt_root).resolve()
    assert_frozen_entrypoint(attempt)
    validate_frozen(attempt)
    validate_prelaunch_lock(attempt)
    summary = read_json(attempt / "formal/summary.json")
    validation = read_json(attempt / "formal/validation.json")
    postrun = read_json(attempt / "postrun/manifest.json")
    complete = read_json(attempt / "formal/COMPLETE.json")
    file_checks = {
        relative: file_digest(attempt / relative) == expected
        for relative, expected in postrun["files"].items()
    }
    if not all(file_checks.values()) or digest(postrun["files"]) != postrun["files_sha256"]:
        raise RuntimeError("postrun file seal mismatch")
    if file_digest(attempt / "prelaunch/manifest.json") != postrun["prelaunch_manifest_sha256"]:
        raise RuntimeError("postrun prelaunch binding mismatch")
    if not validation["passed"]:
        raise RuntimeError("formal validation did not pass")
    outcomes = {
        postrun["outcome"],
        summary["classifier"]["outcome"],
        complete["outcome"],
    }
    if len(outcomes) != 1:
        raise RuntimeError(f"outcome seal mismatch: {outcomes}")
    compact = {
        "outcome": postrun["outcome"],
        "validation_passed": validation["passed"],
        "resources": summary["resources"],
        "cells": summary["classifier"]["cells"],
        "supported_triplets_by_policy": summary["classifier"]["supported_triplets_by_policy"],
        "common_supported_triplets": summary["classifier"]["common_supported_triplets"],
        "postrun_manifest_sha256": file_digest(attempt / "postrun/manifest.json"),
        "raw_sha256": summary["raw_sha256"],
        "pairs_sha256": summary["pairs_sha256"],
    }
    print(json.dumps(compact, indent=2, sort_keys=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--config", required=True)
    prep.add_argument("--gate", required=True)
    prep.add_argument("--attempt-root", required=True)
    run = sub.add_parser("run")
    run.add_argument("--attempt-root", required=True)
    run.add_argument("--phase", choices=("sanity", "formal"), required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--attempt-root", required=True)
    validate.add_argument("--phase", choices=("sanity", "formal"), required=True)
    view = sub.add_parser("inspect")
    view.add_argument("--attempt-root", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        if args.command == "prepare":
            prepare(args)
        elif args.command == "run":
            run_phase(args)
        elif args.command == "validate":
            validate_phase(args)
        elif args.command == "inspect":
            inspect(args)
        else:
            raise AssertionError(args.command)
    except Exception as exc:
        root_value = getattr(args, "attempt_root", None)
        if root_value:
            attempt = Path(root_value).resolve()
            active_or_partial = bool(
                (attempt / "prelaunch/manifest.json").exists()
                and not (attempt / "prelaunch/PRELAUNCH_LOCK.json").exists()
                or (attempt / "sanity/RUNNING.json").exists()
                and not (attempt / "sanity/SANITY_LOCK.json").exists()
                or (attempt / "formal/RUNNING.json").exists()
                and not (attempt / "postrun/manifest.json").exists()
            )
            if attempt.exists() and active_or_partial:
                failure = attempt / "FAILED.json"
                if not failure.exists():
                    try:
                        write_json_exclusive(
                            failure,
                            {
                                "outcome": "FAIL-PROTOCOL-CLOSURE",
                                "command": args.command,
                                "reason": f"{type(exc).__name__}: {exc}",
                                "failed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            },
                        )
                    except Exception:
                        pass
        raise


if __name__ == "__main__":
    main()
