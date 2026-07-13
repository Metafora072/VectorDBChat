#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(16 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    rows = []
    for path in sorted(x for x in args.root.rglob("*") if x.is_file()):
        rows.append({"path": str(path.relative_to(args.root)), "bytes": path.stat().st_size, "sha256": sha256(path)})
    args.output.write_text(json.dumps({"root": str(args.root), "files": rows}, indent=2) + "\n")


if __name__ == "__main__":
    main()
