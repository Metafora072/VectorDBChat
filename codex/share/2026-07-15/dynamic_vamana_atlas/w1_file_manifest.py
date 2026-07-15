#!/usr/bin/env python3
"""Write a deterministic content manifest: relative path, size, and SHA-256."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True); p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    root = a.root.resolve()
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rows.append(f"{path.relative_to(root)}\t{path.stat().st_size}\t{digest(path)}")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text("\n".join(rows) + ("\n" if rows else ""))

if __name__ == "__main__": main()
