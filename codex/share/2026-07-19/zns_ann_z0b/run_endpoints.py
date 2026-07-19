#!/usr/bin/env python3
"""Sequential fail-stop controller for the six Z0B FULL endpoint traces."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys

from endpoint_common import (
    PREREGISTRATION,
    RUN_ROOT,
    SHARE,
    atomic_json,
    load_json,
    locked_tool,
    schedule,
    timestamp_pair,
    tool_command,
)


ACK = "I_ACKNOWLEDGE_Z0B_6_FULL_TRACES_FAIL_STOP_NO_RETRY"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    rows = schedule()
    if not args.execute:
        gate = subprocess.run(
            [sys.executable, str(SHARE / "prelaunch_gate.py"), "--mode", "audit"],
            text=True, capture_output=True,
        )
        report = json.loads(gate.stdout)
        print(json.dumps({
            "schema": "zns-ann-z0b-run-plan-v1",
            "timestamps": timestamp_pair(),
            "mode": "dry-run",
            "formal_full_trace_started": False,
            "failure_policy": "stop on first failure; never retry or reuse",
            "runtime_interposition": "r05 libz0btrace.so:frozen M3 libm0write.so",
            "normalizer_accepted_profile": "trace_ledger.json",
            "m0_profiler_closure": "independent exact request-count/requested-byte comparison",
            "order": [row["label"] for row in rows],
            "prelaunch_audit_status": report.get("audit_status"),
            "launch_ready": report.get("launch_ready"),
        }, indent=2, sort_keys=True))
        raise SystemExit(gate.returncode)

    if os.environ.get("Z0B_ALL_RUNS_AUTHORIZED") != ACK:
        raise SystemExit(f"formal run blocked: set Z0B_ALL_RUNS_AUTHORIZED={ACK}")
    gate = subprocess.run([
        sys.executable, str(SHARE / "prelaunch_gate.py"), "--mode", "run", "--require-launch-ready"
    ])
    if gate.returncode:
        raise SystemExit(gate.returncode)
    if (RUN_ROOT / "CAMPAIGN_STARTED").exists():
        raise SystemExit("campaign reuse/restart is forbidden")

    lock_path = RUN_ROOT / "campaign.lock"
    with lock_path.open("x") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another Z0B controller holds the global lock")
        (RUN_ROOT / "CAMPAIGN_STARTED").touch(exist_ok=False)
        (RUN_ROOT / "RUNNING").touch(exist_ok=False)
        for row in rows:
            label = str(row["label"])
            environment = os.environ.copy()
            environment["Z0B_GLOBAL_LOCK_HELD"] = "1"
            environment["Z0B_FULL_TRACE_AUTHORIZED"] = "I_ACKNOWLEDGE_ONE_FROZEN_Z0B_FULL_TRACE"
            command = [sys.executable, str(SHARE / "run_one_endpoint.py"), label]
            result = subprocess.run(command, env=environment)
            if result.returncode:
                atomic_json(RUN_ROOT / "CAMPAIGN_FAILED.json", {
                    "schema": "zns-ann-z0b-campaign-failure-v1",
                    "status": "failed_stopped",
                    "timestamps": timestamp_pair(),
                    "failed_label": label,
                    "returncode": result.returncode,
                    "retry_permitted": False,
                }, exclusive=True)
                raise SystemExit(result.returncode)
        analyzer = locked_tool("analyze_endpoint_results")
        analysis_output = RUN_ROOT / "analysis.json"
        with (RUN_ROOT / "analysis.log").open("xb", buffering=0) as log:
            postprocess = subprocess.run(tool_command(analyzer) + [
                "--campaign-root", str(RUN_ROOT),
                "--preregistration", str(PREREGISTRATION),
                "--output", str(analysis_output),
            ], stdout=log, stderr=subprocess.STDOUT)
        if postprocess.returncode or not analysis_output.is_file():
            atomic_json(RUN_ROOT / "CAMPAIGN_FAILED.json", {
                "schema": "zns-ann-z0b-campaign-failure-v1",
                "status": "failed_stopped",
                "timestamps": timestamp_pair(),
                "failed_label": "postprocess-288-config",
                "returncode": postprocess.returncode,
                "retry_permitted": False,
            }, exclusive=True)
            raise SystemExit(postprocess.returncode or 1)
        analysis = load_json(analysis_output)
        if (analysis.get("schema") != "zns-ann-z0b-288-postprocess-v1" or
                analysis.get("status") != "pass" or
                int(analysis.get("main_reference_exact_pass_count", -1)) != 288 or
                analysis.get("temporal_fields_used") is not False or
                analysis.get("timestamps_emitted") is not False):
            atomic_json(RUN_ROOT / "CAMPAIGN_FAILED.json", {
                "schema": "zns-ann-z0b-campaign-failure-v1",
                "status": "failed_stopped",
                "timestamps": timestamp_pair(),
                "failed_label": "postprocess-288-config-validation",
                "returncode": 1,
                "retry_permitted": False,
            }, exclusive=True)
            raise SystemExit(1)
        (RUN_ROOT / "CAMPAIGN_OK").touch(exist_ok=False)
        atomic_json(RUN_ROOT / "campaign_status.json", {
            "schema": "zns-ann-z0b-campaign-status-v1",
            "status": "pass",
            "timestamps": timestamp_pair(),
            "completed_traces": 6,
            "total_traces": 6,
            "postprocessed_configurations": 288,
            "analysis": str(analysis_output),
        }, exclusive=True)


if __name__ == "__main__":
    main()
