#!/usr/bin/env python3
"""Read-only Z0B campaign status, space, stage and ETA reporter."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from endpoint_common import (
    ATLAS,
    FREE_SPACE_MULTIPLIER,
    REGISTERED_PEAK_BYTES,
    RUN_ROOT,
    allocated_bytes,
    load_json,
    schedule,
    timestamp_pair,
)


STAGES = [
    ("prepared", "PREPARED_OK"),
    ("capture_complete", "CAPTURE_OK"),
    ("normalized", "NORMALIZED_OK"),
    ("endpoint_closed", "CLOSURE_OK"),
    ("native_replay", "REPLAY_OK"),
    ("independent_reference", "REFERENCE_OK"),
    ("complete", "Z0B_RUN_OK"),
]


def attempt_status(label: str) -> dict[str, object]:
    work = RUN_ROOT / "work" / label
    result = RUN_ROOT / "results" / label
    failed = result / "FAILED.json"
    stage = "not_prepared"
    completed_steps = 0
    for index, (name, marker) in enumerate(STAGES, start=1):
        if (result / marker).is_file() or (name == "prepared" and (work / marker).is_file()):
            stage = name
            completed_steps = index
        else:
            break
    if (result / "RUN_STARTED").is_file() and completed_steps == 1:
        stage = "capturing"
    failure = load_json(failed) if failed.is_file() else None
    if failure is not None:
        stage = "failed"
    return {
        "label": label,
        "stage": stage,
        "failed": failure is not None,
        "stage_steps_complete": completed_steps,
        "stage_steps_total": len(STAGES),
        "allocated_bytes": allocated_bytes(work) + allocated_bytes(result),
        "failure": failure,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", type=Path, default=RUN_ROOT)
    args = parser.parse_args()
    if args.root.resolve() != RUN_ROOT:
        raise SystemExit(f"only the frozen campaign root is queryable: {RUN_ROOT}")

    rows = [attempt_status(str(row["label"])) for row in schedule()]
    completed = sum(row["stage"] == "complete" for row in rows)
    failed = sum(bool(row["failed"]) for row in rows)
    steps = sum(int(row["stage_steps_complete"]) for row in rows)
    total_steps = len(rows) * len(STAGES)
    probe = RUN_ROOT if RUN_ROOT.exists() else ATLAS
    fs = os.statvfs(probe)
    free_bytes = fs.f_bavail * fs.f_frsize
    used = allocated_bytes(RUN_ROOT)

    # The frozen 5M-event native preflight sustains at least 0.5M policy
    # steps/s.  Keep the preregistered 6--15h end-to-end range rather than a
    # false precise deadline. Operational stage progress is not time progress.
    if completed == len(rows):
        eta_low = eta_high = 0
    elif failed:
        eta_low = eta_high = None
    else:
        fraction_left = max(0.0, 1.0 - steps / total_steps)
        eta_low = round(6 * 3600 * fraction_left)
        eta_high = round(15 * 3600 * fraction_left)

    state = "not_prepared"
    if failed:
        state = "failed_stopped"
    elif completed == len(rows):
        state = "complete"
    elif (RUN_ROOT / "RUNNING").is_file():
        state = "running"
    elif (RUN_ROOT / "PREPARED_OK").is_file():
        state = "prepared_not_running"
    elif (RUN_ROOT / "CAMPAIGN_IDENTITY.json").is_file():
        state = "preparing"

    report = {
        "schema": "zns-ann-z0b-endpoint-status-v1",
        "timestamps": timestamp_pair(),
        "campaign_state": state,
        "formal_full_trace_started": any((RUN_ROOT / "results" / str(r["label"]) / "RUN_STARTED").exists() for r in schedule()),
        "trace_runs_complete": completed,
        "trace_runs_total": len(rows),
        "trace_completion_percent": round(100 * completed / len(rows), 2),
        "operational_stage_percent": round(100 * steps / total_steps, 2),
        "progress_is_time_percent": False,
        "failed_runs": failed,
        "eta_remaining_seconds_range": [eta_low, eta_high] if eta_low is not None else None,
        "eta_basis": "frozen native scale preflight plus preregistered 6-15h end-to-end range",
        "space": {
            "campaign_allocated_bytes": used,
            "registered_peak_bytes": REGISTERED_PEAK_BYTES,
            "peak_utilization_percent": round(100 * used / REGISTERED_PEAK_BYTES, 3),
            "nvme_free_bytes": free_bytes,
            "required_free_at_gate_bytes": int(REGISTERED_PEAK_BYTES * FREE_SPACE_MULTIPLIER),
        },
        "runs": rows,
    }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    ts = report["timestamps"]
    print(f"Z0B status @ {ts['utc_plus_8']} (UTC+8) / {ts['utc']} (UTC)")
    print(f"state={state} traces={completed}/{len(rows)} ({report['trace_completion_percent']}%) "
          f"stage={report['operational_stage_percent']}% [not time percentage]")
    print(f"space={used / 1024**3:.3f} GiB / 129 GiB peak; NVMe free={free_bytes / 1024**3:.3f} GiB")
    if eta_low is None:
        print("ETA=stopped after failure")
    else:
        print(f"ETA range={eta_low / 3600:.1f}-{eta_high / 3600:.1f} hours")
    for row in rows:
        print(f"  {row['label']}: {row['stage']} ({row['allocated_bytes'] / 1024**3:.3f} GiB)")


if __name__ == "__main__":
    main()
