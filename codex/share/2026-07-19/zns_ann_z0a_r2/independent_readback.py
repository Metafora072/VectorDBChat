#!/usr/bin/env python3
"""Independent readback and short-trace materialization validator for Z0A-R2.

This program intentionally imports neither the packer nor either simulator.  It
re-parses the initial JSONL, physical map/image, raw trace ABI and normalized
page ABI.  Its fixed write materialization is one full 4096-byte page version
per normalized page event; sub-page replacements account for reconstruction
reads, while sub-page new pages account for zero fill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


BLOCK = 4096
RAW_HEADER = struct.Struct("<8sIIIIQQQQQ96s16s")
RAW_RECORD = struct.Struct("<QQQQQQQQQQQQQqqQQQIHHHH")
PAGE_HEADER = struct.Struct("<8sIIQ")
PAGE_RECORD = struct.Struct("<QQQQQII")


def c_string(value: bytes) -> str:
    return value.split(b"\0", 1)[0].decode("utf-8")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_initial(path: Path) -> tuple[dict[str, object], dict[str, dict[str, object]], dict[str, dict[str, object]], dict[str, object]]:
    header = None
    trailer = None
    objects: dict[str, dict[str, object]] = {}
    pages: dict[str, dict[str, object]] = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        kind = row.get("record_type")
        if kind == "manifest_header":
            if header is not None:
                raise ValueError("duplicate initial header")
            header = row
        elif kind == "object":
            key = str(row["stable_object_id"])
            if key in objects:
                raise ValueError(f"duplicate initial object: {key}")
            objects[key] = row
        elif kind == "initial_live_page":
            key = str(row["logical_page_key"])
            if key in pages or row.get("initial_live") is not True:
                raise ValueError(f"duplicate or non-live initial page: {key}")
            pages[key] = row
        elif kind == "manifest_trailer":
            if trailer is not None:
                raise ValueError("duplicate initial trailer")
            trailer = row
        else:
            raise ValueError(f"unknown initial record: {kind}")
    if not header or not trailer or trailer.get("status") != "complete":
        raise ValueError("initial header/trailer closure absent")
    if int(header.get("logical_block_size", 0)) != BLOCK:
        raise ValueError("initial manifest is not 4 KiB")
    if int(trailer["object_count"]) != len(objects) or int(trailer["page_count"]) != len(pages):
        raise ValueError("initial count closure failed")
    if sum(int(row["page_bytes"]) for row in pages.values()) != int(trailer["logical_bytes"]):
        raise ValueError("initial logical-byte closure failed")
    run_id = str(header["run_id"])
    for object_id, row in objects.items():
        if object_id != f"{run_id}:{int(row['object_incarnation'])}":
            raise ValueError(f"cross-run or malformed object identity: {object_id}")
    return header, objects, pages, trailer


def load_packing(path: Path) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    header = None
    trailer = None
    rows: list[dict[str, object]] = []
    for line in path.read_text().splitlines():
        row = json.loads(line)
        kind = row.get("record_type")
        if kind == "packing_header":
            if header is not None:
                raise ValueError("duplicate packing header")
            header = row
        elif kind == "packed_page":
            rows.append(row)
        elif kind == "packing_trailer":
            if trailer is not None:
                raise ValueError("duplicate packing trailer")
            trailer = row
        else:
            raise ValueError(f"unknown packing record: {kind}")
    if not header or not trailer or trailer.get("status") != "complete":
        raise ValueError("packing header/trailer closure absent")
    return header, rows, trailer


def validate_initial_snapshot(root: Path, objects: dict[str, dict[str, object]]) -> dict[str, Path]:
    expected = {str(row["relative_path"]) for row in objects.values()}
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if expected != actual:
        raise ValueError(f"initial snapshot file set mismatch: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")
    result: dict[str, Path] = {}
    for object_id, row in objects.items():
        source = (root / str(row["relative_path"])).resolve(strict=True)
        if root not in source.parents or source.is_symlink() or not source.is_file():
            raise ValueError(f"invalid initial snapshot object: {source}")
        if source.stat().st_size != int(row["size_bytes"]) or sha256_path(source) != row["sha256"]:
            raise ValueError(f"initial snapshot no longer matches pre-run manifest: {source}")
        result[object_id] = source
    return result


def validate_packing(
    manifest_header: dict[str, object],
    initial_pages: dict[str, dict[str, object]],
    packing_header: dict[str, object],
    packed: list[dict[str, object]],
    trailer: dict[str, object],
    image_path: Path,
    source_paths: dict[str, Path],
) -> tuple[dict[str, object], list[str]]:
    if packing_header["run_id"] != manifest_header["run_id"] or packing_header["system"] != manifest_header["system"]:
        raise ValueError("packing run/system identity mismatch")
    if packing_header.get("materialization_unit") != "full_4096_byte_logical_page_version":
        raise ValueError("packing does not use the fixed full-page materialization")
    config = packing_header["config"]
    zone_size = int(config["zone_size_bytes"])
    capacity = int(config["zone_capacity_bytes"])
    zone_count = int(config["number_of_zones"])
    spares = int(config["host_spare_zones"])
    if int(config["logical_block_size_bytes"]) != BLOCK or capacity % BLOCK or zone_size % BLOCK:
        raise ValueError("packing config is not 4 KiB aligned")
    if not 0 < capacity <= zone_size or not 1 <= spares < zone_count:
        raise ValueError("bad packing zone geometry")
    if image_path.stat().st_size != zone_count * zone_size:
        raise ValueError("physical image logical length mismatch")
    if len(packed) != len(initial_pages) or int(trailer["page_count"]) != len(packed):
        raise ValueError("packing page count mismatch")
    if len({str(row["page_key"]) for row in packed}) != len(packed):
        raise ValueError("physical map page-key collision")
    if {str(row["page_key"]) for row in packed} != set(initial_pages):
        raise ValueError("each initial-live page must appear exactly once")

    canonical = sorted(
        initial_pages.values(),
        key=lambda row: (str(row["file_role"]), str(row["stable_object_id"]), int(row["aligned_page_offset"])),
    )
    capacity_blocks = capacity // BLOCK
    ordinary = zone_count - spares
    logical_bytes = allocated = padding = 0
    ordered_keys: list[str] = []
    with image_path.open("rb") as image:
        for index, (expected, actual) in enumerate(zip(canonical, packed)):
            object_id = str(expected["stable_object_id"])
            offset = int(expected["aligned_page_offset"])
            page_bytes = int(expected["page_bytes"])
            zone_id = index // capacity_blocks
            zone_offset = (index % capacity_blocks) * BLOCK
            physical_offset = zone_id * zone_size + zone_offset
            expected_geometry = {
                "packing_index": index,
                "page_key": expected["logical_page_key"],
                "stable_object_id": object_id,
                "file_role": expected["file_role"],
                "aligned_page_offset": offset,
                "page_bytes": page_bytes,
                "allocated_append_bytes": BLOCK,
                "padding_bytes": BLOCK - page_bytes,
                "zone_id": zone_id,
                "zone_offset": zone_offset,
                "physical_image_offset": physical_offset,
                "initial_version": 0,
            }
            for field, value in expected_geometry.items():
                if actual.get(field) != value:
                    raise ValueError(f"noncanonical packing field {field} at index {index}")
            if zone_id >= ordinary or zone_offset + BLOCK > capacity:
                raise ValueError("initial page entered spare or exceeded zone capacity")
            image.seek(physical_offset)
            payload = image.read(BLOCK)
            if len(payload) != BLOCK or hashlib.sha256(payload).hexdigest() != actual["payload_sha256"]:
                raise ValueError(f"physical image/map payload mismatch at index {index}")
            with source_paths[object_id].open("rb") as source:
                source.seek(offset)
                source_bytes = source.read(page_bytes)
            if payload != source_bytes + bytes(BLOCK - page_bytes):
                raise ValueError(f"physical image is not a readback of the pre-run snapshot: {actual['page_key']}")
            logical_bytes += page_bytes
            allocated += BLOCK
            padding += BLOCK - page_bytes
            ordered_keys.append(str(actual["page_key"]))
    used_zones = (len(packed) + capacity_blocks - 1) // capacity_blocks
    if used_zones > int(config["max_active_zones"]):
        raise ValueError("initial active-zone constraint violated")
    if int(trailer["initial_open_zone_count"]) != 0 or int(trailer["initial_active_zone_count"]) != used_zones:
        raise ValueError("initial open/active counts do not close")
    if list(trailer["host_spare_zone_ids"]) != list(range(ordinary, zone_count)):
        raise ValueError("host spare zone set mismatch")
    if int(trailer["logical_page_bytes"]) != logical_bytes or int(trailer["initial_allocated_append_bytes"]) != allocated:
        raise ValueError("initial physical byte account does not close")
    if int(trailer["padding_bytes"]) != padding:
        raise ValueError("initial padding byte account does not close")
    return config, ordered_keys


@dataclass(frozen=True)
class Raw:
    request_id: int
    submit_seq: int
    completion_seq: int
    run_hash: int
    incarnation: int
    offset: int
    length: int
    returned: int
    completion_status: int
    role: int
    flags: int


def load_raw(path: Path) -> tuple[dict[str, object], list[Raw]]:
    data = path.read_bytes()
    if len(data) < RAW_HEADER.size:
        raise ValueError("short raw trace")
    values = RAW_HEADER.unpack_from(data)
    magic, version, header_bytes, record_bytes, _reserved = values[:5]
    count, capacity, dropped, buffer_bytes, run_hash = values[5:10]
    if magic != b"Z0ATRCE1" or version != 1 or header_bytes != RAW_HEADER.size or record_bytes != RAW_RECORD.size:
        raise ValueError("raw trace ABI mismatch")
    if len(data) != header_bytes + count * record_bytes or count > capacity or dropped:
        raise ValueError("raw trace length/capacity/drop closure failed")
    records: list[Raw] = []
    for index in range(count):
        row = RAW_RECORD.unpack_from(data, header_bytes + index * record_bytes)
        records.append(Raw(row[0], row[1], row[2], row[7], row[8], row[11], row[12], row[13], row[14], row[22], row[18]))
    if len({row.submit_seq for row in records}) != count or any(row.submit_seq <= 0 for row in records):
        raise ValueError("raw write global sequence is not unique and positive")
    if sorted(row.completion_seq for row in records) != list(range(1, count + 1)):
        raise ValueError("raw completion sequence is not a permutation of 1..N")
    if len({row.request_id for row in records}) != count:
        raise ValueError("raw request IDs are not unique")
    if any(row.run_hash != run_hash or (row.flags & 3) != 3 or row.returned < 0 or row.returned > row.length or row.completion_status for row in records):
        raise ValueError("raw success/identity closure failed")
    header = {
        "run_id": c_string(values[10]),
        "system": c_string(values[11]),
        "run_hash": run_hash,
        "record_count": count,
        "buffer_bytes": buffer_bytes,
    }
    return header, sorted(records, key=lambda row: row.submit_seq)


def load_lifecycle(path: Path, run_id: str, run_hash: int, system: str) -> list[dict[str, object]]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    if len(rows) < 2 or rows[0].get("record_type") != "lifecycle_header" or rows[-1].get("record_type") != "lifecycle_trailer":
        raise ValueError("lifecycle header/trailer closure absent")
    header, trailer = rows[0], rows[-1]
    events = rows[1:-1]
    if header.get("schema") != "zns-ann-z0a-r2-lifecycle-v1" or header.get("run_id") != run_id:
        raise ValueError("lifecycle schema/run mismatch")
    if int(header.get("run_hash", -1)) != run_hash or header.get("system") != system or int(header.get("dropped", -1)) != 0:
        raise ValueError("lifecycle identity/drop closure failed")
    if trailer.get("status") != "complete" or int(header.get("record_count", -1)) != len(events) or int(trailer.get("record_count", -1)) != len(events):
        raise ValueError("lifecycle count/status closure failed")
    sequences: set[int] = set()
    for event in events:
        sequence = int(event.get("global_seq", 0))
        if event.get("record_type") != "lifecycle_event" or event.get("event_kind") != "TRUNCATE":
            raise ValueError("unsupported lifecycle event")
        if sequence <= 0 or sequence in sequences or int(event.get("run_hash", -1)) != run_hash:
            raise ValueError("lifecycle global sequence/run hash invalid")
        if int(event.get("flags", 0)) & 3 != 3 or int(event.get("status", -1)) != 0:
            raise ValueError("unsuccessful lifecycle event in formal trace")
        if int(event.get("new_size_bytes", -1)) < 0 or int(event.get("old_size_bytes", -1)) < 0:
            raise ValueError("negative lifecycle size")
        sequences.add(sequence)
    return sorted(events, key=lambda row: int(row["global_seq"]))


def load_normalized(path: Path) -> list[tuple[int, int, int, int, int, int, int]]:
    data = path.read_bytes()
    if len(data) < PAGE_HEADER.size:
        raise ValueError("short normalized page file")
    magic, version, record_bytes, count = PAGE_HEADER.unpack_from(data)
    if magic != b"Z0APAGE1" or version != 1 or record_bytes != PAGE_RECORD.size:
        raise ValueError("normalized page ABI mismatch")
    if len(data) != PAGE_HEADER.size + count * record_bytes:
        raise ValueError("normalized page length/count mismatch")
    return [PAGE_RECORD.unpack_from(data, PAGE_HEADER.size + index * record_bytes) for index in range(count)]


def expected_fragments(raw: list[Raw]) -> list[tuple[int, int, int, int, int, int, int]]:
    output = []
    for request in raw:
        remaining = request.returned
        position = request.offset
        page_index = 0
        while remaining:
            aligned = position // BLOCK * BLOCK
            amount = min(remaining, BLOCK - (position - aligned))
            output.append((request.request_id, request.submit_seq, request.run_hash, request.incarnation, aligned, page_index, amount))
            remaining -= amount
            position += amount
            page_index += 1
    return output


def load_trace_meta(path: Path, run_id: str, run_hash: int) -> tuple[dict[int, dict[str, object]], Path]:
    meta = json.loads(path.read_text())
    if meta.get("status") != "complete" or meta.get("run_id") != run_id or int(meta.get("run_hash", -1)) != run_hash:
        raise ValueError("trace meta run identity/status mismatch")
    objects: dict[int, dict[str, object]] = {}
    for row in meta.get("objects", []):
        incarnation = int(row["incarnation"])
        if incarnation in objects or row["stable_object_id"] != f"{run_id}:{incarnation}":
            raise ValueError("trace meta object incarnation reused or crosses runs")
        objects[incarnation] = row
    return objects, Path(str(meta["index_root"])).resolve(strict=True)


def replay_materialization(
    run_id: str,
    initial_objects: dict[str, dict[str, object]],
    initial_keys: set[str],
    raw_requests: list[Raw],
    normalized: list[tuple[int, int, int, int, int, int, int]],
    lifecycle: list[dict[str, object]],
) -> tuple[dict[str, int], dict[int, int], dict[str, int], list[dict[str, object]]]:
    versions = {key: 0 for key in initial_keys}
    sizes = {int(row["object_incarnation"]): int(row["size_bytes"]) for row in initial_objects.values()}
    counters = {
        "application_bytes": 0,
        "normalized_fragment_bytes": 0,
        "new_page_events": 0,
        "replacement_page_events": 0,
        "allocated_append_bytes": 0,
        "replacement_rmw_read_bytes": 0,
        "new_page_zero_fill_bytes": 0,
    }
    writes: dict[int, list[tuple[int, int, int, int, int, int, int]]] = {}
    for row in normalized:
        writes.setdefault(int(row[1]), []).append(row)
    lifecycle_by_seq = {int(row["global_seq"]): row for row in lifecycle}
    raw_by_seq = {row.submit_seq: row for row in raw_requests}
    if set(raw_by_seq) != set(writes):
        raise ValueError("raw requests and normalized write sequences differ")
    all_sequences = set(writes) | set(lifecycle_by_seq)
    if set(writes) & set(lifecycle_by_seq) or sorted(all_sequences) != list(range(1, len(all_sequences) + 1)):
        raise ValueError("WRITE/TRUNCATE do not form one gap-free global sequence domain")
    events = []
    for global_seq in sorted(all_sequences):
        if global_seq in writes:
            for request_id, submit_seq, _run_hash, incarnation, offset, page_index, amount in sorted(writes[global_seq], key=lambda row: row[5]):
                key = f"{run_id}:{incarnation}:{offset}"
                replacement = key in versions
                version = versions[key] + 1 if replacement else 1
                versions[key] = version
                counters["application_bytes"] += amount
                counters["normalized_fragment_bytes"] += amount
                counters["allocated_append_bytes"] += BLOCK
                counters["replacement_page_events" if replacement else "new_page_events"] += 1
                if amount < BLOCK:
                    counters["replacement_rmw_read_bytes" if replacement else "new_page_zero_fill_bytes"] += BLOCK - amount
                events.append(
                    {
                        "op": "write",
                        "key": key,
                        "page_bytes": amount,
                        "allocated_append_bytes": BLOCK,
                        "request_id": request_id,
                        "global_seq": submit_seq,
                        "page_index_within_request": page_index,
                        "materialization": "full_4096_byte_logical_page_version",
                    }
                )
            # EOF comes from the raw byte range, not aligned page fragments:
            # aligned_offset + fragment_bytes loses the page-internal start.
            request = raw_by_seq[global_seq]
            sizes[request.incarnation] = max(
                sizes.get(request.incarnation, 0), request.offset + request.returned
            )
            continue
        row = lifecycle_by_seq[global_seq]
        incarnation = int(row["object_incarnation"])
        old_size = int(row["old_size_bytes"])
        new_size = int(row["new_size_bytes"])
        if sizes.get(incarnation) != old_size:
            raise ValueError(f"TRUNCATE old-size mismatch for incarnation {incarnation}: replay={sizes.get(incarnation)}, trace={old_size}")
        invalidated: list[str] = []
        first_removed = (new_size + BLOCK - 1) // BLOCK * BLOCK
        if new_size < old_size:
            prefix = f"{run_id}:{incarnation}:"
            for key in list(versions):
                if key.startswith(prefix) and int(key.rsplit(":", 1)[1]) >= first_removed:
                    invalidated.append(key)
                    del versions[key]
        sizes[incarnation] = new_size
        events.append({
            "op": "truncate",
            "global_seq": global_seq,
            "object_incarnation": incarnation,
            "old_size_bytes": old_size,
            "new_size_bytes": new_size,
            "invalidated_keys": sorted(invalidated),
            "allocated_append_bytes": 0,
        })
    if counters["application_bytes"] != counters["normalized_fragment_bytes"]:
        raise ValueError("application/normalized fragment bytes do not close")
    if counters["allocated_append_bytes"] != len(normalized) * BLOCK:
        raise ValueError("allocated append bytes do not close")
    return versions, sizes, counters, events


def final_snapshot_pages(
    root: Path, run_id: str, meta_objects: dict[int, dict[str, object]]
) -> tuple[dict[str, dict[str, object]], dict[str, str], dict[int, int]]:
    expected_names: dict[str, int] = {}
    for incarnation, row in meta_objects.items():
        name = Path(str(row["path"])).name
        if name in expected_names:
            raise ValueError(f"duplicate final object basename: {name}")
        expected_names[name] = incarnation
    actual_names = {path.name for path in root.iterdir() if path.is_file() and not path.is_symlink()}
    if actual_names != set(expected_names):
        raise ValueError(f"final snapshot object set mismatch: missing={sorted(set(expected_names)-actual_names)}, extra={sorted(actual_names-set(expected_names))}")
    pages: dict[str, dict[str, object]] = {}
    object_hashes: dict[str, str] = {}
    object_sizes: dict[int, int] = {}
    for name, incarnation in expected_names.items():
        path = (root / name).resolve(strict=True)
        row = meta_objects[incarnation]
        if path.stat().st_dev != int(row["device_id"]) or path.stat().st_ino != int(row["inode"]):
            raise ValueError(f"final snapshot object identity mismatch: {name}")
        object_hashes[f"{run_id}:{incarnation}"] = sha256_path(path)
        size = path.stat().st_size
        object_sizes[incarnation] = size
        with path.open("rb") as stream:
            for offset in range(0, size, BLOCK):
                page_bytes = min(BLOCK, size - offset)
                payload = stream.read(page_bytes)
                key = f"{run_id}:{incarnation}:{offset}"
                if key in pages:
                    raise ValueError(f"final page collision: {key}")
                pages[key] = {
                    "stable_object_id": f"{run_id}:{incarnation}",
                    "object_incarnation": incarnation,
                    "file_role_code": int(row["initial_role"]),
                    "relative_path": name,
                    "logical_page_key": key,
                    "aligned_page_offset": offset,
                    "page_bytes": page_bytes,
                    "snapshot_page_sha256": hashlib.sha256(payload).hexdigest(),
                }
    return pages, object_hashes, object_sizes


def exclusive_json(path: Path, payload: object) -> None:
    if path.exists() or not path.parent.is_dir():
        raise FileExistsError(f"output exists or parent absent: {path}")
    with path.open("x", encoding="utf-8") as output:
        json.dump(payload, output, indent=2, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-manifest", type=Path, required=True)
    parser.add_argument("--initial-snapshot", type=Path, required=True)
    parser.add_argument("--physical-map", type=Path, required=True)
    parser.add_argument("--physical-image", type=Path, required=True)
    parser.add_argument("--raw-trace", type=Path, required=True)
    parser.add_argument("--normalized-pages", type=Path, required=True)
    parser.add_argument("--trace-meta", type=Path, required=True)
    parser.add_argument("--lifecycle", type=Path, required=True)
    parser.add_argument("--final-snapshot", type=Path, required=True)
    parser.add_argument("--final-live-output", type=Path, required=True)
    parser.add_argument("--replay-spec-output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    initial_header, initial_objects, initial_pages, initial_trailer = load_initial(args.initial_manifest)
    initial_root = args.initial_snapshot.resolve(strict=True)
    source_paths = validate_initial_snapshot(initial_root, initial_objects)
    packing_header, packed, packing_trailer = load_packing(args.physical_map)
    config, ordered_initial = validate_packing(
        initial_header,
        initial_pages,
        packing_header,
        packed,
        packing_trailer,
        args.physical_image,
        source_paths,
    )

    raw_header, raw = load_raw(args.raw_trace)
    run_id = str(initial_header["run_id"])
    if raw_header["run_id"] != run_id or raw_header["system"] != initial_header["system"]:
        raise ValueError("raw trace and initial manifest belong to different runs")
    normalized = load_normalized(args.normalized_pages)
    expected = expected_fragments(raw)
    if normalized != expected:
        raise ValueError("normalized pages are not an independent exact split of raw requests in submit order")
    if sum(row.returned for row in raw) != sum(row[6] for row in normalized):
        raise ValueError("raw request and normalized page bytes do not close")
    lifecycle = load_lifecycle(args.lifecycle, run_id, int(raw_header["run_hash"]), str(initial_header["system"]))

    meta_objects, recorded_final_root = load_trace_meta(args.trace_meta, run_id, int(raw_header["run_hash"]))
    final_root = args.final_snapshot.resolve(strict=True)
    if final_root != recorded_final_root:
        raise ValueError("final snapshot is not the trace-meta index root")
    if any(row.incarnation not in meta_objects for row in raw):
        raise ValueError("raw trace references an object absent from trace meta")
    initial_incarnations = {int(row["object_incarnation"]) for row in initial_objects.values()}
    if any(incarnation not in meta_objects for incarnation in initial_incarnations):
        raise ValueError("initial object absent from trace meta")

    versions, replay_sizes, materialization, replay_events = replay_materialization(
        run_id, initial_objects, set(initial_pages), raw, normalized, lifecycle
    )
    final_pages, object_hashes, final_sizes = final_snapshot_pages(final_root, run_id, meta_objects)
    if replay_sizes != final_sizes:
        raise ValueError(f"replayed EOF map does not equal final snapshot: replay={replay_sizes}, final={final_sizes}")
    if set(versions) != set(final_pages):
        missing = set(final_pages) - set(versions)
        extra = set(versions) - set(final_pages)

        def mismatch_sample(keys: set[str]) -> list[dict[str, object]]:
            rows = []
            for key in sorted(keys)[:16]:
                _prefix, incarnation_text, offset_text = key.rsplit(":", 2)
                incarnation = int(incarnation_text)
                meta = meta_objects.get(incarnation, {})
                snapshot_path = final_root / Path(str(meta.get("path", ""))).name
                rows.append(
                    {
                        "logical_page_key": key,
                        "relative_path": snapshot_path.name,
                        "aligned_page_offset": int(offset_text),
                        "final_size_bytes": snapshot_path.stat().st_size if snapshot_path.is_file() else None,
                    }
                )
            return rows

        raise ValueError(
            f"replayed live-page set does not equal final snapshot; "
            f"missing={len(missing)}, extra={len(extra)}, "
            f"missing_sample={json.dumps(mismatch_sample(missing), sort_keys=True)}, "
            f"extra_sample={json.dumps(mismatch_sample(extra), sort_keys=True)}"
        )
    final_rows = []
    for key in sorted(final_pages):
        row = dict(final_pages[key])
        row.update({"record_type": "final_live_page", "current_version": versions[key], "initial_live": key in initial_pages})
        final_rows.append(row)
    final_payload = {
        "schema": "zns-ann-z0a-r2-final-live-manifest-v1",
        "status": "pass",
        "run_id": run_id,
        "system": initial_header["system"],
        "page_count": len(final_rows),
        "logical_page_bytes": sum(int(row["page_bytes"]) for row in final_rows),
        "object_sha256": object_hashes,
        "pages": final_rows,
    }

    replay_config = {
        "zone_capacity_blocks": int(config["zone_capacity_bytes"]) // BLOCK,
        "zone_size_blocks": int(config["zone_size_bytes"]) // BLOCK,
        "logical_block_size_bytes": BLOCK,
        "number_of_zones": int(config["number_of_zones"]),
        "max_open_zones": int(config["max_open_zones"]),
        "max_active_zones": int(config["max_active_zones"]),
        "host_spare_zones": int(config["host_spare_zones"]),
    }
    replay_spec = {
        "schema": "zns-ann-z0a-r2-formal-replay-spec-v1",
        "run_id": run_id,
        "system": initial_header["system"],
        "materialization_unit": "full_4096_byte_logical_page_version",
        "config": replay_config,
        "initial_live": ordered_initial,
        "events": replay_events,
    }
    summary = {
        "schema": "zns-ann-z0a-r2-independent-readback-v1",
        "status": "pass",
        "run_id": run_id,
        "system": initial_header["system"],
        "checks": {
            "initial_each_page_exactly_once": True,
            "page_key_collision_free": True,
            "zone_capacity_open_active_spare": True,
            "initial_allocated_bytes_closed": True,
            "raw_request_to_normalized_pages": True,
            "replacement_or_new_resolved": True,
            "object_run_incarnation_closed": True,
            "final_live_set_equals_snapshot": True,
            "ordered_lifecycle_replay": True,
            "replayed_eof_equals_snapshot": True,
        },
        "initial": {
            "page_count": len(initial_pages),
            "logical_page_bytes": int(initial_trailer["logical_bytes"]),
            "allocated_append_bytes": len(initial_pages) * BLOCK,
        },
        "trace": {
            "request_count": len(raw),
            "page_event_count": len(normalized),
            "lifecycle_event_count": len(lifecycle),
            **materialization,
        },
        "final": {
            "page_count": len(final_rows),
            "logical_page_bytes": final_payload["logical_page_bytes"],
        },
        "byte_semantics": {
            "application_bytes": "sum successful returned bytes",
            "normalized_fragment_bytes": "sum per-request page intersections; equals application bytes",
            "allocated_append_bytes": "4096 for every page event regardless of fragment size",
            "replacement_rmw_read_bytes": "unwritten bytes needed to reconstruct a full replacement page; read-only cost",
            "new_page_zero_fill_bytes": "unwritten bytes zero-filled for a first page version",
            "relocation_allocated_bytes": "4096 per relocated current page; produced by simulator, not this validator",
        },
        "content_limit": "trace has no payload; final closure proves logical page set/page_bytes, not byte-for-byte replayed payload lineage",
    }
    exclusive_json(args.final_live_output, final_payload)
    exclusive_json(args.replay_spec_output, replay_spec)
    exclusive_json(args.summary, summary)
    print(json.dumps({"status": "pass", "run_id": run_id, "pages": len(normalized), "final_pages": len(final_rows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"independent_readback: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
