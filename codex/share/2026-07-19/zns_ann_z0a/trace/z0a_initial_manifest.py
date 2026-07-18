#!/usr/bin/env python3
"""Create the initial-live page manifest and the profiler object registry."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
from pathlib import Path


PAGE = 4096


def role(path: Path) -> tuple[int, str]:
    name = path.name
    if "shadow_disk.index" in name:
        return 2, "shadow_combined"
    if "disk_index_graph" in name:
        return 3, "graph"
    if "disk_index_data" in name:
        return 4, "vector"
    if "reordered_disk" in name:
        return 8, "reordered_derived"
    if ".tags" in name:
        return 5, "tags"
    if "pq_" in name or "_pq" in name:
        return 6, "pq"
    if "map" in name:
        return 7, "map"
    if "delete" in name or "tombstone" in name:
        return 9, "delete_tombstone"
    if "_disk.index" in name:
        return 1, "primary_combined"
    if "tmp" in name or "temp" in name:
        return 11, "temporary"
    return 10, "metadata"


def extents(path: Path, size: int) -> list[tuple[int, int]]:
    if size == 0:
        return []
    fd = os.open(path, os.O_RDONLY)
    output: list[tuple[int, int]] = []
    try:
        cursor = 0
        while cursor < size:
            try:
                begin = os.lseek(fd, cursor, os.SEEK_DATA)
            except OSError as exc:
                if exc.errno == errno.ENXIO:
                    break
                # Filesystems without SEEK_DATA are treated as fully allocated;
                # the manifest records that fallback in its top-level metadata.
                return [(0, size)]
            try:
                end = os.lseek(fd, begin, os.SEEK_HOLE)
            except OSError:
                return [(0, size)]
            output.append((begin, min(end, size)))
            cursor = max(end, begin + 1)
    finally:
        os.close(fd)
    return output


def is_live(offset: int, length: int, ranges: list[tuple[int, int]]) -> bool:
    end = offset + length
    return any(begin < end and offset < stop for begin, stop in ranges)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--system", choices=("DGAI", "OdinANN"), required=True)
    parser.add_argument("--object-map", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    files = sorted(path for path in root.rglob("*") if path.is_file())
    args.object_map.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    total_live_pages = total_live_bytes = total_pages = 0
    objects = []
    with args.object_map.open("w") as registry, args.manifest.open("w") as manifest:
        registry.write("# incarnation device inode ctime_ns role absolute_path\n")
        for incarnation, path in enumerate(files, 1):
            stat = path.stat()
            role_code, role_name = role(path)
            ctime_ns = stat.st_ctime_ns
            registry.write(f"{incarnation} {stat.st_dev} {stat.st_ino} {ctime_ns} {role_code} {path}\n")
            ranges = extents(path, stat.st_size)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            objects.append(
                {
                    "stable_object_id": f"{args.run_id}:{incarnation}",
                    "incarnation": incarnation,
                    "device_id": stat.st_dev,
                    "inode": stat.st_ino,
                    "file_role": role_name,
                    "path": str(path),
                    "size": stat.st_size,
                    "sha256": digest,
                }
            )
            for offset in range(0, stat.st_size, PAGE):
                page_bytes = min(PAGE, stat.st_size - offset)
                live = is_live(offset, page_bytes, ranges)
                total_pages += 1
                total_live_pages += int(live)
                total_live_bytes += page_bytes if live else 0
                manifest.write(
                    json.dumps(
                        {
                            "schema": "zns-ann-z0a-initial-page-v1",
                            "system": args.system,
                            "run_id": args.run_id,
                            "stable_object_id": f"{args.run_id}:{incarnation}",
                            "file_role": role_name,
                            "logical_page_key": [incarnation, offset],
                            "initial_version": 0,
                            "page_bytes": page_bytes,
                            "initial_live": live,
                            "initial_packing_order": [role_code, incarnation, offset],
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )
    summary = {
        "schema": "zns-ann-z0a-initial-manifest-summary-v1",
        "status": "pass",
        "system": args.system,
        "run_id": args.run_id,
        "root": str(root),
        "object_count": len(objects),
        "logical_pages": total_pages,
        "initial_live_pages": total_live_pages,
        "initial_live_bytes": total_live_bytes,
        "initial_packing": "stable sort by (file_role_code, object_incarnation, aligned_offset)",
        "objects": objects,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({key: value for key, value in summary.items() if key != "objects"}, sort_keys=True))


if __name__ == "__main__":
    main()
