#!/usr/bin/env python3
"""Freeze the DiskANN ELF loader environment without executing query code."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

EXPECTED_BINARY_SHA = "631fc53b4514fdac8325a7d789792ff6d19fb007e5442410898ec4a9505d4c3e"
EXPECTED_TCMALLOC_SHA = "9035515aa26ebfaa2cf390291378e0ccba66175ba8291b92aa32e92f97a8b904"
EXPECTED_TCMALLOC = "libtcmalloc.so.9.9.5"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, env=env, text=True, capture_output=True, check=False)


def parse_interpreter(text: str) -> str:
    match = re.search(r"Requesting program interpreter:\s*([^\]]+)\]", text)
    if not match:
        raise SystemExit("ELF interpreter absent")
    return match.group(1).strip()


def parse_needed(text: str) -> list[str]:
    return re.findall(r"\(NEEDED\).*Shared library:\s*\[([^\]]+)\]", text)


def parse_ldd(text: str) -> dict[str, str | None]:
    rows: dict[str, str | None] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("linux-vdso"):
            continue
        missing = re.match(r"(\S+)\s+=>\s+not found$", line)
        if missing:
            rows[missing.group(1)] = None
            continue
        mapped = re.match(r"(\S+)\s+=>\s+(\S+)\s+\(", line)
        if mapped:
            rows[mapped.group(1)] = mapped.group(2)
            continue
        direct = re.match(r"(/\S+)\s+\(", line)
        if direct:
            rows[Path(direct.group(1)).name] = direct.group(1)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--runtime-lib-dir", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("runtime manifest overwrite refused")
    root = args.root.resolve()
    binary = args.binary.resolve()
    if sha(binary) != EXPECTED_BINARY_SHA:
        raise SystemExit("DiskANN binary identity mismatch")
    directories = sorted({str(path.resolve(strict=True)) for path in args.runtime_lib_dir})
    if not directories or any(not Path(path).is_dir() for path in directories):
        raise SystemExit("runtime library directory invalid")
    runtime_path = ":".join(directories)
    clean_env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "LD_LIBRARY_PATH": runtime_path}
    program = run(["readelf", "-l", str(binary)], clean_env)
    dynamic = run(["readelf", "-d", str(binary)], clean_env)
    if program.returncode or dynamic.returncode:
        raise SystemExit("readelf failed")
    interpreter_lexical = parse_interpreter(program.stdout)
    interpreter = Path(interpreter_lexical).resolve(strict=True)
    needed = parse_needed(dynamic.stdout)
    if EXPECTED_TCMALLOC not in needed or not needed:
        raise SystemExit("required tcmalloc DT_NEEDED entry absent")
    loader_command = ["env", "-i", "PATH=/usr/bin:/bin", "LANG=C", "LC_ALL=C",
                      f"LD_LIBRARY_PATH={runtime_path}", "ldd", str(binary)]
    ldd = run(["ldd", str(binary)], clean_env)
    mappings = parse_ldd(ldd.stdout + "\n" + ldd.stderr)
    if ldd.returncode or "not found" in (ldd.stdout + ldd.stderr):
        raise SystemExit("loader dependency resolution failed")
    dependencies = []
    for name in needed:
        resolved_raw = mappings.get(name)
        if resolved_raw is None:
            raise SystemExit(f"unresolved DT_NEEDED dependency: {name}")
        resolved = Path(resolved_raw).resolve(strict=True)
        stat = resolved.stat()
        private = resolved.is_relative_to(root)
        row = {"name": name, "resolved_realpath": str(resolved), "size_bytes": stat.st_size,
               "experiment_private": private}
        if private:
            row["sha256"] = sha(resolved)
        dependencies.append(row)
    tcmalloc = next(row for row in dependencies if row["name"] == EXPECTED_TCMALLOC)
    expected_realpath = (root / "build/gperftools-install/lib" / EXPECTED_TCMALLOC).resolve(strict=True)
    if tcmalloc["resolved_realpath"] != str(expected_realpath) or tcmalloc.get("sha256") != EXPECTED_TCMALLOC_SHA:
        raise SystemExit("tcmalloc frozen identity mismatch")
    transitive = []
    for name, resolved_raw in sorted(mappings.items()):
        if resolved_raw is None:
            raise SystemExit(f"unresolved transitive dependency: {name}")
        resolved = Path(resolved_raw).resolve(strict=True)
        transitive.append({"name": name, "resolved_realpath": str(resolved), "size_bytes": resolved.stat().st_size,
                           "experiment_private": resolved.is_relative_to(root),
                           **({"sha256": sha(resolved)} if resolved.is_relative_to(root) else {})})
    report = {
        "schema": "dynamic-vamana-w1-diskann-runtime-manifest-v1",
        "status": "pass",
        "binary": {"realpath": str(binary), "size_bytes": binary.stat().st_size, "sha256": sha(binary)},
        "elf_interpreter": {"requested_path": interpreter_lexical, "resolved_realpath": str(interpreter),
                            "size_bytes": interpreter.stat().st_size, "sha256": sha(interpreter)},
        "dt_needed": needed,
        "dependencies": dependencies,
        "transitive_loader_mappings": transitive,
        "runtime_library_directories": directories,
        "runtime_library_path": runtime_path,
        "loader_command": loader_command,
        "loader_returncode": ldd.returncode,
        "loader_stdout": ldd.stdout,
        "loader_stderr": ldd.stderr,
        "not_found_dependencies": [],
        "caller_ld_library_path_ignored": os.environ.get("LD_LIBRARY_PATH") != runtime_path,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
