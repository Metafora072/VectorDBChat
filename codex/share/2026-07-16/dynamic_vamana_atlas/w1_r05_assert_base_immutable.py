#!/usr/bin/env python3
"""Fail closed unless an R05 system base retains exact content and metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--system", choices=("DGAI", "OdinANN"), required=True)
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--attempt", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise SystemExit("R05 base audit overwrite refused")
    expected_content = a.attempt / "base_content_before.tsv"
    expected_mode = a.attempt / "base_mode_before.tsv"
    if not expected_content.is_file() or not expected_mode.is_file():
        raise SystemExit("R05 attempt lacks frozen base manifests")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    current_content = a.output.with_suffix(".content.tsv")
    current_mode = a.output.with_suffix(".mode.tsv")
    old = Path(__file__).resolve().parents[2] / "2026-07-15/dynamic_vamana_atlas"
    subprocess.run(["python3", str(old / "w1_file_manifest.py"), "--root", str(a.base), "--output", str(current_content)], check=True)
    subprocess.run(["python3", str(Path(__file__).with_name("w1_mode_manifest.py")), "write", "--root", str(a.base), "--output", str(current_mode)], check=True)
    content_equal = current_content.read_bytes() == expected_content.read_bytes()
    mode_equal = current_mode.read_bytes() == expected_mode.read_bytes()
    report = {
        "schema": "dynamic-vamana-w1-r05-base-immutability-v1",
        "status": "pass" if content_equal and mode_equal else "fail",
        "system": a.system,
        "base_realpath": str(a.base.resolve()),
        "attempt_realpath": str(a.attempt.resolve()),
        "content_exact": content_equal,
        "mode_exact": mode_equal,
        "expected_content_sha256": sha(expected_content),
        "current_content_sha256": sha(current_content),
        "expected_mode_sha256": sha(expected_mode),
        "current_mode_sha256": sha(current_mode),
    }
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] != "pass":
        raise SystemExit(f"{a.system} immutable base audit failed")


if __name__ == "__main__":
    main()
