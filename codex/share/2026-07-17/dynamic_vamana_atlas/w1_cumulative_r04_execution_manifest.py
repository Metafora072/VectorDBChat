#!/usr/bin/env python3
"""Create or transition the fail-closed CP05 cumulative R04 execution manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with temporary.open("w") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("activate", "phase", "stop", "complete"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--dgai-replay-base-manifest", type=Path)
    parser.add_argument("--odin-replay-base-manifest", type=Path)
    parser.add_argument("--static-smoke", type=Path)
    parser.add_argument("--old-attempt-manifest", type=Path)
    parser.add_argument("--phase")
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    now_ns = time.time_ns()
    if args.action == "activate":
        required = (args.preflight, args.dgai_replay_base_manifest, args.odin_replay_base_manifest,
                    args.static_smoke, args.old_attempt_manifest)
        if args.manifest.exists() or any(path is None or not path.is_file() for path in required):
            raise SystemExit("R04 activation requires fresh manifest and all frozen gate evidence")
        preflight = json.loads(args.preflight.read_text())
        if preflight.get("status") != "pass":
            raise SystemExit("preflight did not pass")
        old = json.loads(args.old_attempt_manifest.read_text())
        if (old.get("schema") != "dynamic-vamana-w1-cp05-cumulative-r03-execution-v1"
                or old.get("status") != "stopped_failed" or old.get("stopped_phase") != "replay_DGAI"):
            raise SystemExit("old cumulative attempt is not the accepted terminal replay_DGAI stop")
        atlas_root = args.manifest.resolve().parents[2]
        payload: dict[str, object] = {
            "schema": "dynamic-vamana-w1-cp05-cumulative-r04-execution-v1",
            "status": "running",
            "phase": args.phase or "execution_deltas",
            "started_unix_ns": now_ns,
            "controller_pid": int(os.environ.get("W1_CONTROLLER_PID", "0")),
            "preflight_realpath": str(args.preflight.resolve()),
            "preflight_sha256": sha256(args.preflight),
            "run": "pilot3_sift10m_w1_cp05_trajectory_r04",
            "result_root": str(args.manifest.parent.resolve()),
            "formal_root": str(atlas_root / "formal/pilot3_sift10m_w1_cp05_trajectory_r04"),
            "replay_run": "pilot3_w1_cp05_trajectory_replay_r04",
            "replay_formal_root": str(atlas_root / "formal/pilot3_w1_cp05_trajectory_replay_r04"),
            "execution_delta_root": str(atlas_root / "datasets/sift10m/w1_trajectory/execution_deltas_r03"),
            "replay_input_root": str(atlas_root / "results/pilot3_sift10m_w1_cp05_trajectory_r03/replay/inputs"),
            "immutable_replay_base_root": str(atlas_root / "formal/pilot3_w1_cp05_replay_bases_v1"),
            "replay_base_manifests": {
                "DGAI": {"realpath": str(args.dgai_replay_base_manifest.resolve()),
                         "sha256": sha256(args.dgai_replay_base_manifest)},
                "OdinANN": {"realpath": str(args.odin_replay_base_manifest.resolve()),
                            "sha256": sha256(args.odin_replay_base_manifest)},
            },
            "static_smoke_realpath": str(args.static_smoke.resolve()),
            "static_smoke_sha256": sha256(args.static_smoke),
            "terminal_r03_manifest_realpath": str(args.old_attempt_manifest.resolve()),
            "terminal_r03_manifest_sha256": sha256(args.old_attempt_manifest),
            "authorized_sequence": ["CP00", "CP01", "CP05"],
            "attempts": {
                "DGAI_replay": "sequential-cp80-04",
                "OdinANN_replay": "sequential-cp80-04",
                "DGAI_formal": "trajectory-cp05-04",
                "OdinANN_formal": "trajectory-cp05-04",
                "DiskANN": "stale-cp05-04",
            },
            "old_attempt_reused": False,
            "r03_clone_result_attempt_reused": False,
            "r03_delta_and_replay_inputs_reused_readonly": True,
            "cp10_cp20": "HOLD",
            "retry_policy": "none",
        }
    else:
        if not args.manifest.is_file():
            raise SystemExit("execution manifest absent")
        payload = json.loads(args.manifest.read_text())
        if payload.get("status") not in ("running",):
            raise SystemExit("terminal execution manifest cannot transition")
        if args.action == "phase":
            if not args.phase:
                raise SystemExit("phase transition requires --phase")
            payload["phase"] = args.phase
            payload["phase_updated_unix_ns"] = now_ns
        elif args.action == "stop":
            payload.update(
                status="stopped_failed",
                stopped_phase=args.phase or payload.get("phase"),
                exit_code=args.exit_code,
                stopped_unix_ns=now_ns,
            )
        else:
            if args.summary is None or not args.summary.is_file():
                raise SystemExit("complete transition requires summary")
            payload.update(
                status="complete",
                phase="complete",
                completed_unix_ns=now_ns,
                summary_realpath=str(args.summary.resolve()),
                summary_sha256=sha256(args.summary),
            )
    write_atomic(args.manifest, payload)


if __name__ == "__main__":
    main()
