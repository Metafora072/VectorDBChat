#!/usr/bin/env python3
"""Validate the R03 shared query-scope positive and missing-primer fixtures."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any


def fail(message: str) -> None:
    raise ValueError(message)


def require(value: bool, message: str) -> None:
    if not value:
        fail(message)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def identity(path: Path) -> dict[str, Any]:
    path = path.resolve(strict=True); digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return {"realpath": str(path), "size_bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def validate_gate(path: Path, system: str, expected_l: int, device: str) -> dict[str, Any]:
    gate = load(path)
    require(gate.get("schema") == "dynamic-vamana-w1-query-identity-v2"
            and gate.get("status") == "pass" and gate.get("system") == system,
            f"{system} positive query gate is not PASS")
    points = gate.get("points", [])
    require(len(points) == 1 and points[0].get("L") == expected_l, f"{system} fixture point mismatch")
    point = points[0]
    require(int(point.get("baseline_target_read_bytes", 0)) >= 4096
            and int(point.get("baseline_target_read_ios", 0)) >= 1
            and int(point.get("query_target_read_bytes_delta", 0)) > 0
            and int(point.get("query_target_read_ios_delta", 0)) > 0
            and point.get("primer_excluded_from_delta") is True
            and point.get("device_read_bytes") == point.get("query_target_read_bytes_delta")
            and point.get("device_read_ios") == point.get("query_target_read_ios_delta"),
            f"{system} primer/query accounting boundary invalid")
    require(gate.get("identities", {}).get("device") == device, f"{system} fixture device mismatch")
    return {"status": "pass", "gate": identity(path), "point": point}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dgai-gate", type=Path, required=True)
    parser.add_argument("--odin-gate", type=Path, required=True)
    parser.add_argument("--negative-resource", type=Path, required=True)
    parser.add_argument("--dgai-content-before", type=Path, required=True)
    parser.add_argument("--dgai-content-after", type=Path, required=True)
    parser.add_argument("--dgai-mode-before", type=Path, required=True)
    parser.add_argument("--dgai-mode-after", type=Path, required=True)
    parser.add_argument("--odin-content-before", type=Path, required=True)
    parser.add_argument("--odin-content-after", type=Path, required=True)
    parser.add_argument("--odin-mode-before", type=Path, required=True)
    parser.add_argument("--odin-mode-after", type=Path, required=True)
    parser.add_argument("--device", default="259:10")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    dgai = validate_gate(args.dgai_gate, "DGAI", 64, args.device)
    odin = validate_gate(args.odin_gate, "OdinANN", 29, args.device)
    for system, before, after in (
        ("DGAI-content", args.dgai_content_before, args.dgai_content_after),
        ("DGAI-mode", args.dgai_mode_before, args.dgai_mode_after),
        ("OdinANN-content", args.odin_content_before, args.odin_content_after),
        ("OdinANN-mode", args.odin_mode_before, args.odin_mode_after),
    ):
        require(before.read_bytes() == after.read_bytes(), f"{system} changed across positive fixture")

    negative = load(args.negative_resource)
    samples = negative.get("samples", [])
    require(negative.get("returncode") == 0 and isinstance(samples, list) and len(samples) >= 2,
            "missing-primer negative resource is incomplete")
    require(not any(row.get("device") == args.device for row in samples[0].get("cgroup_io_stat", [])),
            "missing-primer negative unexpectedly has target device in baseline")
    evidence_path = Path(__file__).with_name("w1_cumulative_evidence_r03.py")
    spec = importlib.util.spec_from_file_location("w1_r03_evidence", evidence_path)
    require(spec is not None and spec.loader is not None, "strict evidence parser unavailable")
    evidence = importlib.util.module_from_spec(spec); spec.loader.exec_module(evidence)
    rejected = False; rejection = ""
    try:
        evidence.resource_read_delta(negative, args.device)
    except evidence.GateError as exc:
        rejected = True; rejection = str(exc)
    require(rejected and "expected exactly one cgroup io row" in rejection,
            "strict parser did not reject missing-primer baseline")

    report = {
        "schema": "dynamic-vamana-w1-r03-query-scope-primer-tests-v1", "status": "pass",
        "shared_launcher": identity(Path(__file__).with_name("w1_run_query_scope.sh")),
        "primer_helper": identity(Path(__file__).with_name("w1_query_io_primer.py")),
        "DGAI_L64_positive": dgai, "OdinANN_L29_positive": odin,
        "missing_primer_negative": {"status": "pass", "resource": identity(args.negative_resource),
                                     "baseline_target_row_absent": True,
                                     "strict_parser_rejected": True, "rejection": rejection},
        "primer_accounting_boundary": "final-minus-baseline excludes 4096-byte primer",
        "base_content_mode_unchanged": True,
    }
    if args.output.exists() or args.output.is_symlink():
        fail(f"test output reuse refused: {args.output}")
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n"); stream.flush(); os.fsync(stream.fileno())


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"w1_query_scope_tests: {exc}") from exc
