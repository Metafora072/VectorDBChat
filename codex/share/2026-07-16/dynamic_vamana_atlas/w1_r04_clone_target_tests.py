#!/usr/bin/env python3
"""Exercise the R04 full clone capability without creating a clone."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--dgai-base", type=Path, required=True)
    parser.add_argument("--odin-base", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", default="pilot3_sift10m_w1_r04")
    parser.add_argument("--attempt", default="cp01-04")
    args = parser.parse_args()
    root = args.root.resolve()
    label = args.run.rsplit("_", 1)[-1]
    formal = root / "formal" / args.run
    if args.output.exists() or formal.exists() or args.scratch.exists():
        raise SystemExit("R04 clone test freshness guard failed")
    dgai = formal / "DGAI" / args.attempt
    odin = formal / "OdinANN" / args.attempt
    args.scratch.mkdir(parents=True)
    common = os.environ.copy()
    common.update({"W1_FORMAL_PATH_AUTHORIZED": "1", "W1_CLONE_PREFLIGHT_ONLY": "1",
                   "ATLAS_ROOT": str(root), "ATLAS_NVME_MAJMIN": os.environ.get("ATLAS_NVME_MAJMIN", "259:10")})
    rows: list[dict] = []
    default = object()

    def run(name: str, system: str, base: Path, target: Path, expected: int,
            capability_target: Path | None | object = default, capability_system: str | None | object = default,
            capability_run: str | None | object = default,
            capability_attempt: str | None | object = default, device: str | None = None) -> None:
        env = common.copy()
        actual_target = target if capability_target is default else capability_target
        actual_system = system if capability_system is default else capability_system
        actual_run = args.run if capability_run is default else capability_run
        actual_attempt = args.attempt if capability_attempt is default else capability_attempt
        values = {"W1_ALLOWED_CLONE_TARGET": str(actual_target) if actual_target is not None else None,
                  "W1_ALLOWED_CLONE_SYSTEM": actual_system,
                  "W1_ALLOWED_CLONE_RUN": actual_run, "W1_ALLOWED_CLONE_ATTEMPT": actual_attempt}
        for key, value in values.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        if device is not None:
            env["ATLAS_NVME_MAJMIN"] = device
        existed_before = target.exists()
        before_names = sorted(path.relative_to(target).as_posix() for path in target.rglob("*")) if target.is_dir() else []
        result = subprocess.run([str(args.helper), system, str(base), str(target)], env=env,
                                text=True, capture_output=True)
        exists_after = target.exists()
        after_names = sorted(path.relative_to(target).as_posix() for path in target.rglob("*")) if target.is_dir() else []
        unchanged = existed_before == exists_after and before_names == after_names
        passed = result.returncode == expected and unchanged
        rows.append({"name": name, "system": system, "target": str(target), "capability": values,
                     "expected_exit": expected, "actual_exit": result.returncode,
                     "existed_before": existed_before, "exists_after": exists_after,
                     "target_unchanged": unchanged, "stdout": result.stdout.strip(),
                     "stderr": result.stderr.strip(), "passed": passed})

    run("dgai_exact_positive", "DGAI", args.dgai_base, dgai, 0)
    run("odin_exact_positive", "OdinANN", args.odin_base, odin, 0)
    run("cross_system_target", "OdinANN", args.odin_base, odin, 2,
        capability_target=dgai, capability_system="DGAI")
    run("wrong_system_metadata", "DGAI", args.dgai_base, dgai, 2, capability_system="OdinANN")
    run("wrong_target_metadata", "DGAI", args.dgai_base, dgai, 2, capability_target=odin)
    run("other_run_target", "DGAI", args.dgai_base, root / "formal/pilot3_sift10m_w1_r99/DGAI" / args.attempt, 2)
    run("other_attempt_target", "DGAI", args.dgai_base, formal / "DGAI/cp01-99", 2)
    run("wrong_run_metadata", "DGAI", args.dgai_base, dgai, 2, capability_run="pilot3_sift10m_w1_r99")
    run("wrong_attempt_metadata", "DGAI", args.dgai_base, dgai, 2, capability_attempt="cp01-99")
    run("forbidden_cp01_02", "DGAI", args.dgai_base, formal / "DGAI/cp01-02", 2)
    run("forbidden_cp01_03", "DGAI", args.dgai_base, formal / "DGAI/cp01-03", 2)
    run("missing_target", "DGAI", args.dgai_base, dgai, 2, capability_target=None)
    run("missing_system", "DGAI", args.dgai_base, dgai, 2, capability_system=None)
    run("missing_run", "DGAI", args.dgai_base, dgai, 2, capability_run=None)
    run("missing_attempt", "DGAI", args.dgai_base, dgai, 2, capability_attempt=None)
    run("wrong_device", "DGAI", args.dgai_base, dgai, 1, device="0:0")

    dgai.mkdir(parents=True)
    try:
        run("existing_target", "DGAI", args.dgai_base, dgai, 1)
    finally:
        shutil.rmtree(formal)

    escape = args.scratch / "escape_root"
    (escape / "DGAI").mkdir(parents=True)
    formal.symlink_to(escape, target_is_directory=True)
    try:
        run("symlink_escape", "DGAI", args.dgai_base, formal / "DGAI" / args.attempt, 2)
    finally:
        formal.unlink(missing_ok=True)

    if formal.exists() or dgai.exists() or odin.exists():
        raise SystemExit("clone tests left an R04 formal target")
    passed = all(row["passed"] for row in rows)
    report = {"schema": f"dynamic-vamana-w1-{label}-clone-capability-tests-v1",
              "status": "pass" if passed else "fail", "preflight_only": True,
              "tests": rows, "positive_tests": 2, "negative_tests": len(rows) - 2,
              "all_targets_unchanged": all(row["target_unchanged"] for row in rows),
              "formal_target_absent_after_tests": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    shutil.rmtree(args.scratch)
    if not passed:
        raise SystemExit("R04 clone capability tests failed")


if __name__ == "__main__":
    main()
