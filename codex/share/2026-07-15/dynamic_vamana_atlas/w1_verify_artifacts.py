#!/usr/bin/env python3
"""Fail-closed verification of frozen W1 binaries and OdinANN io_uring identity."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--system", choices=("DGAI", "OdinANN"), required=True)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--query-binary", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    entry = manifest["systems"][args.system]
    paths = {
        "w1_canary": args.driver.resolve(),
        "search_disk_index": args.query_binary.resolve(),
    }
    checks: dict[str, object] = {}
    for name, path in paths.items():
        expected_path = Path(entry["canonical_install"][name]).resolve()
        expected_hash = entry["binary_sha256"][name]
        actual_hash = digest(path)
        checks[f"{name}_realpath"] = str(path)
        checks[f"{name}_sha256"] = actual_hash
        checks[f"{name}_path_match"] = path == expected_path
        checks[f"{name}_hash_match"] = actual_hash == expected_hash
        if path != expected_path or actual_hash != expected_hash:
            raise SystemExit(f"frozen {args.system} {name} identity mismatch")

    ldd = subprocess.run(
        ["ldd", str(paths["w1_canary"])], check=True, text=True, capture_output=True
    ).stdout
    checks["w1_canary_ldd"] = ldd.splitlines()
    if args.system == "OdinANN":
        compile_commands = Path(entry["identity_evidence"]["compile_commands"]).read_text()
        cmake_log = Path(entry["identity_evidence"]["cmake_log"]).read_text()
        checks["io_engine"] = entry.get("io_engine")
        checks["cmake_reports_system_liburing"] = "Using system liburing" in cmake_log
        checks["compile_definition_use_uring"] = "-DUSE_URING" in compile_commands
        checks["ldd_has_liburing"] = "liburing" in ldd
        checks["ldd_has_libaio"] = "libaio" in ldd
        if not (
            entry.get("io_engine") == "uring"
            and checks["cmake_reports_system_liburing"]
            and checks["compile_definition_use_uring"]
            and checks["ldd_has_liburing"]
            and not checks["ldd_has_libaio"]
        ):
            raise SystemExit("OdinANN io_uring identity check failed")

    result = {
        "schema": "dynamic-vamana-w1-artifact-verification-v1",
        "system": args.system,
        "valid": True,
        "checks": checks,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
