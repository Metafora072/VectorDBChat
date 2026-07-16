#!/usr/bin/env python3
"""Final R03 proof that reused R02 GT and CP01 artifacts remained unchanged."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""): h.update(block)
    return h.hexdigest()

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--preflight", type=Path, required=True)
    p.add_argument("--cp01", type=Path, required=True); p.add_argument("--gt", type=Path, required=True)
    p.add_argument("--run-label", choices=("R03", "R04", "R05"), default="R03")
    p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    if a.output.exists(): raise SystemExit(f"{a.run_label} reuse preservation report overwrite refused")
    before = json.loads(a.preflight.read_text()); current = {}; mismatches = []
    expected_names = set(before["cp01_artifacts"])
    actual_names = {path.relative_to(a.cp01).as_posix() for path in a.cp01.rglob("*") if path.is_file()}
    if actual_names != expected_names: mismatches.append({"kind": "cp01_file_set", "expected": sorted(expected_names), "actual": sorted(actual_names)})
    for name, expected in before["cp01_artifacts"].items():
        path = a.cp01 / name
        if not path.is_file(): continue
        stat = path.stat(); row = {"size_bytes": stat.st_size, "sha256": sha(path), "mtime_ns": stat.st_mtime_ns}
        if row != expected: mismatches.append({"kind": "cp01_artifact", "name": name, "expected": expected, "actual": row})
        current[name] = row
    gt_sha = sha(a.gt) if a.gt.is_file() else None
    if gt_sha != before["r02_gt_sha256"]: mismatches.append({"kind": "r02_gt", "expected": before["r02_gt_sha256"], "actual": gt_sha})
    gt_mtime_ns = a.gt.stat().st_mtime_ns if a.gt.is_file() else None
    if before.get("r02_gt_mtime_ns") is not None and gt_mtime_ns != before["r02_gt_mtime_ns"]:
        mismatches.append({"kind": "r02_gt_mtime", "expected": before["r02_gt_mtime_ns"], "actual": gt_mtime_ns})
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps({"schema": f"dynamic-vamana-w1-{a.run_label.lower()}-reuse-preservation-v1",
        "status": "pass" if not mismatches else "fail", "cp01_unchanged": not any(row["kind"].startswith("cp01") for row in mismatches),
        "r02_gt_unchanged": not any(row["kind"].startswith("r02_gt") for row in mismatches), "r02_gt_sha256": gt_sha,
        "r02_gt_mtime_ns": gt_mtime_ns,
        "cp01_artifacts": current, "mismatches": mismatches}, indent=2) + "\n")
    if mismatches: raise SystemExit(f"{a.run_label} reused-input preservation failed")

if __name__ == "__main__": main()
