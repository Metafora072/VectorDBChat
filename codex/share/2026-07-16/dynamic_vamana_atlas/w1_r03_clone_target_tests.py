#!/usr/bin/env python3
"""Exercise R03 exact clone-target capability without cloning or creating attempts."""
from __future__ import annotations
import argparse, json, os, shutil, subprocess
from pathlib import Path

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True)
    p.add_argument("--helper", type=Path, required=True); p.add_argument("--dgai-base", type=Path, required=True)
    p.add_argument("--odin-base", type=Path, required=True); p.add_argument("--scratch", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    root = a.root.resolve(); formal = root / "formal/pilot3_sift10m_w1_r03"
    if a.output.exists() or formal.exists() or a.scratch.exists(): raise SystemExit("clone target test freshness guard failed")
    dgai = formal / "DGAI/cp01-03"; odin = formal / "OdinANN/cp01-03"
    a.scratch.mkdir(parents=True)
    common = os.environ.copy(); common.update({"W1_FORMAL_PATH_AUTHORIZED": "1", "W1_CLONE_PREFLIGHT_ONLY": "1",
                                               "ATLAS_ROOT": str(root), "ATLAS_NVME_MAJMIN": os.environ.get("ATLAS_NVME_MAJMIN", "259:10")})
    rows = []
    def run(name: str, system: str, base: Path, target: Path, capability: Path | None, expected: int) -> None:
        env = common.copy()
        if capability is None: env.pop("W1_ALLOWED_CLONE_TARGET", None)
        else: env["W1_ALLOWED_CLONE_TARGET"] = str(capability)
        result = subprocess.run([str(a.helper), system, str(base), str(target)], env=env, text=True, capture_output=True)
        target_created = target.exists(); passed = (result.returncode == expected and not target_created)
        rows.append({"name": name, "system": system, "target": str(target), "expected_exit": expected,
                     "actual_exit": result.returncode, "target_created": target_created,
                     "stdout": result.stdout.strip(), "stderr": result.stderr.strip(), "passed": passed})

    run("dgai_exact_positive", "DGAI", a.dgai_base, dgai, dgai, 0)
    run("odin_exact_positive", "OdinANN", a.odin_base, odin, odin, 0)
    run("dgai_capability_on_odin_target", "OdinANN", a.odin_base, odin, dgai, 2)
    run("odin_capability_on_dgai_target", "DGAI", a.dgai_base, dgai, odin, 2)
    run("wrong_system_component", "DGAI", a.dgai_base, odin, odin, 2)
    run("forbidden_cp01_02", "DGAI", a.dgai_base, formal / "DGAI/cp01-02", formal / "DGAI/cp01-02", 2)
    run("forbidden_cp01_04", "DGAI", a.dgai_base, formal / "DGAI/cp01-04", formal / "DGAI/cp01-04", 2)
    run("forbidden_arbitrary_path", "DGAI", a.dgai_base, root / "tmp/r03-arbitrary/cp01-03", root / "tmp/r03-arbitrary/cp01-03", 2)
    run("missing_capability", "DGAI", a.dgai_base, dgai, None, 2)
    escape = a.scratch / "escape_root"; (escape / "DGAI").mkdir(parents=True)
    formal.symlink_to(escape, target_is_directory=True)
    try: run("symlink_escape", "DGAI", a.dgai_base, formal / "DGAI/cp01-03", formal / "DGAI/cp01-03", 2)
    finally: formal.unlink(missing_ok=True)
    if formal.exists() or dgai.exists() or odin.exists(): raise SystemExit("clone tests left an R03 formal target")
    report = {"schema": "dynamic-vamana-w1-r03-clone-target-tests-v1", "status": "pass" if all(row["passed"] for row in rows) else "fail",
              "preflight_only": True, "tests": rows, "positive_tests": 2, "negative_tests": len(rows) - 2,
              "all_failures_before_target_creation": all(not row["target_created"] for row in rows), "formal_target_absent_after_tests": True}
    a.output.parent.mkdir(parents=True, exist_ok=True); a.output.write_text(json.dumps(report, indent=2) + "\n")
    shutil.rmtree(a.scratch)
    if report["status"] != "pass": raise SystemExit("R03 clone target tests failed")

if __name__ == "__main__": main()
