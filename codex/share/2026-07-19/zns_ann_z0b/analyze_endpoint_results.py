#!/usr/bin/env python3
"""Deterministic, preregistered post-processing for all 6 x 48 Z0B results.

The analyzer consumes sequence-only native outputs.  It does not inspect or
emit timestamps, choose a new effect threshold, or turn the reported facts
into a discretionary fourth verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Sequence

import numpy as np

from compare_native_results import projection


PAGE = 4096
FRACTION_RE = re.compile(r"^(0|[1-9][0-9]*)/([1-9][0-9]*)$")
PLACEMENTS = (
    ("canonical", "canonical", 0, "Canonical"),
    ("role", "role", 0, "RoleSeparated"),
    ("random-2026071901", "random", 2026071901, "RandomPacking-2026071901"),
    ("random-2026071902", "random", 2026071902, "RandomPacking-2026071902"),
    ("random-2026071903", "random", 2026071903, "RandomPacking-2026071903"),
    ("oracle", "oracle", 0, "OfflineHotColdOracle"),
)
CLEANERS = (("greedy", "greedy", "GreedyValidFraction"),
            ("oracle", "oracle", "OracleMinCopy"))
METRICS = ("HostWA_cycle", "relocated_pages_cycle", "victim_valid_fraction")
TRANSPARENT = {row[3] for row in PLACEMENTS if row[3] != "OfflineHotColdOracle"}


def fail(message: str) -> None:
    raise ValueError(message)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def parse_fraction(value: object, field: str) -> Fraction:
    if not isinstance(value, str):
        fail(f"{field} must be an exact n/d string")
    match = FRACTION_RE.fullmatch(value)
    if not match:
        fail(f"invalid exact fraction at {field}: {value!r}")
    return Fraction(int(match.group(1)), int(match.group(2)))


def integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        fail(f"nonnegative integer required at {field}")
    return value


def ratio(value: Fraction | None) -> str | None:
    return None if value is None else f"{value.numerator}/{value.denominator}"


def sign(value: Fraction) -> int:
    return (value > 0) - (value < 0)


def exact_median(values: Sequence[Fraction]) -> Fraction | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def exact_w1(left: Sequence[int], right: Sequence[int]) -> Fraction | None:
    """Exact empirical 1D W1 through quantile-interval integration."""
    if not left or not right:
        return None
    a, b = sorted(left), sorted(right)
    i = j = 0
    q = Fraction(0)
    total = Fraction(0)
    while i < len(a) and j < len(b):
        boundary = min(Fraction(i + 1, len(a)), Fraction(j + 1, len(b)))
        total += abs(a[i] - b[j]) * (boundary - q)
        q = boundary
        if q == Fraction(i + 1, len(a)):
            i += 1
        if q == Fraction(j + 1, len(b)):
            j += 1
    if q != 1:
        fail("internal W1 quantile closure failure")
    return total


def normalized_w1(left: Sequence[int], right: Sequence[int]) -> Fraction | None:
    distance = exact_w1(left, right)
    if distance is None:
        return None
    pooled_mean = Fraction(sum(left) + sum(right), len(left) + len(right))
    return Fraction(0) if pooled_mean == 0 else distance / pooled_mean


def exact_theil_sen(x: Sequence[int], y: Sequence[Fraction]) -> tuple[Fraction, Fraction]:
    if len(x) != len(y) or len(x) < 2 or any(x[index] >= x[index + 1] for index in range(len(x) - 1)):
        fail("Theil-Sen requires >=2 strictly increasing integer coordinates")
    slopes = [(y[j] - y[i]) / (x[j] - x[i])
              for i in range(len(x)) for j in range(i + 1, len(x))]
    slope = exact_median(slopes)
    assert slope is not None
    intercept = exact_median([value - slope * coordinate for coordinate, value in zip(x, y)])
    assert intercept is not None
    return slope, intercept


def ceil_cuberoot(value: int) -> int:
    result = max(1, round(value ** (1 / 3)))
    while result**3 < value:
        result += 1
    while result > 1 and (result - 1)**3 >= value:
        result -= 1
    return result


def derived_seed(master: int, config_id: str, trace_id: str, metric: str) -> tuple[int, str]:
    # Literal UTF-8 concatenation implements the preregistered A || B || C || D.
    preimage = f"{master}{config_id}{trace_id}{metric}"
    return int.from_bytes(hashlib.sha256(preimage.encode()).digest()[:8], "big"), preimage


def bootstrap_ci(x: Sequence[int], y: Sequence[Fraction], slope: Fraction, intercept: Fraction,
                 seed: int, resamples: int) -> tuple[float, float, int, str]:
    """All-pair Theil-Sen for every circular moving-block residual resample."""
    n = len(x)
    block_length = min(n, max(2, ceil_cuberoot(n)))
    residual = [value - (intercept + slope * coordinate) for coordinate, value in zip(x, y)]
    mean = sum(residual, Fraction(0)) / n
    centered = [value - mean for value in residual]
    if all(value == 0 for value in centered):
        exact = float(slope)
        return exact, exact, block_length, "exact-zero-residual-fast-path"

    x_values = np.asarray(x, dtype=np.float64)
    fitted = float(intercept) + float(slope) * x_values
    residual_values = np.asarray([float(value) for value in centered], dtype=np.float64)
    pair_i, pair_j = np.triu_indices(n, 1)
    denominators = x_values[pair_j] - x_values[pair_i]
    pair_count = pair_i.size
    # Bound the largest slope matrix to about 128 MiB.
    batch = max(1, min(4096, (128 * 1024 * 1024) // max(8 * (pair_count + 4 * n), 1)))
    block_count = (n + block_length - 1) // block_length
    offsets = np.arange(block_length, dtype=np.int64)
    rng = np.random.Generator(np.random.PCG64(seed))
    estimates = np.empty(resamples, dtype=np.float64)
    cursor = 0
    while cursor < resamples:
        count = min(batch, resamples - cursor)
        starts = rng.integers(0, n, size=(count, block_count), dtype=np.int64)
        indices = ((starts[:, :, None] + offsets) % n).reshape(count, -1)[:, :n]
        sample = fitted[None, :] + residual_values[indices]
        slopes = (sample[:, pair_j] - sample[:, pair_i]) / denominators
        estimates[cursor:cursor + count] = np.median(slopes, axis=1)
        cursor += count
    low, high = np.quantile(estimates, [0.05, 0.95], method="linear")
    return float(low), float(high), block_length, "float64-all-pair-type7-percentile"


def trend_result(values: Sequence[Fraction], cycle_indices: Sequence[int], config_id: str,
                 trace_id: str, metric: str, bootstrap: dict[str, object]) -> dict[str, object]:
    if len(values) != len(cycle_indices) or len(values) < 2:
        fail("eligible trend sample is malformed")
    slope, intercept = exact_theil_sen(cycle_indices, values)
    master = int(bootstrap["master_seed"])
    resamples = int(bootstrap["resamples"])
    seed, preimage = derived_seed(master, config_id, trace_id, metric)
    low, high, block, numeric = bootstrap_ci(cycle_indices, values, slope, intercept, seed, resamples)
    label = "NO-DETECTED-SEQUENCE-TREND" if low <= 0.0 <= high else "NONSTATIONARY"
    return {
        "metric": metric, "sample_count": len(values),
        "cycle_index_first": cycle_indices[0], "cycle_index_last": cycle_indices[-1],
        "theil_sen_slope": ratio(slope), "theil_sen_intercept": ratio(intercept),
        "bootstrap_kind": "circular-moving-block-residual",
        "residual_center": "arithmetic-mean", "block_length": block,
        "resamples": resamples, "prng": "NumPy-PCG64", "derived_seed": seed,
        "derived_seed_encoding": "uint64-big-endian(first8(SHA256(utf8(decimal_master||config_id||trace_id||metric))))",
        "derived_seed_preimage_sha256": hashlib.sha256(preimage.encode()).hexdigest(),
        "ci90": {"low": format(low, ".17g"), "high": format(high, ".17g"),
                 "percentile_method": "type-7-linear"},
        "bootstrap_numeric_method": numeric, "trend_label": label,
    }


@dataclass(frozen=True)
class RunRecord:
    trace_id: str
    system: str
    realization: int
    capacity_blocks: int
    host_spares: int
    placement: str
    cleaner: str
    config_id: str
    host_wa: Fraction
    reset_count: int
    relocated_pages: tuple[int, ...]
    victim_fractions: tuple[Fraction, ...]
    cycle_host_wa: tuple[Fraction, ...]
    cycle_indices: tuple[int, ...]

    @property
    def eligible(self) -> bool:
        return self.reset_count >= 8

    @property
    def median_victim(self) -> Fraction | None:
        return exact_median(self.victim_fractions)


def validate_result(payload: dict[str, object], expected: dict[str, object], source: str) -> RunRecord:
    cycles = payload["cycles"]
    if not isinstance(cycles, list):
        fail(f"cycles not a list: {source}")
    reset_count = integer(payload["reset_count"], f"{source}.reset_count")
    cycle_count = integer(payload["complete_cycle_count"], f"{source}.complete_cycle_count")
    if reset_count != cycle_count or len(cycles) != cycle_count:
        fail(f"reset/complete-cycle/list closure mismatch: {source}")
    if payload.get("placement") != expected["native_placement"] or payload.get("random_seed") != expected["seed"] or payload.get("cleaner") != expected["native_cleaner"]:
        fail(f"native configuration identity mismatch: {source}")
    byte_accounts = payload.get("bytes")
    if not isinstance(byte_accounts, dict):
        fail(f"byte accounts absent: {source}")
    required_accounts = (
        "application_returned_bytes", "normalized_fragment_bytes", "allocated_append_bytes",
        "replacement_rmw_read_bytes", "new_page_zero_fill_bytes", "relocation_allocated_bytes",
    )
    accounts = {name: integer(byte_accounts.get(name), f"{source}.{name}") for name in required_accounts}
    allocated = integer(byte_accounts.get("allocated_append_bytes"), f"{source}.allocated_append_bytes")
    relocated = integer(byte_accounts.get("relocation_allocated_bytes"), f"{source}.relocation_allocated_bytes")
    if (not allocated or allocated % PAGE or relocated % PAGE or
            accounts["application_returned_bytes"] != accounts["normalized_fragment_bytes"] or
            allocated - accounts["normalized_fragment_bytes"] !=
            accounts["replacement_rmw_read_bytes"] + accounts["new_page_zero_fill_bytes"]):
        fail(f"overall allocated/relocated page account mismatch: {source}")
    host_wa = parse_fraction(payload["host_wa_fraction"], f"{source}.host_wa_fraction")
    if host_wa != Fraction(allocated + relocated, allocated):
        fail(f"overall HostWA fraction/byte mismatch: {source}")
    relocated_pages = []
    victim_fractions = []
    cycle_host_wa = []
    cycle_indices = []
    cycle_allocated = cycle_relocated = cycle_application = 0
    for ordinal, row in enumerate(cycles, 1):
        if not isinstance(row, dict):
            fail(f"cycle row malformed: {source}:{ordinal}")
        index = integer(row.get("cycle_index"), f"{source}.cycle_index")
        if index != ordinal:
            fail(f"cycle indices are not strict 1..C: {source}")
        new_blocks = integer(row.get("allocated_new_blocks"), f"{source}.allocated_new_blocks")
        new_bytes = integer(row.get("allocated_new_append_bytes"), f"{source}.allocated_new_append_bytes")
        moved = integer(row.get("relocated_pages"), f"{source}.relocated_pages")
        moved_bytes = integer(row.get("relocation_allocated_bytes"), f"{source}.relocation_allocated_bytes")
        application_bytes = integer(row.get("application_returned_bytes"), f"{source}.application_returned_bytes")
        if not new_blocks or new_bytes != new_blocks * PAGE or moved_bytes != moved * PAGE:
            fail(f"cycle byte/page account mismatch: {source}:{ordinal}")
        cycle_wa = parse_fraction(row.get("host_wa_fraction"), f"{source}.cycle.host_wa_fraction")
        victim = parse_fraction(row.get("victim_valid_fraction"), f"{source}.victim_valid_fraction")
        if cycle_wa != Fraction(new_blocks + moved, new_blocks) or victim != Fraction(moved, int(expected["capacity_blocks"])):
            fail(f"cycle HostWA/victim fraction mismatch: {source}:{ordinal}")
        role_pages = row.get("victim_role_pages")
        if (not isinstance(role_pages, dict) or
                sum(integer(value, f"{source}.victim_role_pages") for value in role_pages.values()) != moved):
            fail(f"victim role-page closure mismatch: {source}:{ordinal}")
        for boundary_name in ("start", "last_append_before_gc", "gc_trigger"):
            boundary = row.get(boundary_name)
            if (not isinstance(boundary, dict) or
                    set(boundary) != {"event_ordinal", "global_seq", "page_index_within_request"} or
                    any(isinstance(boundary[name], bool) or not isinstance(boundary[name], int)
                        for name in boundary)):
                fail(f"sequence-only cycle boundary malformed: {source}:{ordinal}:{boundary_name}")
        relocated_pages.append(moved)
        victim_fractions.append(victim)
        cycle_host_wa.append(cycle_wa)
        cycle_indices.append(index)
        cycle_allocated += new_bytes
        cycle_relocated += moved_bytes
        cycle_application += application_bytes
    tail = payload.get("tail")
    if not isinstance(tail, dict) or tail.get("complete_cycle") is not False:
        fail(f"tail closure absent: {source}")
    tail_allocated = integer(tail.get("allocated_append_bytes"), f"{source}.tail.allocated_append_bytes")
    tail_blocks = integer(tail.get("allocated_new_blocks"), f"{source}.tail.allocated_new_blocks")
    tail_application = integer(tail.get("application_returned_bytes"), f"{source}.tail.application_returned_bytes")
    if (tail_allocated != tail_blocks * PAGE or cycle_allocated + tail_allocated != allocated or
            cycle_relocated != relocated or
            cycle_application + tail_application != accounts["application_returned_bytes"]):
        fail(f"cycle/tail versus overall byte closure mismatch: {source}")
    initial_image = payload.get("initial_image")
    if not isinstance(initial_image, dict):
        fail(f"initial image account absent: {source}")
    initial_pages = integer(initial_image.get("page_count"), f"{source}.initial_image.page_count")
    initial_allocated = integer(initial_image.get("allocated_bytes"), f"{source}.initial_image.allocated_bytes")
    initial_logical = integer(initial_image.get("logical_bytes"), f"{source}.initial_image.logical_bytes")
    if initial_allocated != initial_pages * PAGE or initial_logical > initial_allocated:
        fail(f"initial image byte/page closure mismatch: {source}")
    victim_sequence = payload.get("victim_sequence")
    if not isinstance(victim_sequence, list) or len(victim_sequence) != reset_count:
        fail(f"victim sequence count mismatch: {source}")
    return RunRecord(
        str(expected["trace_id"]), str(expected["system"]), int(expected["realization"]),
        int(expected["capacity_blocks"]), int(expected["host_spares"]),
        str(expected["placement"]), str(expected["cleaner"]), str(expected["config_id"]),
        host_wa, reset_count, tuple(relocated_pages), tuple(victim_fractions),
        tuple(cycle_host_wa), tuple(cycle_indices),
    )


def load_records(campaign: Path, prereg: dict[str, object]) -> tuple[list[RunRecord], dict[str, object]]:
    schedule_path = campaign / "schedule.json"
    schedule = json.loads(schedule_path.read_text())
    if schedule.get("schema") != "zns-ann-z0b-endpoint-schedule-v1":
        fail("campaign schedule schema mismatch")
    rows = schedule.get("runs")
    if not isinstance(rows, list) or len(rows) != 6:
        fail("campaign schedule must contain exactly six traces")
    seen = set()
    systems: dict[str, set[int]] = {"DGAI": set(), "OdinANN": set()}
    records = []
    hashes = {}
    for trace in rows:
        if not isinstance(trace, dict):
            fail("schedule trace row malformed")
        trace_id = str(trace.get("label"))
        system = str(trace.get("system"))
        realization = integer(trace.get("realization"), f"schedule.{trace_id}.realization")
        if trace_id in seen or system not in systems or realization not in (1, 2, 3):
            fail("schedule trace identity mismatch")
        seen.add(trace_id)
        systems[system].add(realization)
        result = campaign / "results" / trace_id
        final = json.loads((result / "final_status.json").read_text())
        closure = json.loads((result / "closure.json").read_text())
        matrix = json.loads((result / "matrix_crosscheck.json").read_text())
        closure_checks = closure.get("checks")
        if (final.get("status") != "pass" or int(final.get("configuration_count", -1)) != 48 or
                closure.get("status") != "pass" or not isinstance(closure_checks, dict) or
                not closure_checks or not all(value is True for value in closure_checks.values()) or
                matrix.get("status") != "pass" or int(matrix.get("configuration_count", -1)) != 48 or
                matrix.get("exact_replay_reference_match") is not True):
            fail(f"trace closure/final/matrix status failure: {trace_id}")
        if closure.get("temporal_fields_consumed") is not False or matrix.get("temporal_fields_used") is not False:
            fail(f"temporal field consumption detected: {trace_id}")
        expected_names = {f"z{blocks}-h{spares}-{pid}-{cleaner_id}.json"
                          for blocks in (65536, 262144) for spares in (2, 8)
                          for pid, _native, _seed, _placement in PLACEMENTS
                          for cleaner_id, _native_cleaner, _cleaner in CLEANERS}
        for directory in ("replay", "reference", "comparison"):
            actual_names = {path.name for path in (result / directory).glob("*.json")}
            if actual_names != expected_names:
                fail(f"strict 48-file set mismatch: {trace_id}/{directory}")
        for blocks in (65536, 262144):
            for spares in (2, 8):
                for placement_id, native_placement, seed, placement in PLACEMENTS:
                    for cleaner_id, native_cleaner, cleaner in CLEANERS:
                        name = f"z{blocks}-h{spares}-{placement_id}-{cleaner_id}.json"
                        main_path = result / "replay" / name
                        reference_path = result / "reference" / name
                        comparison_path = result / "comparison" / name
                        main = json.loads(main_path.read_text())
                        reference = json.loads(reference_path.read_text())
                        comparison = json.loads(comparison_path.read_text())
                        if main.get("schema") != "zns-ann-z0b-native-replay-v1" or main.get("engine") != "main":
                            fail(f"main schema/engine mismatch: {trace_id}/{name}")
                        if reference.get("schema") != "zns-ann-z0b-native-reference-v1" or reference.get("engine") != "reference":
                            fail(f"reference schema/engine mismatch: {trace_id}/{name}")
                        if projection(main) != projection(reference):
                            fail(f"main/reference exact projection mismatch: {trace_id}/{name}")
                        if (comparison.get("schema") != "zns-ann-z0b-native-exact-comparison-v1" or
                                comparison.get("status") != "pass" or comparison.get("primary_equals_reference") is not True or
                                comparison.get("main_sha256") != sha256_path(main_path) or
                                comparison.get("reference_sha256") != sha256_path(reference_path)):
                            fail(f"comparison digest/status mismatch: {trace_id}/{name}")
                        config_id = name[:-5]
                        expected = {
                            "trace_id": trace_id, "system": system, "realization": realization,
                            "capacity_blocks": blocks, "host_spares": spares,
                            "placement": placement, "native_placement": native_placement,
                            "seed": seed, "cleaner": cleaner, "native_cleaner": native_cleaner,
                            "config_id": config_id,
                        }
                        records.append(validate_result(main, expected, f"{trace_id}/{name}"))
                        hashes[f"{trace_id}/{name}"] = sha256_path(main_path)
    if any(values != {1, 2, 3} for values in systems.values()) or len(records) != 288:
        fail("six-trace/three-realization/288-configuration closure failure")
    expected_matrix = prereg["matrix"]
    if int(expected_matrix["configurations_per_trace"]) != 48 or int(expected_matrix["total_configurations"]) != 288:
        fail("preregistered matrix count mismatch")
    return records, {"schedule_sha256": sha256_path(schedule_path),
                     "main_result_set_sha256": hashlib.sha256("".join(f"{key} {hashes[key]}\n" for key in sorted(hashes)).encode()).hexdigest()}


def group_key(record: RunRecord) -> tuple[object, ...]:
    return (record.system, record.capacity_blocks, record.host_spares, record.placement, record.cleaner)


def group_id(key: tuple[object, ...]) -> str:
    return f"{key[0]}:z{key[1]}:h{key[2]}:{key[3]}:{key[4]}"


def cross_realization(records: Sequence[RunRecord]) -> list[dict[str, object]]:
    grouped: dict[tuple[object, ...], list[RunRecord]] = {}
    for record in records:
        grouped.setdefault(group_key(record), []).append(record)
    output = []
    for key in sorted(grouped, key=lambda row: tuple(str(item) for item in row)):
        rows = sorted(grouped[key], key=lambda row: row.realization)
        if [row.realization for row in rows] != [1, 2, 3]:
            fail(f"cross-realization group is not exactly r1-r3: {group_id(key)}")
        host = [row.host_wa for row in rows]
        medians = [row.median_victim for row in rows]
        pairwise = []
        for i, j in ((0, 1), (0, 2), (1, 2)):
            raw = exact_w1(rows[i].relocated_pages, rows[j].relocated_pages)
            normalized = normalized_w1(rows[i].relocated_pages, rows[j].relocated_pages)
            pairwise.append({"pair": f"r{rows[i].realization}-r{rows[j].realization}",
                             "empirical_w1_pages": ratio(raw), "normalized_w1": ratio(normalized),
                             "status": "NA-NO-COMPLETE-CYCLES" if raw is None else "defined"})
        defined_medians = [value for value in medians if value is not None]
        regimes = ["ZERO-RECLAIM" if row.reset_count == 0 else
                   "LOW-RECLAIM-1-TO-7" if row.reset_count < 8 else "MULTI-RECLAIM-GE-8"
                   for row in rows]
        output.append({
            "group_id": group_id(key), "system": key[0], "capacity_blocks": key[1],
            "zone_capacity_bytes": int(key[1]) * PAGE, "host_spares": key[2],
            "placement": key[3], "cleaner": key[4],
            "realizations": [row.trace_id for row in rows],
            "host_wa": {"values": [ratio(value) for value in host],
                        "range": [ratio(min(host)), ratio(max(host))]},
            "reset_count": {"values": [row.reset_count for row in rows],
                            "range": [min(row.reset_count for row in rows), max(row.reset_count for row in rows)]},
            "median_victim_valid_fraction": {
                "values": [ratio(value) for value in medians],
                "range": [ratio(min(defined_medians)), ratio(max(defined_medians))]
                if len(defined_medians) == 3 else None,
                "status": "defined" if len(defined_medians) == 3 else "NA-MISSING-COMPLETE-CYCLES",
            },
            "relocated_page_distribution_distance": pairwise,
            "cycle_eligibility_ge_8": [row.eligible for row in rows],
            "cycle_eligibility_consistent": len({row.eligible for row in rows}) == 1,
            "reclaim_regimes": regimes, "reclaim_regime_consistent": len(set(regimes)) == 1,
        })
    if len(output) != 96:
        fail("expected exactly 96 three-realization groups")
    return output


def placement_directions(records: Sequence[RunRecord]) -> list[dict[str, object]]:
    selected = [row for row in records if row.placement in ("Canonical", "RoleSeparated")]
    grouped: dict[tuple[object, ...], dict[str, RunRecord]] = {}
    for row in selected:
        key = (row.system, row.capacity_blocks, row.host_spares, row.cleaner, row.realization, row.trace_id)
        grouped.setdefault(key, {})[row.placement] = row
    per_base: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for key, pair in grouped.items():
        if set(pair) != {"Canonical", "RoleSeparated"}:
            fail("Canonical/RoleSeparated pair closure failure")
        difference = pair["Canonical"].host_wa - pair["RoleSeparated"].host_wa
        base = key[:4]
        per_base.setdefault(base, []).append({"trace_id": key[5], "realization": key[4],
                                               "difference": ratio(difference), "sign": sign(difference)})
    output = []
    for key in sorted(per_base, key=lambda row: tuple(str(item) for item in row)):
        rows = sorted(per_base[key], key=lambda row: int(row["realization"]))
        signs = {int(row["sign"]) for row in rows}
        output.append({
            "comparison_id": f"{key[0]}:z{key[1]}:h{key[2]}:{key[3]}",
            "system": key[0], "capacity_blocks": key[1], "zone_capacity_bytes": int(key[1]) * PAGE,
            "host_spares": key[2], "cleaner": key[3], "per_realization": rows,
            "opposite_direction_flip": -1 in signs and 1 in signs,
            "direction_signs": sorted(signs),
        })
    if len(output) != 16:
        fail("expected exactly 16 Canonical/RoleSeparated direction comparisons")
    return output


def trends(records: Sequence[RunRecord], prereg: dict[str, object]) -> list[dict[str, object]]:
    bootstrap = prereg["trend"]["bootstrap"]
    output = []
    for row in sorted(records, key=lambda item: (item.trace_id, item.config_id)):
        if row.system != "OdinANN" or not row.eligible:
            continue
        start = row.reset_count // 2
        indices = row.cycle_indices[start:]
        metric_values = {
            "HostWA_cycle": row.cycle_host_wa[start:],
            "relocated_pages_cycle": tuple(Fraction(value) for value in row.relocated_pages[start:]),
            "victim_valid_fraction": row.victim_fractions[start:],
        }
        metric_rows = [trend_result(metric_values[metric], indices, row.config_id, row.trace_id,
                                    metric, bootstrap) for metric in METRICS]
        output.append({
            "trace_id": row.trace_id, "realization": row.realization,
            "config_id": row.config_id, "capacity_blocks": row.capacity_blocks,
            "zone_capacity_bytes": row.capacity_blocks * PAGE, "host_spares": row.host_spares,
            "placement": row.placement, "cleaner": row.cleaner,
            "complete_cycle_count": row.reset_count, "sample_start_zero_based": start,
            "sample_rule": "last ceil(C/2)", "metrics": metric_rows,
            "all_three_no_detected_sequence_trend": all(metric["trend_label"] == "NO-DETECTED-SEQUENCE-TREND" for metric in metric_rows),
        })
    return output


def decision_facts(records: Sequence[RunRecord], groups: Sequence[dict[str, object]],
                   directions: Sequence[dict[str, object]], trend_rows: Sequence[dict[str, object]]) -> dict[str, object]:
    odin = [row for row in records if row.system == "OdinANN"]
    odin_nonoracle = [row for row in odin if row.placement in TRANSPARENT]
    stable = {(row["trace_id"], row["config_id"]) for row in trend_rows
              if row["placement"] in ("Canonical", "RoleSeparated") and row["all_three_no_detected_sequence_trend"]}
    odin_groups = [row for row in groups if row["system"] == "OdinANN"]
    dgai_groups = [row for row in groups if row["system"] == "DGAI"]
    signal_traces = sorted({row.trace_id for row in odin_nonoracle if row.eligible})
    single_trace_groups = [row["group_id"] for row in odin_groups
                           if sum(bool(value) for value in row["cycle_eligibility_ge_8"]) == 1]
    random_mixed = []
    random_index: dict[tuple[object, ...], dict[str, bool]] = {}
    placement_index: dict[tuple[object, ...], dict[str, RunRecord]] = {}
    for row in odin:
        placement_index.setdefault((row.trace_id, row.capacity_blocks, row.host_spares, row.cleaner), {})[row.placement] = row
        if not row.placement.startswith("RandomPacking-"):
            continue
        key = (row.trace_id, row.capacity_blocks, row.host_spares, row.cleaner)
        random_index.setdefault(key, {})[row.placement] = row.eligible
    for key, values in sorted(random_index.items(), key=lambda item: tuple(str(value) for value in item[0])):
        if len(set(values.values())) > 1:
            random_mixed.append({"trace_id": key[0], "capacity_blocks": key[1], "host_spares": key[2],
                                 "cleaner": key[3], "eligibility_by_seed": values})
    placement_profiles = []
    oracle_differences = []
    for key, values in sorted(placement_index.items(), key=lambda item: tuple(str(value) for value in item[0])):
        if set(values) != {row[3] for row in PLACEMENTS}:
            fail("Odin placement profile does not contain all six placements")
        eligibility = {placement: values[placement].eligible for placement in sorted(values)}
        placement_profiles.append({
            "trace_id": key[0], "capacity_blocks": key[1], "host_spares": key[2],
            "cleaner": key[3], "cycle_eligibility_by_placement": eligibility,
            "transparent_eligibility_mixed": len({eligibility[name] for name in TRANSPARENT}) > 1,
        })
        oracle = values["OfflineHotColdOracle"].host_wa
        oracle_differences.append({
            "trace_id": key[0], "capacity_blocks": key[1], "host_spares": key[2], "cleaner": key[3],
            "oracle_minus_canonical_host_wa": ratio(oracle - values["Canonical"].host_wa),
            "oracle_minus_role_separated_host_wa": ratio(oracle - values["RoleSeparated"].host_wa),
        })
    return {
        "exact_closure": {
            "all_six_trace_final_closure_pass": True, "all_288_main_reference_exact_pass": True,
            "sequence_only": True, "temporal_fields_used": False,
            "materialization_hostwa_tail_accounts_closed": True,
        },
        "PASS-RECLAIM-SIGNAL": {
            "odin_nonoracle_any_run_ge_8_cycles": any(row.eligible for row in odin_nonoracle),
            "odin_nonoracle_any_group_all_three_ge_8_cycles": any(
                row["placement"] in TRANSPARENT and all(row["cycle_eligibility_ge_8"]) for row in odin_groups),
            "canonical_or_role_any_run_ge_8_and_all_three_metrics_no_trend": bool(stable),
            "odin_all_group_eligibility_consistent": all(row["cycle_eligibility_consistent"] for row in odin_groups),
            "odin_nonoracle_signal_trace_ids": signal_traces,
            "signal_present_in_more_than_one_odin_trace": len(signal_traces) > 1,
            "single_odin_trace_signal_groups": single_trace_groups,
            "conclusion_depends_only_on_random_packing": (
                any(row.eligible and row.placement.startswith("RandomPacking-") for row in odin) and
                not any(row.eligible and row.placement in ("Canonical", "RoleSeparated") for row in odin)),
        },
        "HOLD-PLACEMENT-DOMINATED": {
            "canonical_role_opposite_direction_flip_ids": [row["comparison_id"] for row in directions if row["opposite_direction_flip"]],
            "random_seed_cycle_eligibility_flip_facts": random_mixed,
            "placement_cycle_eligibility_profiles": placement_profiles,
            "oracle_host_wa_exact_difference_facts": oracle_differences,
            "odin_multi_realization_regime_inconsistency_ids": [row["group_id"] for row in odin_groups if not row["reclaim_regime_consistent"]],
            "dgai_multi_realization_regime_inconsistency_ids": [row["group_id"] for row in dgai_groups if not row["reclaim_regime_consistent"]],
            "arbitrary_difference_threshold": None,
            "note": "Magnitude-based placement dominance is intentionally not auto-decided because preregistered thresholds are null.",
        },
        "KILL-NO-RECLAIM-SIGNAL": {
            "odin_all_nonoracle_runs_below_8_cycles": not any(row.eligible for row in odin_nonoracle),
            "no_canonical_or_role_eligible_run_with_all_metrics_no_trend": not bool(stable),
            "eligible_odin_nonstationary_metric_count": sum(
                metric["trend_label"] == "NONSTATIONARY" for row in trend_rows for metric in row["metrics"]),
            "exact_replay_failure_count": 0,
            "toy_geometry_or_trace_looping_used": False,
        },
        "verdict_domain": ["PASS-RECLAIM-SIGNAL", "HOLD-PLACEMENT-DOMINATED", "KILL-NO-RECLAIM-SIGNAL"],
        "automatic_final_verdict": None,
        "automatic_final_verdict_reason": "The preregistration leaves placement magnitude/range thresholds null; this file emits exact decision facts without inventing them.",
    }


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    if path.exists() or temporary.exists():
        fail(f"refusing output reuse: {path}")
    with temporary.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def analyze(args: argparse.Namespace) -> dict[str, object]:
    campaign = args.campaign_root.resolve(strict=True)
    prereg_path = args.preregistration.resolve(strict=True)
    prereg = json.loads(prereg_path.read_text())
    if prereg.get("schema") != "zns-ann-z0b-preregistration-v1":
        fail("preregistration schema mismatch")
    matrix = prereg.get("matrix", {})
    trend = prereg.get("trend", {})
    bootstrap = trend.get("bootstrap", {})
    cross = prereg.get("cross_realization", {})
    if (prereg.get("ordering", {}).get("timestamps_permitted") is not False or
            matrix.get("trace_realizations") != 6 or
            matrix.get("zone_capacity_blocks_4096") != [65536, 262144] or
            matrix.get("host_spare_zones") != [2, 8] or
            matrix.get("placements") != [row[3] for row in PLACEMENTS] or
            matrix.get("cleaners") != [row[2] for row in CLEANERS] or
            matrix.get("configurations_per_trace") != 48 or matrix.get("total_configurations") != 288 or
            trend.get("eligible_minimum_complete_cycles") != 8 or
            trend.get("sample_start_zero_based") != "floor(C/2)" or
            trend.get("metrics") != list(METRICS) or
            bootstrap.get("resamples") != 100000 or bootstrap.get("master_seed") != 2026071904 or
            bootstrap.get("confidence_interval") != "percentile 90% [5th, 95th]" or
            cross.get("arbitrary_difference_threshold") is not None or
            cross.get("relocated_page_distribution_distance", {}).get("threshold") is not None):
        fail("preregistered matrix/trend/threshold contract drift")
    records, input_digests = load_records(campaign, prereg)
    groups = cross_realization(records)
    directions = placement_directions(records)
    trend_rows = trends(records, prereg)
    result = {
        "schema": "zns-ann-z0b-288-postprocess-v1", "status": "pass",
        "preregistration_sha256": sha256_path(prereg_path), **input_digests,
        "trace_count": 6, "configuration_count": 288,
        "main_reference_exact_pass_count": 288,
        "temporal_fields_used": False, "timestamps_emitted": False,
        "cross_realization_group_count": len(groups), "cross_realization": groups,
        "canonical_role_direction_count": len(directions), "canonical_role_direction": directions,
        "odin_eligible_trend_configuration_count": len(trend_rows), "odin_eligible_trends": trend_rows,
        "decision_facts": decision_facts(records, groups, directions, trend_rows),
    }
    atomic_json(args.output, result)
    return {"status": "pass", "traces": 6, "configurations": 288,
            "groups": len(groups), "trend_configurations": len(trend_rows)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path,
                        default=Path(__file__).with_name("preregistration.json"))
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(analyze(parser.parse_args()), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"analyze_endpoint_results: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
