#!/usr/bin/env python3
"""Revalidate every preflight-bound R05 input and infrastructure artifact."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any


SCHEMA = "dynamic-vamana-w1-cp05-cumulative-r05-preservation-v1"


def require(value: bool, message: str) -> None:
    if not value: raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""): digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text()); require(isinstance(value, dict), f"JSON object required: {path}")
    return value


def load_helper() -> Any:
    path = Path(__file__).with_name("w1_cp05_r05_preflight.py")
    spec = importlib.util.spec_from_file_location("w1_cp05_r05_preflight_import", path)
    require(spec is not None and spec.loader is not None, "cannot import R05 preflight helper")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def write_new(path: Path, value: dict[str, Any]) -> None:
    require(not path.exists() and not path.is_symlink(), f"preservation overwrite refused: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())


def validate(args: argparse.Namespace) -> dict[str, Any]:
    helper = load_helper(); preflight_path = args.preflight.resolve(strict=True); preflight = load(preflight_path)
    require(preflight.get("schema") == "dynamic-vamana-w1-cp05-cumulative-r05-preflight-v1"
            and preflight.get("status") == "pass", "R05 preflight not PASS")
    result = Path(preflight["fresh_targets"]["result_root"]).resolve(strict=True)
    execution_path = result / "execution_manifest.json"; execution = load(execution_path)
    require(execution.get("status") in ("running", "complete", "stopped_failed"), "execution status invalid")
    anchor = execution.get("preflight") or {"realpath": execution.get("preflight_realpath"),
                                             "sha256": execution.get("preflight_sha256")}
    require(Path(anchor.get("realpath", "")).resolve(strict=True) == preflight_path
            and anchor.get("sha256") == sha256(preflight_path), "execution/preflight anti-tamper anchor mismatch")

    mismatches: list[dict[str, Any]] = []; checked: dict[str, Any] = {}
    def check_identity(name: str, expected: dict[str, Any]) -> None:
        try: actual = helper.identity(Path(expected["realpath"])); checked[name] = actual
        except (KeyError, OSError, ValueError) as exc:
            mismatches.append({"name": name, "reason": str(exc)}); return
        if actual != expected: mismatches.append({"name": name, "expected": expected, "actual": actual})
    for name, expected in preflight.get("protected_artifacts", {}).items(): check_identity(name, expected)
    check_identity("artifact_manifest", preflight["artifact_manifest"])
    terminal = preflight["terminal_attempt"]["R03"]
    check_identity("terminal_R03_execution_manifest", terminal["execution_manifest"])
    check_identity("terminal_R03_preservation_after_stop", terminal["preservation_after_stop"])
    check_identity("terminal_R03_cp00_query_gate", terminal["cp00_query_gate"])
    terminal_r04 = preflight["terminal_attempt"]["R04"]
    check_identity("terminal_R04_execution_manifest", terminal_r04["execution_manifest"])
    check_identity("terminal_R04_preservation_after_stop", terminal_r04["preservation_after_stop"])
    check_identity("terminal_R04_cp00_query_gate", terminal_r04["cp00_query_gate"])
    check_identity("terminal_R04_stage_local_canary", terminal_r04["stage_local_canary"])
    check_identity("static_load_smoke", preflight["static_load_smoke"])
    check_identity("static_smoke_revalidation", preflight["static_smoke_revalidation"])
    check_identity("query_scope_tests", preflight["query_scope_tests"])
    check_identity("input_canary_tests", preflight["input_canary_tests"])
    tests = load(Path(preflight["query_scope_tests"]["realpath"]))
    for field in ("shared_launcher", "primer_helper"):
        expected = tests[field]; path = Path(expected["realpath"])
        if path.stat().st_size != expected["size_bytes"] or sha256(path) != expected["sha256"]:
            mismatches.append({"name": field, "reason": "shared query-scope tool changed"})
    canary_tests = load(Path(preflight["input_canary_tests"]["realpath"]))
    canary_helper = canary_tests["helper"]; canary_helper_path = Path(canary_helper["realpath"])
    if (canary_helper_path.stat().st_size != canary_helper["size_bytes"]
            or sha256(canary_helper_path) != canary_helper["sha256"]):
        mismatches.append({"name": "input_canary_helper", "reason": "minimal canary helper changed"})
    for system, lineage in preflight.get("immutable_replay_bases", {}).items():
        for key in ("manifest", "accepted_r07_manifest", "base_content", "base_mode", "write_denial"):
            check_identity(f"immutable_{system}_{key}", lineage[key])
        try:
            # Canonical base root is directly recoverable from the bound manifest.
            manifest = load(Path(lineage["manifest"]["realpath"]))
            base_dir = Path(manifest["immutable_base"]["realpath"]).parent
            helper.verify_base(base_dir.parent.parent, system)
        except (OSError, ValueError, KeyError) as exc:
            mismatches.append({"name": f"immutable_{system}_live", "reason": str(exc)})
    reused = preflight["reused_inputs"]
    try:
        delta = helper.tree(Path(reused["delta_root"]), immutable=True)
        if delta != reused["delta_tree"]:
            mismatches.append({"name": "R03_delta_tree", "reason": "live tree differs from preflight"})
        replay = helper.tree(Path(reused["replay_input_root"]), immutable=True)
        if replay != reused["replay_input_tree"]:
            mismatches.append({"name": "R03_replay_input_tree", "reason": "live tree differs from preflight"})
    except (OSError, ValueError) as exc:
        mismatches.append({"name": "R03_reused_input_tree", "reason": str(exc)}); delta = replay = None
    diskann = preflight.get("diskann_lineage", {})
    require(diskann.get("status") == "pass", "DiskANN lineage absent from preflight")
    for key in ("runtime_manifest", "loader_tests", "runtime_environment", "base_content_manifest",
                "base_mode_manifest", "binary"):
        if isinstance(diskann.get(key), dict): check_identity(f"diskann_{key}", diskann[key])
    for index, dependency in enumerate(diskann.get("dependencies", [])):
        path = Path(dependency["realpath"])
        actual = {"size_bytes": path.stat().st_size, "sha256": sha256(path)}
        if (actual["size_bytes"], actual["sha256"]) != (dependency["size_bytes"], dependency["sha256"]):
            mismatches.append({"name": f"diskann_dependency_{index}", "actual": actual, "expected": dependency})

    report = {"schema": SCHEMA, "status": "pass" if not mismatches else "fail", "phase": args.phase,
        "preflight": {"realpath": str(preflight_path), "sha256": sha256(preflight_path)},
        "execution_manifest": helper.identity(execution_path), "checked_count": len(checked),
        "mismatches": mismatches, "artifacts": checked, "r03_delta_tree": delta,
        "r03_replay_input_tree": replay, "immutable_replay_bases_preserved": not any(
            row["name"].startswith("immutable_") for row in mismatches),
        "formal_base_and_diskann_lineage_preserved": not any(
            row["name"].startswith("diskann_") for row in mismatches)}
    write_new(args.output, report)
    if mismatches: raise ValueError("R05 protected input/infrastructure changed")
    return report


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(); parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--phase", default="final"); parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    try: validate(parser().parse_args())
    except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc: raise SystemExit(str(exc)) from exc


if __name__ == "__main__": main()
