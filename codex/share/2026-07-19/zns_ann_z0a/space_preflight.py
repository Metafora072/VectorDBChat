#!/usr/bin/env python3
"""Fail-closed Z0A disk/RAM budget and target-device preflight."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


GIB = 1024**3
MIB = 1024**2
DEFAULT_Z0A_ROOT = Path(
    "/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/"
    "z0a_trace_model_preflight_0719"
)
DEFAULT_ALLOWED_PREFIX = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas")

# Conservative, sequential-run budget from the accepted immutable 1M bases.
DEFAULT_DISK_ITEMS = {
    "base_index_snapshot": int(2.11 * GIB),
    "active_mutable_clone_shadow": int(1.60 * GIB),
    "trace_binary": int(0.75 * GIB),
    "initial_manifest": int(0.75 * GIB),
    "normalized_event_file": int(1.50 * GIB),
    "simulator_state": int(0.25 * GIB),
    "simulator_output": int(0.75 * GIB),
    "temporary_compression": int(1.50 * GIB),
    "failure_residue": int(4.00 * GIB),
    "safety_margin": int(3.00 * GIB),
}
DEFAULT_RAM_ITEMS = {
    "application_peak": 4 * GIB,
    "trace_ram_buffer": 256 * MIB,
    "normalizer_simulator": 1 * GIB,
    "ram_safety_margin": 2 * GIB,
}
REQUIRED_DISK_ITEMS = set(DEFAULT_DISK_ITEMS)
REQUIRED_RAM_ITEMS = set(DEFAULT_RAM_ITEMS)


def parse_device(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+):(\d+)", value)
    if not match:
        raise argparse.ArgumentTypeError("device must be MAJOR:MINOR")
    return int(match.group(1)), int(match.group(2))


def parse_bytes(value: str) -> int:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(B|KiB|MiB|GiB|TiB)?", value)
    if not match:
        raise argparse.ArgumentTypeError(f"invalid byte quantity: {value}")
    number = float(match.group(1))
    unit = match.group(2) or "B"
    scale = {"B": 1, "KiB": 1024, "MiB": MIB, "GiB": GIB, "TiB": 1024**4}[unit]
    result = int(number * scale)
    if result < 0:
        raise argparse.ArgumentTypeError("byte quantity must be nonnegative")
    return result


def parse_item(value: str) -> tuple[str, int]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("item must be NAME=BYTES")
    name, amount = value.split("=", 1)
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise argparse.ArgumentTypeError(f"invalid item name: {name}")
    return name, parse_bytes(amount)


def items_or_default(values: list[tuple[str, int]] | None, defaults: dict[str, int], required: set[str]) -> dict[str, int]:
    if not values:
        return defaults.copy()
    result: dict[str, int] = {}
    for name, amount in values:
        if name in result:
            raise ValueError(f"duplicate budget item: {name}")
        result[name] = amount
    missing = required - result.keys()
    extra = result.keys() - required
    if missing or extra:
        raise ValueError(f"budget item schema mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    return result


def mem_available_bytes() -> int:
    with Path("/proc/meminfo").open(encoding="ascii") as stream:
        for line in stream:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable absent from /proc/meminfo")


def strict_target(target: Path, allowed_prefix: Path, expected_device: tuple[int, int]) -> Path:
    allowed = allowed_prefix.resolve(strict=True)
    resolved = target.resolve(strict=True)
    if resolved == allowed or allowed not in resolved.parents:
        raise ValueError(f"target is not a strict descendant of allowed prefix: {resolved}")
    actual = (os.major(resolved.stat().st_dev), os.minor(resolved.stat().st_dev))
    if actual != expected_device:
        raise ValueError(f"target device mismatch: {actual[0]}:{actual[1]} != {expected_device[0]}:{expected_device[1]}")
    return resolved


def atomic_json(path: Path, payload: dict[str, object], root: Path) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite preflight report: {path}")
    if not path.parent.is_dir():
        raise ValueError(f"preflight report parent must already exist: {path.parent}")
    parent = path.parent.resolve(strict=True)
    if parent != root and root not in parent.parents:
        raise ValueError(f"report path escapes target root: {path}")
    partial = path.with_name(f".{path.name}.partial.{os.getpid()}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(partial, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(partial, path)
    except BaseException:
        try:
            partial.unlink()
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-root", type=Path, default=DEFAULT_Z0A_ROOT)
    parser.add_argument("--allowed-prefix", type=Path, default=DEFAULT_ALLOWED_PREFIX)
    parser.add_argument("--expected-device", type=parse_device, default=parse_device("259:10"))
    parser.add_argument("--multiplier", type=float, default=1.5)
    parser.add_argument("--disk-item", action="append", type=parse_item)
    parser.add_argument("--ram-item", action="append", type=parse_item)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.multiplier < 1.5:
        raise ValueError("safety multiplier below the gate minimum 1.5")
    if args.expected_device != (259, 10):
        test_root = str(args.target_root)
        if os.environ.get("Z0A_STORAGE_SELFTEST") != "1" or not test_root.startswith("/tmp/z0a-"):
            raise ValueError("non-production device override is allowed only for an explicit /tmp Z0A self-test")
    target = strict_target(args.target_root, args.allowed_prefix, args.expected_device)
    disk_items = items_or_default(args.disk_item, DEFAULT_DISK_ITEMS, REQUIRED_DISK_ITEMS)
    ram_items = items_or_default(args.ram_item, DEFAULT_RAM_ITEMS, REQUIRED_RAM_ITEMS)
    disk_peak = sum(disk_items.values())
    ram_peak = sum(ram_items.values())
    required_free = int(disk_peak * args.multiplier)
    required_ram = int(ram_peak * args.multiplier)
    statvfs = os.statvfs(target)
    free_bytes = statvfs.f_bavail * statvfs.f_frsize
    available_ram = mem_available_bytes()
    disk_pass = free_bytes > required_free
    ram_pass = available_ram > required_ram
    payload: dict[str, object] = {
        "schema": "zns-ann-z0a-space-preflight-v1",
        "status": "pass" if disk_pass and ram_pass else "fail",
        "target_root": str(target),
        "device_id": f"{args.expected_device[0]}:{args.expected_device[1]}",
        "safety_multiplier": args.multiplier,
        "disk": {
            "items": disk_items,
            "estimated_peak_bytes": disk_peak,
            "required_free_bytes_strictly_greater_than": required_free,
            "free_bytes": free_bytes,
            "pass": disk_pass,
        },
        "ram": {
            "items": ram_items,
            "estimated_peak_bytes": ram_peak,
            "required_available_bytes_strictly_greater_than": required_ram,
            "mem_available_bytes": available_ram,
            "pass": ram_pass,
        },
    }
    if args.output:
        atomic_json(args.output, payload, target)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "pass" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"space_preflight: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
