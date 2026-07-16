#!/usr/bin/env python3
"""Minimal R04 allowed/denied input canary executed as ubuntu."""
from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path


def fail(message: str) -> None:
    raise RuntimeError(message)


def open_read(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    os.close(descriptor)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allowed", type=Path, required=True)
    parser.add_argument("--denied", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if os.geteuid() != 1000 or os.getegid() != 1000:
        fail("input canary must run as ubuntu")
    allowed = args.allowed.resolve(strict=True)
    denied = [path.absolute() for path in args.denied]
    output = args.output.absolute()
    if output.name != "canary.json" or output.parent.name != "input_canary":
        fail("canary output must be stage-local input_canary/canary.json")
    if output.exists() or output.is_symlink() or output.parent.resolve(strict=True) != output.parent:
        fail("canary output capability is not fresh and exact")
    if (output.parent.stat().st_uid, output.parent.stat().st_gid,
            output.parent.stat().st_mode & 0o777) != (1000, 1000, 0o700):
        fail("canary evidence directory must be ubuntu:ubuntu/0700")
    open_read(allowed)
    rows = []
    for path in denied:
        if path == allowed:
            fail("allowed delta appears in denied set")
        try:
            open_read(path)
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EPERM):
                fail(f"denied path failed for the wrong reason: {path}: {exc.errno}")
            rows.append({"realpath": str(path), "open_refused": True, "errno": exc.errno})
        else:
            fail(f"denied input unexpectedly readable: {path}")
    payload = {
        "schema": "dynamic-vamana-w1-r04-input-canary-v1", "status": "pass",
        "uid": os.geteuid(), "gid": os.getegid(), "allowed_delta": str(allowed),
        "allowed_readable": True, "denied": rows, "update_worker_started": False,
    }
    with output.open("x") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"w1_input_canary: {exc}") from exc
