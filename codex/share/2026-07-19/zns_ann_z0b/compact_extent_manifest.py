#!/usr/bin/env python3
"""Compact, sequence-only initial/final live-page manifests for Z0B.

``prepare`` scans a private pre-run clone once and emits an extent binary plus
the TSV object registry consumed by the endpoint tracer. ``close`` streams the
64-byte Z0BNORM1 records, merges them with namespace lifecycle events, and
emits the current live-page map as compact extents.  It never emits an expanded
per-page JSON/JSONL manifest or a payload image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np


PAGE = 4096
MAGIC = b"Z0BEXT1\0"
VERSION = 1
HEADER = struct.Struct("<8sIIIIQQQQQ")
OBJECT = struct.Struct("<QQQQQQHHI")
EXTENT = struct.Struct("<QQQQIIHHI")
PAGE_DIGEST_BYTES = 32
NORMAL_HEADER = struct.Struct("<8sIIQQ")
NORMAL_MAGIC = b"Z0BNORM1"
NORMAL_DTYPE = np.dtype([
    ("global_seq", "<u8"), ("request_id", "<u8"),
    ("object_incarnation", "<u8"), ("aligned_offset", "<u8"),
    ("update_id", "<u8"), ("batch_id", "<u8"),
    ("fragment_bytes", "<u4"), ("page_index", "<u4"),
    ("phase", "<u2"), ("role", "<u2"), ("source", "<u2"),
    ("reserved", "<u2"),
], align=False)

KIND_INITIAL = 0
KIND_WRITE = 1
KIND_ZERO = 2
FLAG_LIVE = 1
FLAG_INITIAL = 2


def fail(message: str) -> None:
    raise ValueError(message)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def padded_page_digests(path: Path, expected_size: int):
    """Yield SHA-256(valid bytes || zero padding) for each logical 4 KiB page."""
    before = path.stat()
    if before.st_size != expected_size:
        fail(f"object size changed before page hashing: {path}")
    with path.open("rb", buffering=0) as stream:
        remaining = expected_size
        while remaining:
            valid = min(PAGE, remaining)
            payload = stream.read(valid)
            if len(payload) != valid:
                fail(f"short object read while hashing pages: {path}")
            yield hashlib.sha256(payload + bytes(PAGE - valid)).digest()
            remaining -= valid
        if stream.read(1):
            fail(f"object grew while hashing pages: {path}")
    after = path.stat()
    for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns"):
        if getattr(before, key) != getattr(after, key):
            fail(f"object changed while hashing pages: {path}")


def fnv1a(text: str) -> int:
    value = 1469598103934665603
    for byte in text.encode():
        value ^= byte
        value = (value * 1099511628211) & ((1 << 64) - 1)
    return value


def role_for_name(name: str) -> int:
    if "shadow_disk.index" in name:
        return 2
    if "disk_index_graph" in name:
        return 3
    if "disk_index_data" in name:
        return 4
    if "reordered_disk" in name:
        return 8
    if ".tags" in name:
        return 5
    if "pq_" in name or "_pq" in name:
        return 6
    if "map" in name:
        return 7
    if "delete" in name or "tombstone" in name:
        return 9
    if "_disk.index" in name:
        return 1
    if "tmp" in name or "temp" in name:
        return 11
    return 10


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    if path.exists() or temporary.exists():
        fail(f"refusing output reuse: {path}")
    with temporary.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def atomic_binary(path: Path, writer) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    if path.exists() or temporary.exists():
        fail(f"refusing output reuse: {path}")
    with temporary.open("xb") as stream:
        writer(stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return sha256_path(path)


def root_files(root: Path) -> list[Path]:
    output = []
    for path in root.rglob("*"):
        if path.is_symlink() or (path.exists() and not path.is_file()):
            fail(f"non-regular object under index root: {path}")
        if path.is_file():
            output.append(path)
    return sorted(output, key=lambda item: item.relative_to(root).as_posix())


def prepare(args: argparse.Namespace) -> dict[str, object]:
    root = args.initial_root.resolve(strict=True)
    files = root_files(root)
    if not files:
        fail("initial root contains no files")
    objects = []
    total_pages = total_bytes = 0
    registry_tmp = args.object_map.with_name(f".{args.object_map.name}.tmp.{os.getpid()}")
    args.object_map.parent.mkdir(parents=True, exist_ok=True)
    if args.object_map.exists() or registry_tmp.exists():
        fail(f"refusing object-map reuse: {args.object_map}")
    with registry_tmp.open("x") as registry:
        registry.write("# incarnation device inode ctime_ns role absolute_path\n")
        for incarnation, path in enumerate(files, 1):
            relative = path.relative_to(root).as_posix()
            if "/" in relative:
                fail(f"nested initial index object rejected: {relative}")
            before = path.stat()
            if before.st_nlink != 1:
                fail(f"hard-linked initial object rejected: {path}")
            digest = sha256_path(path)
            after = path.stat()
            identity = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(before, key) != getattr(after, key) for key in identity):
                fail(f"initial object changed while hashing: {path}")
            role = role_for_name(path.name)
            pages = (before.st_size + PAGE - 1) // PAGE
            registry.write(f"{incarnation} {before.st_dev} {before.st_ino} {before.st_ctime_ns} {role} {path}\n")
            objects.append({
                "incarnation": incarnation,
                "stable_object_id": f"{args.run_id}:{incarnation}",
                "relative_path": relative,
                "path_hash": fnv1a(str(path)),
                "device_id": before.st_dev,
                "inode": before.st_ino,
                "ctime_ns": before.st_ctime_ns,
                "role": role,
                "size_bytes": before.st_size,
                "page_count": pages,
                "sha256": digest,
            })
            total_pages += pages
            total_bytes += before.st_size
        registry.flush()
        os.fsync(registry.fileno())
    os.replace(registry_tmp, args.object_map)

    def write_initial(stream) -> None:
        extent_count = sum(row["page_count"] > 0 for row in objects)
        stream.write(HEADER.pack(MAGIC, VERSION, HEADER.size, OBJECT.size, EXTENT.size,
                                 len(objects), extent_count, total_pages, total_bytes, fnv1a(args.run_id)))
        cursor = 0
        for row in objects:
            count = int(row["page_count"] > 0)
            stream.write(OBJECT.pack(row["incarnation"], row["path_hash"], row["size_bytes"], cursor,
                                     count, row["page_count"], row["role"], FLAG_LIVE | FLAG_INITIAL, 0))
            cursor += count
        for row in objects:
            if row["page_count"]:
                last = row["size_bytes"] - (row["page_count"] - 1) * PAGE
                stream.write(EXTENT.pack(row["incarnation"], 0, row["page_count"], 0, 0,
                                         last, row["role"], KIND_INITIAL, 0))
        for row in objects:
            path = root / row["relative_path"]
            for digest_bytes in padded_page_digests(path, row["size_bytes"]):
                stream.write(digest_bytes)

    digest = atomic_binary(args.output, write_initial)
    expected_objects = []
    cursor = 0
    for row in objects:
        count = int(row["page_count"] > 0)
        expected_objects.append((row["incarnation"], row["path_hash"], row["size_bytes"], cursor,
                                 count, row["page_count"], row["role"], FLAG_LIVE | FLAG_INITIAL, 0))
        cursor += count

    def initial_extents():
        for row in objects:
            if row["page_count"]:
                last = row["size_bytes"] - (row["page_count"] - 1) * PAGE
                yield (row["incarnation"], 0, row["page_count"], 0, 0,
                       last, row["role"], KIND_INITIAL, 0)

    initial_header = (len(objects), sum(row["page_count"] > 0 for row in objects),
                      total_pages, total_bytes, fnv1a(args.run_id))
    verify_extent_binary(args.output, initial_header, expected_objects, initial_extents,
                         [(root / row["relative_path"], row["size_bytes"]) for row in objects])
    summary = {
        "schema": "zns-ann-z0b-compact-initial-v1", "status": "pass",
        "run_id": args.run_id, "run_hash": fnv1a(args.run_id), "system": args.system,
        "logical_block_size": PAGE, "object_count": len(objects),
        "extent_count": sum(row["page_count"] > 0 for row in objects),
        "page_count": total_pages, "logical_bytes": total_bytes,
        "binary_sha256": digest, "representation": "one_initial_extent_per_nonempty_file",
        "page_digest_bytes": PAGE_DIGEST_BYTES,
        "page_digest_semantics": "sha256(valid_bytes || zero_pad_to_4096), ordered by (incarnation,aligned_offset)",
        "payload_image_bytes": 0, "expanded_page_manifest_bytes": 0,
        "objects": objects,
    }
    atomic_json(args.summary, summary)
    return {"status": "pass", "mode": "prepare", "objects": len(objects), "pages": total_pages}


def read_extent_header(path: Path) -> tuple[int, int, int, int, int]:
    with path.open("rb") as stream:
        raw = stream.read(HEADER.size)
    if len(raw) != HEADER.size:
        fail("short compact extent header")
    magic, version, header_bytes, object_bytes, extent_bytes, objects, extents, pages, logical, run_hash = HEADER.unpack(raw)
    if (magic, version, header_bytes, object_bytes, extent_bytes) != (MAGIC, VERSION, HEADER.size, OBJECT.size, EXTENT.size):
        fail("compact extent ABI mismatch")
    expected = HEADER.size + objects * OBJECT.size + extents * EXTENT.size + pages * PAGE_DIGEST_BYTES
    if path.stat().st_size != expected:
        fail("compact extent size/count closure")
    return objects, extents, pages, logical, run_hash


def verify_extent_binary(path: Path, expected_header: tuple[int, int, int, int, int],
                         object_records, extent_records, page_sources) -> None:
    """Independently stream-read every identity, extent, and content digest."""
    if read_extent_header(path) != expected_header:
        fail("compact extent header readback mismatch")
    with path.open("rb", buffering=0) as stream:
        stream.seek(HEADER.size)
        for expected in object_records:
            raw = stream.read(OBJECT.size)
            if len(raw) != OBJECT.size or OBJECT.unpack(raw) != tuple(expected):
                fail("compact object identity readback mismatch")
        for expected in extent_records():
            raw = stream.read(EXTENT.size)
            if len(raw) != EXTENT.size or EXTENT.unpack(raw) != tuple(expected):
                fail("compact current-page extent readback mismatch")
        page_count = 0
        for source, size in page_sources:
            for expected_digest in padded_page_digests(source, size):
                page_count += 1
                raw = stream.read(PAGE_DIGEST_BYTES)
                if raw != expected_digest:
                    fail(f"compact page-content digest readback mismatch: {source}")
        if page_count != expected_header[2] or stream.read(1):
            fail("compact page-content digest count/EOF mismatch")


def load_initial(map_path: Path, summary_path: Path) -> tuple[dict[str, object], dict[int, dict[str, object]]]:
    summary = json.loads(summary_path.read_text())
    if summary.get("schema") != "zns-ann-z0b-compact-initial-v1" or summary.get("status") != "pass":
        fail("initial summary schema/status mismatch")
    if (summary.get("logical_block_size") != PAGE or
            summary.get("page_digest_bytes") != PAGE_DIGEST_BYTES or
            summary.get("page_digest_semantics") !=
            "sha256(valid_bytes || zero_pad_to_4096), ordered by (incarnation,aligned_offset)"):
        fail("initial summary page/content ABI mismatch")
    if sha256_path(map_path) != summary.get("binary_sha256"):
        fail("initial map digest mismatch")
    counts = read_extent_header(map_path)
    expected = (int(summary["object_count"]), int(summary["extent_count"]),
                int(summary["page_count"]), int(summary["logical_bytes"]), int(summary["run_hash"]))
    if counts != expected:
        fail("initial binary/summary count mismatch")
    objects: dict[int, dict[str, object]] = {}
    ordered_rows = summary.get("objects", [])
    prior_incarnation = 0
    paths = set()
    for row in ordered_rows:
        incarnation = int(row["incarnation"])
        relative = str(row["relative_path"])
        size = int(row["size_bytes"])
        pages = int(row["page_count"])
        if (incarnation <= prior_incarnation or incarnation in objects or
                row["stable_object_id"] != f"{summary['run_id']}:{incarnation}" or
                not relative or "/" in relative or relative in paths or size < 0 or
                pages != (size + PAGE - 1) // PAGE or
                len(str(row.get("sha256", ""))) != 64):
            fail("invalid initial object identity")
        prior_incarnation = incarnation
        paths.add(relative)
        objects[incarnation] = row
    if len(objects) != expected[0]:
        fail("initial object-table count mismatch")
    if (sum(int(row["page_count"]) for row in ordered_rows) != expected[2] or
            sum(int(row["size_bytes"]) for row in ordered_rows) != expected[3] or
            sum(int(row["page_count"]) > 0 for row in ordered_rows) != expected[1]):
        fail("initial object-table aggregate mismatch")
    with map_path.open("rb", buffering=0) as stream:
        stream.seek(HEADER.size)
        cursor = 0
        for row in ordered_rows:
            count = int(int(row["page_count"]) > 0)
            expected_object = (int(row["incarnation"]), int(row["path_hash"]),
                               int(row["size_bytes"]), cursor, count, int(row["page_count"]),
                               int(row["role"]), FLAG_LIVE | FLAG_INITIAL, 0)
            raw = stream.read(OBJECT.size)
            if len(raw) != OBJECT.size or OBJECT.unpack(raw) != expected_object:
                fail("initial compact object identity mismatch")
            cursor += count
        for row in ordered_rows:
            if not int(row["page_count"]):
                continue
            last = int(row["size_bytes"]) - (int(row["page_count"]) - 1) * PAGE
            expected_extent = (int(row["incarnation"]), 0, int(row["page_count"]), 0, 0,
                               last, int(row["role"]), KIND_INITIAL, 0)
            raw = stream.read(EXTENT.size)
            if len(raw) != EXTENT.size or EXTENT.unpack(raw) != expected_extent:
                fail("initial compact extent identity mismatch")
    return summary, objects


def load_meta(path: Path, run_id: str, run_hash: int, final_root: Path) -> dict[int, dict[str, object]]:
    meta = json.loads(path.read_text())
    if (meta.get("schema") != "zns-ann-z0a-trace-meta-v1" or meta.get("status") != "complete" or
            meta.get("run_id") != run_id or int(meta.get("run_hash", -1)) != run_hash):
        fail("trace meta identity/status mismatch")
    if Path(str(meta.get("index_root"))).resolve(strict=True) != final_root:
        fail("trace meta index root differs from final root")
    if any(int(meta.get(key, -1)) != 0 for key in ("dropped_events", "identity_errors", "lifecycle_dropped_events")):
        fail("trace meta contains dropped/identity events")
    objects = {}
    for row in meta.get("objects", []):
        incarnation = int(row["incarnation"])
        if incarnation <= 0 or incarnation in objects or row.get("stable_object_id") != f"{run_id}:{incarnation}":
            fail("trace meta object identity collision")
        absolute = Path(str(row["path"])).absolute()
        try:
            relative = absolute.relative_to(final_root).as_posix()
        except ValueError:
            fail(f"trace object outside final root: {absolute}")
        row = dict(row)
        row["relative_path"] = relative
        computed_path_hash = fnv1a(str(absolute))
        if "path_hash" in row and int(row["path_hash"]) != computed_path_hash:
            fail(f"trace meta path hash mismatch: {absolute}")
        row["path_hash"] = computed_path_hash
        objects[incarnation] = row
    return objects


def load_lifecycle(path: Path, run_id: str, run_hash: int) -> list[dict[str, object]]:
    header = trailer = None
    events = []
    with path.open() as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            kind = row.get("record_type")
            if kind == "lifecycle_header":
                if header is not None:
                    fail("duplicate lifecycle header")
                header = row
            elif kind == "lifecycle_event":
                events.append(row)
            elif kind == "lifecycle_trailer":
                if trailer is not None:
                    fail("duplicate lifecycle trailer")
                trailer = row
            else:
                fail("unknown lifecycle record")
    if not header or not trailer or trailer.get("status") != "complete":
        fail("lifecycle header/trailer closure absent")
    if (header.get("schema") != "zns-ann-z0a-r2-lifecycle-v1" or header.get("run_id") != run_id or
            int(header.get("run_hash", -1)) != run_hash or int(header.get("dropped", -1)) != 0):
        fail("lifecycle identity/drop mismatch")
    if int(header.get("record_count", -1)) != len(events) or int(trailer.get("record_count", -1)) != len(events):
        fail("lifecycle count closure")
    events.sort(key=lambda row: int(row["global_seq"]))
    prior = 0
    for row in events:
        seq = int(row.get("global_seq", 0))
        source = int(row.get("source_entrypoint", 0))
        if seq <= prior or source not in (1, 2, 3, 4) or row.get("event_kind") != "TRUNCATE":
            fail("invalid lifecycle order/kind")
        if int(row.get("run_hash", -1)) != run_hash or int(row.get("status", -1)) != 0 or int(row.get("flags", 0)) & 3 != 3:
            fail("lifecycle success/identity closure")
        if int(row.get("old_size_bytes", -1)) < 0 or int(row.get("new_size_bytes", -1)) < 0:
            fail("negative lifecycle size")
        prior = seq
    return events


@dataclass
class ObjectState:
    incarnation: int
    meta: dict[str, object]
    initial: bool
    live: bool
    size_lo: int
    size_hi: int
    capacity_pages: int
    seq: np.memmap | None = None
    page_index: np.memmap | None = None
    kind: np.memmap | None = None


def validate_normalized(path: Path, temp: Path, lifecycle: list[dict[str, object]], meta: dict[int, dict[str, object]],
                        raw_count_expected: int, chunk: int) -> tuple[np.memmap, int, dict[int, int], int, int]:
    with path.open("rb") as stream:
        raw = stream.read(NORMAL_HEADER.size)
    if len(raw) != NORMAL_HEADER.size:
        fail("short normalized header")
    magic, version, record_bytes, count, raw_count = NORMAL_HEADER.unpack(raw)
    if (magic, version, record_bytes) != (NORMAL_MAGIC, 1, NORMAL_DTYPE.itemsize):
        fail("normalized ABI mismatch")
    if path.stat().st_size != NORMAL_HEADER.size + count * record_bytes or raw_count != raw_count_expected:
        fail("normalized size/raw-count closure")
    rows = (np.memmap(path, dtype=NORMAL_DTYPE, mode="r", offset=NORMAL_HEADER.size, shape=(count,))
            if count else np.empty(0, dtype=NORMAL_DTYPE))
    request_ids_path = temp / "request_ids.u64"
    with request_ids_path.open("wb") as stream:
        stream.truncate(raw_count * 8)
    request_ids = (np.memmap(request_ids_path, dtype="<u8", mode="r+", shape=(raw_count,))
                   if raw_count else np.empty(0, dtype="<u8"))
    groups = cursor = 0
    page_max: dict[int, int] = {}
    first_seq = last_seq = 0
    carry = None
    while cursor < count:
        end = min(count, cursor + chunk)
        part = np.asarray(rows[cursor:end])
        if np.any(part["global_seq"] == 0) or np.any(part["request_id"] == 0):
            fail("normalized nonpositive sequence/request identity")
        if np.any(part["aligned_offset"] % PAGE) or np.any(part["fragment_bytes"] == 0) or np.any(part["fragment_bytes"] > PAGE):
            fail("normalized alignment/fragment failure")
        if np.any(part["reserved"] != 0):
            fail("normalized reserved field is nonzero")
        for incarnation in np.unique(part["object_incarnation"]):
            value = int(incarnation)
            if value not in meta:
                fail(f"normalized references unknown object {value}")
            selected = part[part["object_incarnation"] == incarnation]
            if np.any(selected["role"] != int(meta[value]["initial_role"])):
                fail(f"normalized role mismatch for object {value}")
            page_max[value] = max(page_max.get(value, -1), int(selected["aligned_offset"].max()) // PAGE)
        previous = np.empty(part.size, dtype=bool)
        previous[0] = carry is None or int(part[0]["global_seq"]) != int(carry["global_seq"])
        if part.size > 1:
            previous[1:] = part["global_seq"][1:] != part["global_seq"][:-1]
        starts = np.flatnonzero(previous)
        if carry is not None and not previous[0]:
            same_fields = ("request_id", "object_incarnation", "update_id", "batch_id", "phase", "role", "source")
            if any(int(part[0][name]) != int(carry[name]) for name in same_fields):
                fail("cross-chunk request identity mismatch")
            if int(part[0]["page_index"]) != int(carry["page_index"]) + 1 or int(part[0]["aligned_offset"]) != int(carry["aligned_offset"]) + PAGE:
                fail("cross-chunk request page order mismatch")
        if groups + starts.size > raw_count:
            fail("normalized request groups exceed raw count")
        request_ids[groups:groups + starts.size] = part["request_id"][starts]
        groups += int(starts.size)
        if starts.size:
            if np.any(part["page_index"][starts] != 0):
                fail("request does not start at page index zero")
            group_seq = part["global_seq"][starts]
            if first_seq == 0:
                first_seq = int(group_seq[0])
            if last_seq and int(group_seq[0]) <= last_seq:
                fail("normalized global sequence is not strictly increasing")
            if group_seq.size > 1 and np.any(group_seq[1:] <= group_seq[:-1]):
                fail("normalized global sequence is not strictly increasing")
            last_seq = int(group_seq[-1])
        if part.size > 1:
            same = part["global_seq"][1:] == part["global_seq"][:-1]
            if np.any(np.where(same, part["page_index"][1:] != part["page_index"][:-1] + 1, False)):
                fail("request page-index order mismatch")
            if np.any(np.where(same, part["aligned_offset"][1:] != part["aligned_offset"][:-1] + PAGE, False)):
                fail("request aligned-offset order mismatch")
            for name in ("request_id", "object_incarnation", "update_id", "batch_id", "phase", "role", "source"):
                if np.any(np.where(same, part[name][1:] != part[name][:-1], False)):
                    fail(f"request {name} identity mismatch")
        carry = part[-1].copy()
        cursor = end
    if isinstance(request_ids, np.memmap):
        request_ids.flush()
    if groups != raw_count:
        fail(f"normalized request-group/raw-count mismatch: {groups} != {raw_count}")
    ids = request_ids[:groups]
    ids.sort(kind="quicksort")
    if groups and (ids[0] == 0 or np.any(ids[1:] == ids[:-1])):
        fail("request-id uniqueness closure")
    del request_ids
    lifecycle_seq = np.array([int(row["global_seq"]) for row in lifecycle], dtype=np.uint64)
    if lifecycle_seq.size:
        positions = np.searchsorted(rows["global_seq"], lifecycle_seq)
        collision = (positions < count) & (rows["global_seq"][np.minimum(positions, max(count - 1, 0))] == lifecycle_seq) if count else np.zeros(lifecycle_seq.size, bool)
        if np.any(collision):
            fail("write/lifecycle sequence collision")
    maximum = max(last_seq, int(lifecycle_seq[-1]) if lifecycle_seq.size else 0)
    minimum = min(first_seq or maximum, int(lifecycle_seq[0]) if lifecycle_seq.size else maximum)
    if (groups + len(lifecycle)) and (minimum != 1 or maximum != groups + len(lifecycle)):
        fail("write/lifecycle union is not gap-free 1..N")
    return rows, int(count), page_max, groups, maximum


def allocate_states(temp: Path, initial: dict[int, dict[str, object]], meta: dict[int, dict[str, object]],
                    page_max: dict[int, int], lifecycle: list[dict[str, object]]) -> dict[int, ObjectState]:
    capacity = {inc: (int(row["size_bytes"]) + PAGE - 1) // PAGE for inc, row in initial.items()}
    for inc, page in page_max.items():
        capacity[inc] = max(capacity.get(inc, 0), page + 1)
    for row in lifecycle:
        inc = int(row["object_incarnation"])
        capacity[inc] = max(capacity.get(inc, 0), (max(int(row["old_size_bytes"]), int(row["new_size_bytes"])) + PAGE - 1) // PAGE)
    states = {}
    for inc, row in meta.items():
        base = initial.get(inc)
        pages = capacity.get(inc, 0)
        state = ObjectState(inc, row, base is not None, base is not None,
                            int(base["size_bytes"]) if base else 0,
                            int(base["size_bytes"]) if base else 0, pages)
        if pages:
            state.seq = np.memmap(temp / f"o{inc}.seq", dtype="<u8", mode="w+", shape=(pages,))
            state.page_index = np.memmap(temp / f"o{inc}.pidx", dtype="<u4", mode="w+", shape=(pages,))
            state.kind = np.memmap(temp / f"o{inc}.kind", dtype="u1", mode="w+", shape=(pages,))
            state.kind[:] = KIND_ZERO
            if base:
                state.kind[:(int(base["size_bytes"]) + PAGE - 1) // PAGE] = KIND_INITIAL
        states[inc] = state
    return states


def apply_writes(rows: np.memmap, begin: int, end: int, states: dict[int, ObjectState], chunk: int) -> None:
    cursor = begin
    growth: dict[int, tuple[int, int]] = {}
    while cursor < end:
        upper = min(end, cursor + chunk)
        part = np.asarray(rows[cursor:upper])
        continuation = np.zeros(part.size, dtype=bool)
        if part.size > 1:
            continuation[:-1] = part["global_seq"][:-1] == part["global_seq"][1:]
        if upper < end and part.size:
            continuation[-1] = int(part[-1]["global_seq"]) == int(rows[upper]["global_seq"])
        for raw_inc in np.unique(part["object_incarnation"]):
            inc = int(raw_inc)
            state = states[inc]
            if not state.live:
                fail(f"write targets non-live object {inc}")
            positions = np.flatnonzero(part["object_incarnation"] == raw_inc)
            selected = part[positions]
            pages = (selected["aligned_offset"] // PAGE).astype(np.int64)
            reverse_unique = np.unique(pages[::-1], return_index=True)[1]
            chosen = positions[pages.size - 1 - reverse_unique]
            target_pages = (part["aligned_offset"][chosen] // PAGE).astype(np.int64)
            state.seq[target_pages] = part["global_seq"][chosen]
            state.page_index[target_pages] = part["page_index"][chosen]
            state.kind[target_pages] = KIND_WRITE
            definite = part["aligned_offset"][positions] + part["fragment_bytes"][positions].astype(np.uint64)
            definite = np.where(continuation[positions], part["aligned_offset"][positions] + PAGE, definite)
            lo = int(definite.max())
            singles = (~continuation[positions]) & (part["page_index"][positions] == 0)
            upper_end = part["aligned_offset"][positions] + np.where(
                continuation[positions] | singles, PAGE, part["fragment_bytes"][positions]
            ).astype(np.uint64)
            hi = int(upper_end.max())
            old = growth.get(inc, (state.size_lo, state.size_hi))
            growth[inc] = (max(old[0], lo), max(old[1], hi))
        cursor = upper
    for inc, (lo, hi) in growth.items():
        states[inc].size_lo, states[inc].size_hi = lo, hi


def apply_lifecycle(row: dict[str, object], states: dict[int, ObjectState]) -> None:
    inc = int(row["object_incarnation"])
    if inc not in states:
        fail(f"lifecycle references unknown object {inc}")
    state = states[inc]
    source = int(row["source_entrypoint"])
    seq = int(row["global_seq"])
    old = int(row["old_size_bytes"])
    new = int(row["new_size_bytes"])
    if source == 2:
        if state.live or old != 0 or new != 0 or bool(state.meta.get("initial")):
            fail(f"illegal CREATE for object {inc}")
        state.live = True
        state.size_lo = state.size_hi = 0
        return
    if not state.live or not (state.size_lo <= old <= state.size_hi):
        fail(f"lifecycle old-size/live mismatch for object {inc}: [{state.size_lo},{state.size_hi}] vs {old}")
    state.size_lo = state.size_hi = old
    if source == 3:
        if new != 0:
            fail("UNLINK new size must be zero")
        state.live = False
        state.size_lo = state.size_hi = 0
        return
    if source not in (1, 4) or (source == 4 and new != 0):
        fail("illegal namespace lifecycle source/size")
    old_pages = (old + PAGE - 1) // PAGE
    new_pages = (new + PAGE - 1) // PAGE
    if state.capacity_pages and new_pages > state.capacity_pages:
        fail("truncate exceeds preflighted object capacity")
    if state.capacity_pages and new_pages < old_pages:
        state.seq[new_pages:old_pages] = seq
        state.page_index[new_pages:old_pages] = 0
        state.kind[new_pages:old_pages] = KIND_ZERO
    elif state.capacity_pages and new_pages > old_pages:
        state.seq[old_pages:new_pages] = seq
        state.page_index[old_pages:new_pages] = 0
        state.kind[old_pages:new_pages] = KIND_ZERO
    state.size_lo = state.size_hi = new


def extent_rows(state: ObjectState, size: int):
    pages = (size + PAGE - 1) // PAGE
    if not pages:
        return
    seq = state.seq
    pidx = state.page_index
    kind = state.kind
    start = 0
    while start < pages:
        current_seq = int(seq[start])
        current_idx = int(pidx[start])
        current_kind = int(kind[start])
        stop = start + 1
        while stop < pages:
            if int(kind[stop]) != current_kind or int(seq[stop]) != current_seq:
                break
            if current_kind == KIND_WRITE and int(pidx[stop]) != current_idx + (stop - start):
                break
            stop += 1
        last_bytes = size - (pages - 1) * PAGE if stop == pages else PAGE
        yield (state.incarnation, start * PAGE, stop - start, current_seq, current_idx,
               last_bytes, int(state.meta["initial_role"]), current_kind, 0)
        start = stop


def close(args: argparse.Namespace) -> dict[str, object]:
    initial_summary, initial = load_initial(args.initial_map, args.initial_summary)
    run_id = str(initial_summary["run_id"])
    run_hash = int(initial_summary["run_hash"])
    final_root = args.final_root.resolve(strict=True)
    meta = load_meta(args.trace_meta, run_id, run_hash, final_root)
    for inc, row in initial.items():
        if inc not in meta or not bool(meta[inc].get("initial")):
            fail(f"initial object absent/noninitial in trace meta: {inc}")
        if (int(meta[inc]["initial_role"]) != int(row["role"]) or
                meta[inc]["relative_path"] != row["relative_path"] or
                int(meta[inc]["path_hash"]) != int(row["path_hash"]) or
                int(meta[inc]["device_id"]) != int(row["device_id"]) or
                int(meta[inc]["inode"]) != int(row["inode"]) or
                int(meta[inc]["ctime_ns"]) != int(row["ctime_ns"])):
            fail(f"initial object role/path mismatch: {inc}")
    lifecycle = load_lifecycle(args.lifecycle, run_id, run_hash)
    meta_json = json.loads(args.trace_meta.read_text())
    if (meta_json.get("system") != initial_summary.get("system") or
            int(meta_json.get("lifecycle_record_count", -1)) != len(lifecycle)):
        fail("trace meta system/lifecycle-count closure mismatch")
    create_counts = {inc: 0 for inc in meta}
    for event in lifecycle:
        inc = int(event["object_incarnation"])
        if inc not in meta:
            fail(f"lifecycle references unknown object {inc}")
        identity = meta[inc]
        if (int(event.get("file_role", -1)) != int(identity["initial_role"]) or
                int(event.get("path_hash", -1)) != int(identity["path_hash"]) or
                int(event.get("device_id", -1)) != int(identity["device_id"]) or
                int(event.get("inode", -1)) != int(identity["inode"])):
            fail(f"lifecycle object identity mismatch: {inc}")
        if int(event["source_entrypoint"]) == 2:
            create_counts[inc] += 1
    for inc, identity in meta.items():
        expected_creates = 0 if bool(identity.get("initial")) else 1
        if create_counts[inc] != expected_creates:
            fail(f"object CREATE/incarnation closure mismatch: {inc}")
    if args.temp_dir:
        args.temp_dir.mkdir(parents=True, exist_ok=True)
        workspace = Path(tempfile.mkdtemp(prefix="z0b-extents-", dir=args.temp_dir))
    else:
        workspace = Path(tempfile.mkdtemp(prefix="z0b-extents-"))
    try:
        rows, normalized_count, page_max, request_groups, maximum_seq = validate_normalized(
            args.normalized, workspace, lifecycle, meta, int(meta_json["record_count"]), args.chunk_records)
        states = allocate_states(workspace, initial, meta, page_max, lifecycle)
        cursor = 0
        for event in lifecycle:
            seq = int(event["global_seq"])
            boundary = int(np.searchsorted(rows["global_seq"], np.uint64(seq), side="left"))
            apply_writes(rows, cursor, boundary, states, args.chunk_records)
            apply_lifecycle(event, states)
            cursor = boundary
        apply_writes(rows, cursor, normalized_count, states, args.chunk_records)

        expected_paths = {}
        final_objects = []
        for inc in sorted(states):
            state = states[inc]
            if not state.live:
                continue
            relative = str(state.meta["relative_path"])
            if relative in expected_paths:
                fail(f"two live incarnations share final path: {relative}")
            path = final_root / relative
            if not path.is_file() or path.is_symlink():
                fail(f"live object absent/nonregular in final snapshot: {relative}")
            actual = path.stat().st_size
            if not (state.size_lo <= actual <= state.size_hi):
                fail(f"final size outside replay interval for {relative}: [{state.size_lo},{state.size_hi}] vs {actual}")
            state.size_lo = state.size_hi = actual
            expected_paths[relative] = inc
            final_objects.append((state, actual, sha256_path(path)))
        actual_paths = {path.relative_to(final_root).as_posix() for path in root_files(final_root)}
        if actual_paths != set(expected_paths):
            fail(f"final namespace mismatch: missing={sorted(set(expected_paths)-actual_paths)}, extra={sorted(actual_paths-set(expected_paths))}")

        object_descriptors = []
        extent_count = page_count = logical_bytes = 0
        for state, size, digest in final_objects:
            count = sum(1 for _ in extent_rows(state, size))
            pages = (size + PAGE - 1) // PAGE
            object_descriptors.append((state, size, digest, extent_count, count, pages))
            extent_count += count
            page_count += pages
            logical_bytes += size

        def write_final(stream) -> None:
            stream.write(HEADER.pack(MAGIC, VERSION, HEADER.size, OBJECT.size, EXTENT.size,
                                     len(object_descriptors), extent_count, page_count, logical_bytes, run_hash))
            for state, size, _digest, first, count, pages in object_descriptors:
                flags = FLAG_LIVE | (FLAG_INITIAL if state.initial else 0)
                stream.write(OBJECT.pack(state.incarnation, int(state.meta["path_hash"]), size, first,
                                         count, pages, int(state.meta["initial_role"]), flags, 0))
            for state, size, _digest, _first, _count, _pages in object_descriptors:
                for row in extent_rows(state, size):
                    stream.write(EXTENT.pack(*row))
            for state, size, _digest, _first, _count, _pages in object_descriptors:
                path = final_root / str(state.meta["relative_path"])
                for digest_bytes in padded_page_digests(path, size):
                    stream.write(digest_bytes)

        binary_digest = atomic_binary(args.output, write_final)
        expected_object_records = []
        for state, size, _digest, first, count, pages in object_descriptors:
            flags = FLAG_LIVE | (FLAG_INITIAL if state.initial else 0)
            expected_object_records.append((state.incarnation, int(state.meta["path_hash"]), size,
                                            first, count, pages, int(state.meta["initial_role"]), flags, 0))

        def final_extents():
            for state, size, _digest, _first, _count, _pages in object_descriptors:
                yield from extent_rows(state, size)

        final_header = (len(object_descriptors), extent_count, page_count, logical_bytes, run_hash)
        verify_extent_binary(
            args.output, final_header, expected_object_records, final_extents,
            [(final_root / str(state.meta["relative_path"]), size)
             for state, size, _digest, _first, _count, _pages in object_descriptors],
        )
        for state, size, digest, _first, _count, _pages in object_descriptors:
            if sha256_path(final_root / str(state.meta["relative_path"])) != digest:
                fail("final object changed across whole-file/page-digest closure")
        objects_json = [{
            "incarnation": state.incarnation,
            "stable_object_id": f"{run_id}:{state.incarnation}",
            "relative_path": str(state.meta["relative_path"]),
            "path_hash": int(state.meta["path_hash"]), "role": int(state.meta["initial_role"]),
            "initial": state.initial, "size_bytes": size, "page_count": pages,
            "first_extent": first, "extent_count": count, "sha256": digest,
        } for state, size, digest, first, count, pages in object_descriptors]
        summary = {
            "schema": "zns-ann-z0b-compact-final-closure-v1", "status": "pass",
            "run_id": run_id, "run_hash": run_hash, "system": initial_summary["system"],
            "sequence_only": True, "temporal_fields_consumed": False,
            "logical_block_size": PAGE, "normalized_record_bytes": NORMAL_DTYPE.itemsize,
            "normalized_page_event_count": normalized_count, "request_count": request_groups,
            "lifecycle_event_count": len(lifecycle), "global_sequence_max": maximum_seq,
            "object_count": len(objects_json), "extent_count": extent_count,
            "page_count": page_count, "logical_bytes": logical_bytes,
            "binary_sha256": binary_digest, "binary_extent_bytes": EXTENT.size,
            "page_digest_bytes": PAGE_DIGEST_BYTES,
            "page_digest_semantics": "sha256(valid_bytes || zero_pad_to_4096), ordered by (incarnation,aligned_offset)",
            "payload_image_bytes": 0, "expanded_page_manifest_bytes": 0,
            "checks": {
                "normalized_abi_and_size": True, "request_page_identity_and_order": True,
                "request_id_unique": True, "write_lifecycle_gap_free_sequence": True,
                "namespace_lifecycle_legal": True, "object_role_identity_closed": True,
                "final_namespace_equal": True, "final_sizes_equal": True,
                "final_file_hashes_recorded": True, "compact_binary_count_closed": True,
                "final_page_identity_and_content_closed": True,
            },
            "objects": objects_json,
            "content_limit": "write payloads are absent from trace; final snapshot binds each live page identity to a padded 4 KiB SHA-256 digest",
        }
        atomic_json(args.summary, summary)
        return {"status": "pass", "mode": "close", "requests": request_groups,
                "events": normalized_count, "objects": len(objects_json), "extents": extent_count,
                "pages": page_count}
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="mode", required=True)
    pre = sub.add_parser("prepare")
    pre.add_argument("--initial-root", type=Path, required=True)
    pre.add_argument("--run-id", required=True)
    pre.add_argument("--system", choices=("DGAI", "OdinANN"), required=True)
    pre.add_argument("--object-map", type=Path, required=True)
    pre.add_argument("--output", type=Path, required=True)
    pre.add_argument("--summary", type=Path, required=True)
    post = sub.add_parser("close")
    post.add_argument("--initial-map", type=Path, required=True)
    post.add_argument("--initial-summary", type=Path, required=True)
    post.add_argument("--normalized", type=Path, required=True)
    post.add_argument("--lifecycle", type=Path, required=True)
    post.add_argument("--trace-meta", type=Path, required=True)
    post.add_argument("--final-root", type=Path, required=True)
    post.add_argument("--output", type=Path, required=True)
    post.add_argument("--summary", type=Path, required=True)
    post.add_argument("--temp-dir", type=Path)
    post.add_argument("--chunk-records", type=int, default=1_000_000)
    return result


def main() -> int:
    args = parser().parse_args()
    if getattr(args, "chunk_records", 1) <= 0:
        fail("chunk-records must be positive")
    answer = prepare(args) if args.mode == "prepare" else close(args)
    print(json.dumps(answer, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"compact_extent_manifest: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
