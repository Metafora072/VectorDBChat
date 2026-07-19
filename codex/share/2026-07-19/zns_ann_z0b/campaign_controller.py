#!/usr/bin/env python3
"""Persistent prepare-then-run wrapper for the one authorized Z0B campaign."""

from __future__ import annotations

import os
import subprocess
import sys

from endpoint_common import RUN_ROOT, SHARE, atomic_json, timestamp_pair


PREPARE_ACK = "I_ACKNOWLEDGE_Z0B_6_INDEPENDENT_NVME_CLONES"
RUN_ACK = "I_ACKNOWLEDGE_Z0B_6_FULL_TRACES_FAIL_STOP_NO_RETRY"


def status(phase: str, state: str, returncode: int | None = None) -> None:
    if not RUN_ROOT.exists():
        return
    payload: dict[str, object] = {
        "schema": "zns-ann-z0b-controller-status-v1",
        "phase": phase,
        "status": state,
        "timestamps": timestamp_pair(),
    }
    if returncode is not None:
        payload["returncode"] = returncode
    atomic_json(RUN_ROOT / "controller_status.json", payload)


def invoke(script: str, acknowledgement: str, value: str) -> int:
    environment = os.environ.copy()
    environment[acknowledgement] = value
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run([
        sys.executable, str(SHARE / script), "--execute",
    ], env=environment)
    return completed.returncode


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Z0B campaign controller must run as root")
    prepare_rc = invoke("prepare_endpoints.py", "Z0B_PREPARE_AUTHORIZED", PREPARE_ACK)
    if prepare_rc:
        status("prepare", "failed_stopped", prepare_rc)
        raise SystemExit(prepare_rc)
    status("prepare", "pass")
    run_rc = invoke("run_endpoints.py", "Z0B_ALL_RUNS_AUTHORIZED", RUN_ACK)
    running = RUN_ROOT / "RUNNING"
    if running.exists():
        running.unlink()
    if run_rc:
        status("run", "failed_stopped", run_rc)
        raise SystemExit(run_rc)
    status("complete", "pass", 0)


if __name__ == "__main__":
    main()
