#!/usr/bin/env python3
"""Create a fail-closed, page-granular Z0A initial-live manifest.

The manifest is taken from an already-created private pre-run clone.  It is not
valid for a source index that can change concurrently.  Every regular file in
the clone must occur in the system-specific allowlist; unknown, symlinked,
special, cross-device, or hard-linked objects abort the operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import BinaryIO, Iterable


SCHEMA = "zns-ann-z0a-initial-live-jsonl-v1"
PAGE_SIZE = 4096
DEFAULT_Z0A_ROOT = Path(
    "/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/"
    "z0a_trace_model_preflight_0719"
)

# This is deliberately an exact-name allowlist, not a suffix/pattern classifier.
# BUILD_OK is recorded as an object with zero live pages so the clone file set is
# still closed.  Shadow objects are allowed for runtime registries but must not be
# present in an initial OdinANN clone.
FILE_ROLES: dict[str, dict[str, str]] = {
    "DGAI": {
        "BUILD_OK": "control_marker",
        "disk_index_data": "long_lived_aux_vector_source",
        "disk_index_graph": "long_lived_aux_graph_source",
        "index_disk.index": "active_graph_vector",
        "index_disk.index.tags": "active_tags",
        "index_map.bin": "long_lived_aux_mapping",
        "index_pq_compressed.bin": "active_pq_vectors",
        "index_pq_compressed_2.bin": "long_lived_aux_pq_vectors",
        "index_pq_compressed_refined.bin": "long_lived_aux_pq_vectors_refined",
        "index_pq_pivots.bin": "active_pq_pivots",
        "index_pq_pivots_2.bin": "long_lived_aux_pq_pivots",
        "index_pq_pivots_refined.bin": "long_lived_aux_pq_pivots_refined",
        "reorder_map_data_2": "long_lived_aux_reorder_mapping",
        "reorder_map_graph_2": "long_lived_aux_reorder_mapping",
        "reordered_disk_index_graph_2": "long_lived_aux_reordered_graph",
    },
    "OdinANN": {
        "BUILD_OK": "control_marker",
        "index_disk.index": "active_graph_vector",
        "index_disk.index.tags": "active_tags",
        "index_pq_compressed.bin": "active_pq_vectors",
        "index_pq_pivots.bin": "active_pq_pivots",
        "index_shadow_disk.index": "shadow_graph_vector",
        "index_shadow_disk.index.tags": "shadow_tags",
        "index_shadow_pq_compressed.bin": "shadow_pq_vectors",
        "index_shadow_pq_pivots.bin": "shadow_pq_pivots",
    },
}

REQUIRED_INITIAL_FILES = {
    "DGAI": {
        "disk_index_data",
        "disk_index_graph",
        "index_disk.index",
        "index_disk.index.tags",
        "index_map.bin",
        "index_pq_compressed.bin",
        "index_pq_compressed_2.bin",
        "index_pq_compressed_refined.bin",
        "index_pq_pivots.bin",
        "index_pq_pivots_2.bin",
        "index_pq_pivots_refined.bin",
        "reorder_map_data_2",
        "reorder_map_graph_2",
        "reordered_disk_index_graph_2",
    },
    "OdinANN": {
        "index_disk.index",
        "index_disk.index.tags",
        "index_pq_compressed.bin",
        "index_pq_pivots.bin",
    },
}
OPTIONAL_INITIAL_FILES = {"BUILD_OK"}

INITIAL_FORBIDDEN_ROLES = {
    "shadow_graph_vector",
    "shadow_tags",
    "shadow_pq_vectors",
    "shadow_pq_pivots",
}


def parse_device(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+):(\d+)", value)
    if not match:
        raise argparse.ArgumentTypeError("device must be MAJOR:MINOR")
    return int(match.group(1)), int(match.group(2))


def device_of(stat_result: os.stat_result) -> tuple[int, int]:
    return os.major(stat_result.st_dev), os.minor(stat_result.st_dev)


def require_descendant(path: Path, root: Path, label: str) -> Path:
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    if resolved == resolved_root or resolved_root not in resolved.parents:
        raise ValueError(f"{label} is not a strict descendant of Z0A root: {resolved}")
    return resolved


def discover_objects(clone_root: Path, system: str, expected_device: tuple[int, int]) -> list[tuple[Path, str]]:
    allowlist = FILE_ROLES[system]
    objects: list[tuple[Path, str]] = []
    seen_names: set[str] = set()

    for directory, dirnames, filenames in os.walk(clone_root, followlinks=False):
        if dirnames:
            raise ValueError(f"nested directories are not allowed in the deployment image: {directory}: {dirnames}")
        for filename in sorted(filenames):
            path = Path(directory) / filename
            relative = path.relative_to(clone_root).as_posix()
            if relative != filename:
                raise ValueError(f"nested clone object is not allowlisted: {relative}")
            if filename not in allowlist:
                raise ValueError(f"unknown file role (fail closed): {filename}")
            if filename in seen_names:
                raise ValueError(f"duplicate deployment object name: {filename}")
            seen_names.add(filename)

            lst = path.lstat()
            if not os.path.isfile(path) or os.path.islink(path):
                raise ValueError(f"non-regular or symlink object rejected: {path}")
            if lst.st_nlink != 1:
                raise ValueError(f"hard-linked object rejected: {path} (nlink={lst.st_nlink})")
            if device_of(lst) != expected_device:
                raise ValueError(f"cross-device clone object rejected: {path}: {device_of(lst)}")
            role = allowlist[filename]
            if role in INITIAL_FORBIDDEN_ROLES:
                raise ValueError(f"pre-run clone already contains a shadow object: {filename}")
            objects.append((path, role))

    if not objects:
        raise ValueError("pre-run clone contains no regular files")
    required = REQUIRED_INITIAL_FILES[system]
    missing = required - seen_names
    extra = seen_names - required - OPTIONAL_INITIAL_FILES
    if missing or extra:
        raise ValueError(
            "initial deployment image does not match the frozen allowlist; "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )
    return sorted(objects, key=lambda item: item[0].name)


def stable_object_id(run_uuid: uuid.UUID, system: str, ordinal: int, st: os.stat_result) -> str:
    # The run UUID scopes a monotonically allocated object incarnation.  Device,
    # inode and ctime are retained as independently checked registry anchors, but
    # are deliberately not the logical identity itself (rename keeps identity;
    # inode reuse receives a new incarnation).
    del system, st
    return f"{run_uuid}:{ordinal}"


def hash_fd(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    while True:
        block = stream.read(8 * 1024 * 1024)
        if not block:
            return digest.hexdigest()
        digest.update(block)


def unchanged(before: os.stat_result, after: os.stat_result) -> bool:
    fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_uid", "st_gid", "st_size", "st_mtime_ns", "st_ctime_ns")
    return all(getattr(before, field) == getattr(after, field) for field in fields)


def emit_jsonl(
    output: Path,
    clone_root: Path,
    z0a_root: Path,
    system: str,
    run_uuid: uuid.UUID,
    expected_device: tuple[int, int],
    objects: Iterable[tuple[Path, str]],
) -> dict[str, int]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite manifest: {output}")
    if not output.parent.is_dir():
        raise ValueError(f"manifest parent must already exist: {output.parent}")
    require_descendant(output.parent, z0a_root, "manifest parent")
    if device_of(output.parent.stat()) != expected_device:
        raise ValueError(f"manifest parent is not on expected device {expected_device}: {output.parent}")

    partial = output.with_name(f".{output.name}.partial.{os.getpid()}")
    if partial.exists():
        raise FileExistsError(f"stale partial manifest exists: {partial}")

    object_count = 0
    page_count = 0
    logical_bytes = 0
    allocated_bytes = 0
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(partial, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", buffering=1024 * 1024) as out:
            header = {
                "record_type": "manifest_header",
                "schema": SCHEMA,
                "system": system,
                "run_id": str(run_uuid),
                "clone_root": str(clone_root),
                "logical_block_size": PAGE_SIZE,
                "initial_packing": "not_encoded; simulator must declare deterministic packing separately",
                "stable_object_identity": "run_uuid + run-local object incarnation; preserved across rename",
            }
            out.write(json.dumps(header, sort_keys=True, separators=(",", ":")) + "\n")

            for ordinal, (path, role) in enumerate(objects, 1):
                open_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                object_fd = os.open(path, open_flags)
                with os.fdopen(object_fd, "rb", buffering=0) as stream:
                    before = os.fstat(stream.fileno())
                    if device_of(before) != expected_device or before.st_nlink != 1:
                        raise ValueError(f"object identity changed before scan: {path}")
                    object_id = stable_object_id(run_uuid, system, ordinal, before)
                    sha256 = hash_fd(stream)
                    after = os.fstat(stream.fileno())
                    if not unchanged(before, after):
                        raise RuntimeError(f"pre-run clone changed during manifest scan: {path}")

                object_row = {
                    "record_type": "object",
                    "stable_object_id": object_id,
                    "object_incarnation": ordinal,
                    "system": system,
                    "run_id": str(run_uuid),
                    "relative_path": path.relative_to(clone_root).as_posix(),
                    "file_role": role,
                    "device_id": f"{expected_device[0]}:{expected_device[1]}",
                    "device_number": before.st_dev,
                    "inode": before.st_ino,
                    "ctime_ns": before.st_ctime_ns,
                    "size_bytes": before.st_size,
                    "allocated_bytes": before.st_blocks * 512,
                    "sha256": sha256,
                    "initial_live_pages": (before.st_size + PAGE_SIZE - 1) // PAGE_SIZE,
                }
                out.write(json.dumps(object_row, sort_keys=True, separators=(",", ":")) + "\n")
                object_count += 1
                logical_bytes += before.st_size
                allocated_bytes += before.st_blocks * 512

                for page_index, offset in enumerate(range(0, before.st_size, PAGE_SIZE)):
                    page_bytes = min(PAGE_SIZE, before.st_size - offset)
                    page_row = {
                        "record_type": "initial_live_page",
                        "stable_object_id": object_id,
                        "file_role": role,
                        "logical_page_key": f"{object_id}:{offset}",
                        "aligned_page_offset": offset,
                        "page_index": page_index,
                        "initial_version": 0,
                        "record_bytes": page_bytes,
                        "page_bytes": page_bytes,
                        "initial_live": True,
                    }
                    out.write(json.dumps(page_row, sort_keys=True, separators=(",", ":")) + "\n")
                    page_count += 1

            trailer = {
                "record_type": "manifest_trailer",
                "schema": SCHEMA,
                "status": "complete",
                "object_count": object_count,
                "page_count": page_count,
                "logical_bytes": logical_bytes,
                "allocated_bytes": allocated_bytes,
            }
            out.write(json.dumps(trailer, sort_keys=True, separators=(",", ":")) + "\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(partial, output)
        parent_fd = os.open(output.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except BaseException:
        try:
            partial.unlink()
        except FileNotFoundError:
            pass
        raise

    return {
        "object_count": object_count,
        "page_count": page_count,
        "logical_bytes": logical_bytes,
        "allocated_bytes": allocated_bytes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", required=True, choices=sorted(FILE_ROLES))
    parser.add_argument("--run-id", required=True, type=uuid.UUID)
    parser.add_argument("--clone-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--z0a-root", type=Path, default=DEFAULT_Z0A_ROOT)
    parser.add_argument("--expected-device", type=parse_device, default=parse_device("259:10"))
    args = parser.parse_args()

    if args.expected_device != (259, 10):
        test_root = str(args.z0a_root)
        if os.environ.get("Z0A_STORAGE_SELFTEST") != "1" or not test_root.startswith("/tmp/z0a-"):
            raise ValueError("non-production device override is allowed only for an explicit /tmp Z0A self-test")
    z0a_root = args.z0a_root.resolve(strict=True)
    if device_of(z0a_root.stat()) != args.expected_device:
        raise ValueError(f"Z0A root device mismatch: {device_of(z0a_root.stat())} != {args.expected_device}")
    clone_root = require_descendant(args.clone_root, z0a_root, "clone root")
    if not clone_root.is_dir():
        raise ValueError(f"clone root is not a directory: {clone_root}")
    objects = discover_objects(clone_root, args.system, args.expected_device)
    summary = emit_jsonl(
        args.output,
        clone_root,
        z0a_root,
        args.system,
        args.run_id,
        args.expected_device,
        objects,
    )
    print(json.dumps({"status": "pass", "schema": SCHEMA, "output": str(args.output.resolve()), **summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"initial_manifest: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
