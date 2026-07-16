#!/usr/bin/env python3
"""Compare all protected CP05 cumulative inputs against preflight identities."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import stat
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def content_manifest(root: Path) -> bytes:
    root = root.resolve(strict=True)
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.is_symlink():
            raise ValueError(f"base content manifest refuses symlink: {path}")
        rows.append(f"{path.relative_to(root)}\t{path.stat().st_size}\t{sha256(path)}")
    return (("\n".join(rows) + "\n") if rows else "").encode()


def mode_manifest(root: Path) -> bytes:
    root = root.resolve(strict=True)
    rows: list[dict[str, str]] = []

    def visit(path: Path, relative: str) -> None:
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            kind = "directory"
        elif stat.S_ISREG(info.st_mode):
            kind = "regular"
        else:
            raise ValueError(f"unsupported base object: {path}")
        rows.append({"relative_path": relative, "type": kind, "uid": str(info.st_uid),
                     "gid": str(info.st_gid), "mode_octal": f"{stat.S_IMODE(info.st_mode):04o}",
                     "inode": str(info.st_ino), "link_count": str(info.st_nlink)})
        if kind == "directory":
            for name in sorted(entry.name for entry in os.scandir(path)):
                visit(path / name, name if relative == "." else f"{relative}/{name}")

    visit(root, ".")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream,
                            fieldnames=("relative_path", "type", "uid", "gid", "mode_octal", "inode", "link_count"),
                            delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("preservation output overwrite refused")
    preflight = json.loads(args.preflight.read_text())
    mismatches: list[dict[str, object]] = []
    checked: dict[str, dict[str, object]] = {}
    for name, expected in preflight["protected_artifacts"].items():
        path = Path(expected["realpath"])
        if not path.is_file():
            mismatches.append({"name": name, "reason": "missing", "path": str(path)})
            continue
        stat = path.stat()
        actual = {
            "realpath": str(path.resolve(strict=True)),
            "size_bytes": stat.st_size,
            "sha256": sha256(path),
            "mtime_ns": stat.st_mtime_ns,
            "mode": stat.st_mode & 0o7777,
            "uid": stat.st_uid,
            "gid": stat.st_gid,
            "device": stat.st_dev,
            "inode": stat.st_ino,
        }
        checked[name] = actual
        if actual != expected:
            mismatches.append({"name": name, "expected": expected, "actual": actual})
    base_lineage_checks: dict[str, dict[str, object]] = {}
    lineages = dict(preflight.get("dynamic_base_lineage", {}))
    diskann = preflight.get("diskann_lineage")
    if not isinstance(diskann, dict) or diskann.get("status") != "pass":
        mismatches.append({"name": "diskann_lineage", "reason": "missing_or_invalid"})
    for system, lineage in lineages.items():
        try:
            root = Path(lineage["base_root_realpath"]).resolve(strict=True)
            expected_content = lineage["live_content_manifest"]["sha256"]
            expected_mode = lineage["live_mode_manifest"]["sha256"]
            actual_content = hashlib.sha256(content_manifest(root)).hexdigest()
            actual_mode = hashlib.sha256(mode_manifest(root)).hexdigest()
            row = {"base_root_realpath": str(root), "content_sha256": actual_content,
                   "mode_sha256": actual_mode, "content_exact": actual_content == expected_content,
                   "mode_exact": actual_mode == expected_mode}
            base_lineage_checks[system] = row
            if not row["content_exact"] or not row["mode_exact"]:
                mismatches.append({"name": f"live_{system}_base", "expected_content": expected_content,
                                   "actual_content": actual_content, "expected_mode": expected_mode,
                                   "actual_mode": actual_mode})
        except (KeyError, OSError, ValueError) as exc:
            mismatches.append({"name": f"live_{system}_base", "reason": str(exc)})
    report = {
        "schema": "dynamic-vamana-w1-cp05-cumulative-preservation-v1",
        "status": "pass" if not mismatches else "fail",
        "checked_count": len(checked),
        "mismatches": mismatches,
        "artifacts": checked,
        "base_lineage_checks": base_lineage_checks,
        "diskann_lineage_present": isinstance(diskann, dict) and diskann.get("status") == "pass",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    if mismatches:
        raise SystemExit("protected CP05 cumulative input changed")


if __name__ == "__main__":
    main()
