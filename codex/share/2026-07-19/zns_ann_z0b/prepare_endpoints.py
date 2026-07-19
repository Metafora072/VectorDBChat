#!/usr/bin/env python3
"""Prepare six independent Z0B endpoint clones; dry-run by default.

Formal preparation requires an explicit acknowledgement and a fully passing
prelaunch gate.  It never overwrites, retries, or removes an old attempt.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from endpoint_common import (
    BUILD,
    PREREGISTRATION,
    RUN_ROOT,
    SHARE,
    TOOLCHAIN_LOCK,
    allocated_bytes,
    atomic_json,
    load_json,
    locked_tool,
    schedule,
    schedule_document,
    timestamp_pair,
    tool_command,
)


ACK = "I_ACKNOWLEDGE_Z0B_6_INDEPENDENT_NVME_CLONES"


def run_checked(command: list[str], log: Path | None = None) -> None:
    if log is None:
        subprocess.run(command, check=True)
        return
    with log.open("ab", buffering=0) as handle:
        subprocess.run(command, check=True, stdout=handle, stderr=subprocess.STDOUT)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    gate_command = [sys.executable, str(SHARE / "prelaunch_gate.py"), "--mode", "prepare"]
    if args.execute:
        gate_command.append("--require-launch-ready")
    gate = subprocess.run(gate_command, text=True, capture_output=True)
    try:
        gate_report = json.loads(gate.stdout)
    except json.JSONDecodeError:
        gate_report = {"audit_status": "fail", "stderr": gate.stderr}
    if gate.returncode != 0:
        print(json.dumps(gate_report, indent=2, sort_keys=True))
        raise SystemExit(gate.returncode)

    rows = schedule()
    clone_source_bytes = sum(allocated_bytes(Path(str(row["initial_root"]))) for row in rows)
    plan = {
        "schema": "zns-ann-z0b-prepare-plan-v1",
        "timestamps": timestamp_pair(),
        "mode": "execute" if args.execute else "dry-run",
        "formal_full_trace_started": False,
        "target": str(RUN_ROOT),
        "frozen_build": str(BUILD),
        "runs": rows,
        "clone_source_allocated_bytes": clone_source_bytes,
        "prelaunch_audit_status": gate_report.get("audit_status"),
        "launch_ready": gate_report.get("launch_ready"),
    }
    if not args.execute:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return

    if os.environ.get("Z0B_PREPARE_AUTHORIZED") != ACK:
        raise SystemExit(f"formal prepare blocked: set Z0B_PREPARE_AUTHORIZED={ACK}")
    if os.geteuid() != 0:
        raise SystemExit("formal prepare must execute as root (runtime clones are handed to uid 1000)")
    if RUN_ROOT.exists():
        raise SystemExit(f"campaign root reuse is forbidden: {RUN_ROOT}")

    compactor = locked_tool("compact_extent_manifest")
    # The compact object registry binds absolute clone paths.  Therefore the
    # campaign must be prepared at its final pathname; renaming a staging root
    # would silently invalidate object identity.  A partial root is retained
    # on failure and is permanently non-reusable.
    temp_root = RUN_ROOT
    temp_root.mkdir(mode=0o700)
    os.chown(temp_root, 1000, 1000)
    try:
        atomic_json(temp_root / "schedule.json", schedule_document(), exclusive=True)
        atomic_json(temp_root / "prepare_plan.json", plan, exclusive=True)
        shutil.copy2(PREREGISTRATION, temp_root / "preregistration.json")
        shutil.copy2(TOOLCHAIN_LOCK, temp_root / "endpoint_toolchain_lock.json")
        atomic_json(temp_root / "CAMPAIGN_IDENTITY.json", {
            "schema": "zns-ann-z0b-campaign-identity-v1",
            "timestamps": timestamp_pair(),
            "formal_build": str(BUILD),
            "formal_build_marker": str(BUILD / "Z0B_BUILD_OK"),
            "nvme_only": True,
            "independent_traces": 3,
            "reuse_permitted": False,
        }, exclusive=True)

        for row in rows:
            label = str(row["label"])
            work = temp_root / "work" / label
            result = temp_root / "results" / label
            index = work / "index"
            result.mkdir(parents=True, mode=0o700)
            work.mkdir(parents=True, mode=0o700)
            os.chown(result, 1000, 1000)
            os.chown(work, 1000, 1000)
            log = result / "prepare.log"
            source = Path(str(row["initial_root"]))
            index.mkdir(mode=0o700)
            run_checked(["cp", "-a", "--reflink=auto", str(source) + "/.", str(index)], log)
            run_checked(["chmod", "-R", "u+w", str(index)], log)
            os.chown(index, 1000, 1000)
            run_checked(tool_command(compactor) + [
                "prepare",
                "--initial-root", str(index),
                "--run-id", str(row["run_uuid"]),
                "--system", str(row["system"]),
                "--object-map", str(result / "object_registry.tsv"),
                "--output", str(result / "initial_extents.bin"),
                "--summary", str(result / "initial_extents_summary.json"),
            ], log)
            summary = load_json(result / "initial_extents_summary.json")
            if summary.get("status") != "pass":
                raise RuntimeError(f"initial compact manifest failed: {label}")
            if not (result / "initial_extents.bin").is_file() or not (result / "object_registry.tsv").is_file():
                raise RuntimeError(f"initial compact outputs absent: {label}")
            os.chmod(result / "initial_extents.bin", 0o444)
            os.chmod(result / "initial_extents_summary.json", 0o444)
            os.chmod(result / "object_registry.tsv", 0o444)
            (work / "PREPARED_OK").touch(exist_ok=False)
            atomic_json(result / "prepare_status.json", {
                "schema": "zns-ann-z0b-attempt-prepare-v1",
                "status": "pass",
                "timestamps": timestamp_pair(),
                "label": label,
                "allocated_bytes": allocated_bytes(work) + allocated_bytes(result),
            }, exclusive=True)

        (temp_root / "PREPARED_OK").touch(exist_ok=False)
        print(json.dumps({
            "status": "pass",
            "prepared_root": str(RUN_ROOT),
            "formal_full_trace_started": False,
            "timestamps": timestamp_pair(),
        }, indent=2, sort_keys=True))
    except BaseException as exc:
        atomic_json(temp_root / "PREPARE_FAILED.json", {
            "schema": "zns-ann-z0b-prepare-failure-v1",
            "status": "failed",
            "timestamps": timestamp_pair(),
            "error": repr(exc),
            "manual_disposition_required": True,
            "automatic_delete_or_retry": False,
        })
        raise


if __name__ == "__main__":
    main()
