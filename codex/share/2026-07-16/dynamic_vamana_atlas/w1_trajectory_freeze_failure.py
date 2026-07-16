#!/usr/bin/env python3
"""Inventory and freeze every retained output after a fail-closed attempt."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(root: Path) -> list[dict]:
    rows = []
    if not root.exists():
        return rows
    for path in sorted([root] + list(root.rglob("*"))):
        st = path.lstat()
        row = {"relative_path": "." if path == root else path.relative_to(root).as_posix(),
               "mode_before_freeze": stat.S_IMODE(st.st_mode), "uid": st.st_uid, "gid": st.st_gid,
               "inode": st.st_ino, "device": st.st_dev}
        if path.is_symlink():
            row.update({"type": "symlink", "target": os.readlink(path)})
        elif path.is_file():
            row.update({"type": "file", "size_bytes": st.st_size, "allocated_bytes": st.st_blocks * 512,
                        "sha256": sha(path)})
        elif path.is_dir():
            row["type"] = "directory"
        else:
            row["type"] = "other"
        rows.append(row)
    return rows


def freeze(root: Path) -> None:
    if not root.exists():
        return
    paths = sorted([root] + list(root.rglob("*")), key=lambda path: len(path.parts), reverse=True)
    for path in paths:
        if not path.is_symlink():
            os.chmod(path, stat.S_IMODE(path.stat().st_mode) & ~0o222)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--groundtruth", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--controller-pid", type=int, required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise SystemExit("failed-output manifest overwrite refused")
    execution = json.loads(args.execution.read_text())
    expected_result = args.root.resolve() / "results/pilot3_sift10m_w1_trajectory_prep"
    expected_trajectory = args.root.resolve() / "datasets/sift10m/w1_trajectory"
    expected_groundtruth = args.root.resolve() / "groundtruth/sift10m/w1_trajectory"
    if (args.result.resolve() != expected_result or args.trajectory.resolve() != expected_trajectory
            or args.groundtruth.resolve() != expected_groundtruth or args.output.resolve().parent != expected_result
            or execution.get("controller_pid") != args.controller_pid
            or execution.get("experiment_root") != str(args.root.resolve())
            or execution.get("launcher_realpath") != str(args.launcher.resolve())
            or execution.get("launcher_sha256") != sha(args.launcher)
            or execution.get("status") not in {"preflighting", "running", "stopped_failed"}):
        raise SystemExit("failed-output freezer ownership/capability guard failed")
    report = {"schema": "dynamic-vamana-w1-trajectory-failed-output-v1", "status": "retained_frozen",
              "stopped_phase": args.phase, "exit_code": args.exit_code,
              "roots": {"trajectory": {"realpath": str(args.trajectory.resolve()), "artifacts": inventory(args.trajectory)},
                        "groundtruth": {"realpath": str(args.groundtruth.resolve()), "artifacts": inventory(args.groundtruth)}}}
    freeze(args.trajectory); freeze(args.groundtruth)
    for tree in report["roots"].values():
        tree["all_non_symlink_outputs_read_only"] = all(
            Path(tree["realpath"], row["relative_path"]).is_symlink()
            or not (Path(tree["realpath"], row["relative_path"]).stat().st_mode & 0o222)
            for row in tree["artifacts"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    freeze(args.result)


if __name__ == "__main__":
    main()
