#!/usr/bin/env python3
"""Re-hash preserved parent GT and CP01 to prove the R02 path did not mutate them."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""): h.update(block)
    return h.hexdigest()

def tree(root: Path) -> dict:
    h = hashlib.sha256(); count = total = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix(); size = path.stat().st_size
        h.update(f"{rel}\t{size}\t{sha(path)}\n".encode()); count += 1; total += size
    return {"realpath": str(root.resolve()), "manifest_sha256": h.hexdigest(), "file_count": count, "total_bytes": total}

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--preflight", type=Path, required=True)
    p.add_argument("--failed-gt", type=Path, required=True); p.add_argument("--cp01", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    if a.output.exists(): raise SystemExit("preservation report overwrite refused")
    before = json.loads(a.preflight.read_text()); gt = tree(a.failed_gt); cp01 = tree(a.cp01)
    metadata_exact = True
    for name, expected in before["preserved_cp01_artifacts"].items():
        stat = (a.cp01 / name).stat()
        metadata_exact &= stat.st_size == expected["size_bytes"] and stat.st_mtime_ns == expected["mtime_ns"]
    if gt != before["preserved_failed_gt"] or cp01 != before["preserved_cp01"] or not metadata_exact:
        raise SystemExit("a preserved parent artifact changed during R02")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps({"schema": "dynamic-vamana-w1-r02-preservation-audit-v1", "status": "pass",
        "failed_gt_unchanged": True, "cp01_content_unchanged": True, "cp01_size_mtime_unchanged": True,
        "failed_gt": gt, "cp01": cp01}, indent=2) + "\n")

if __name__ == "__main__": main()
