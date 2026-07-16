#!/usr/bin/env python3
"""Write and semantically compare no-follow ownership/mode manifests."""
from __future__ import annotations

import argparse
import csv
import os
import pwd
import stat
from pathlib import Path


FIELDS = ("relative_path", "type", "uid", "gid", "mode_octal", "inode", "link_count")


def walk(root: Path) -> list[dict[str, str]]:
    root = root.resolve(strict=True)
    rows: list[dict[str, str]] = []

    def visit(path: Path, relative: str) -> None:
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            kind = "directory"
        elif stat.S_ISREG(info.st_mode):
            kind = "regular"
        else:
            raise SystemExit(f"unsupported file type in mode manifest: {path}")
        rows.append({"relative_path": relative, "type": kind, "uid": str(info.st_uid),
                     "gid": str(info.st_gid), "mode_octal": f"{stat.S_IMODE(info.st_mode):04o}",
                     "inode": str(info.st_ino), "link_count": str(info.st_nlink)})
        if kind == "directory":
            with os.scandir(path) as entries:
                names = sorted(entry.name for entry in entries)
            for name in names:
                visit(path / name, name if relative == "." else f"{relative}/{name}")

    visit(root, ".")
    return rows


def write_manifest(root: Path, output: Path) -> None:
    if output.exists():
        raise SystemExit("mode manifest overwrite refused")
    rows = walk(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def load(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def compare(left: Path, right: Path, policy_only: bool) -> None:
    a, b = load(left), load(right)
    fields = ("relative_path", "type", "uid", "gid", "mode_octal", "link_count") if policy_only else FIELDS
    projected_a = [{key: row[key] for key in fields} for row in a]
    projected_b = [{key: row[key] for key in fields} for row in b]
    if projected_a != projected_b:
        raise SystemExit(f"mode manifest mismatch: {left} != {right}; policy_only={policy_only}")


def verify_private(path: Path, owner: str) -> None:
    account = pwd.getpwnam(owner)
    for row in load(path):
        expected_mode = "0700" if row["type"] == "directory" else "0600"
        if (row["uid"], row["gid"], row["mode_octal"]) != (str(account.pw_uid), str(account.pw_gid), expected_mode):
            raise SystemExit(f"private-tree policy mismatch: {row}")
        if row["type"] == "regular" and row["link_count"] != "1":
            raise SystemExit(f"private-tree hard-link risk: {row}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    write = sub.add_parser("write"); write.add_argument("--root", type=Path, required=True); write.add_argument("--output", type=Path, required=True)
    compare_parser = sub.add_parser("compare"); compare_parser.add_argument("--left", type=Path, required=True)
    compare_parser.add_argument("--right", type=Path, required=True); compare_parser.add_argument("--policy-only", action="store_true")
    verify = sub.add_parser("verify-private"); verify.add_argument("--manifest", type=Path, required=True); verify.add_argument("--owner", required=True)
    args = parser.parse_args()
    if args.command == "write": write_manifest(args.root, args.output)
    elif args.command == "compare": compare(args.left, args.right, args.policy_only)
    else: verify_private(args.manifest, args.owner)


if __name__ == "__main__":
    main()
