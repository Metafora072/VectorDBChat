"""Canonical serialization, hashing, and preparation resource guards."""

from __future__ import annotations

import hashlib
import json
import os
import resource
import time
from pathlib import Path
from typing import Any, Iterable


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def write_jsonl(path: Path, rows: Iterable[Any]) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    digest = hashlib.sha256()
    with path.open("wb") as handle:
        for row in rows:
            encoded = canonical_json_bytes(row)
            handle.write(encoded)
            digest.update(encoded)
            count += 1
    return count, digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def directory_bytes(root: Path) -> int:
    total = 0
    for base, _, files in os.walk(root):
        for name in files:
            try:
                total += (Path(base) / name).stat().st_size
            except FileNotFoundError:
                pass
    return total


def mem_available_bytes() -> int:
    with Path("/proc/meminfo").open() as handle:
        for line in handle:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable is absent from /proc/meminfo")


def cgroup_memory_headroom_bytes() -> int | None:
    relative = None
    for line in Path("/proc/self/cgroup").read_text().splitlines():
        fields = line.split(":", 2)
        if len(fields) == 3 and fields[0] == "0":
            relative = fields[2].lstrip("/")
            break
    if relative is None:
        return None
    root = Path("/sys/fs/cgroup") / relative
    maximum = (root / "memory.max").read_text().strip()
    if maximum == "max":
        return None
    current = int((root / "memory.current").read_text().strip())
    return max(0, int(maximum) - current)


def _cpu_set(spec: str) -> set[int]:
    values: set[int] = set()
    for part in spec.split(","):
        bounds = part.split("-", 1)
        start = int(bounds[0])
        end = int(bounds[-1])
        values.update(range(start, end + 1))
    return values


class PreparationGuard:
    def __init__(self, root: Path, config: dict[str, Any], started: float | None = None):
        self.root = root
        self.cfg = config["resources"]
        self.started = time.monotonic() if started is None else started

    def check(self, stage: str) -> dict[str, Any]:
        roots = [self.root, *(Path(path) for path in self.cfg.get("accounted_external_roots", []))]
        storage_by_root = {str(path): directory_bytes(path) for path in roots}
        storage = sum(storage_by_root.values())
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        available = mem_available_bytes()
        cgroup_headroom = cgroup_memory_headroom_bytes()
        wall = (
            time.time() - float(self.cfg["stage_started_unix"])
            if "stage_started_unix" in self.cfg
            else time.monotonic() - self.started
        )
        affinity = sorted(os.sched_getaffinity(0))
        record = {
            "stage": stage,
            "storage_bytes": storage,
            "storage_by_root": storage_by_root,
            "peak_rss_bytes": rss,
            "mem_available_bytes": available,
            "cgroup_memory_headroom_bytes": cgroup_headroom,
            "cpu_affinity": affinity,
            "wall_seconds": wall,
        }
        if storage >= self.cfg["hard_storage_bytes"]:
            raise RuntimeError(f"hard storage gate exceeded: {record}")
        if rss >= self.cfg["hard_rss_bytes"]:
            raise RuntimeError(f"hard RSS gate exceeded: {record}")
        if available < self.cfg["min_mem_available_bytes"]:
            raise RuntimeError(f"host memory headroom gate failed: {record}")
        if (
            cgroup_headroom is not None
            and cgroup_headroom < self.cfg["min_cgroup_headroom_bytes"]
        ):
            raise RuntimeError(f"cgroup memory headroom gate failed: {record}")
        if set(affinity) != _cpu_set(self.cfg["cpu_ids"]):
            raise RuntimeError(f"CPU affinity gate failed: {record}")
        if wall >= self.cfg["hard_wall_seconds"]:
            raise RuntimeError(f"hard wall gate exceeded: {record}")
        return record
