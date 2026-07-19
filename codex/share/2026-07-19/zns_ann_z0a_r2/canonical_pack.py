#!/usr/bin/env python3
"""Materialize a canonical Z0A initial image from an immutable pre-run snapshot.

Pages are sorted by (file_role, stable_object_id, aligned_page_offset), then
packed into ordinary zones.  Every logical page version consumes exactly one
4 KiB append block.  A partial tail is zero padded in the physical image; its
logical page_bytes and its allocated_append_bytes remain distinct in the map.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import BinaryIO


BLOCK = 4096
SCHEMA = "zns-ann-z0a-r2-canonical-packing-v1"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(path: Path) -> dict[str, int | str]:
    config = json.loads(path.read_text())
    required = {
        "logical_block_size_bytes",
        "zone_size_bytes",
        "zone_capacity_bytes",
        "number_of_zones",
        "max_open_zones",
        "max_active_zones",
        "host_spare_zones",
    }
    if set(config) - required - {"schema"} or required - set(config):
        raise ValueError("configuration field set is not exact")
    values = {name: int(config[name]) for name in required}
    if values["logical_block_size_bytes"] != BLOCK:
        raise ValueError("R2 materialization is fixed to 4096-byte logical pages")
    if values["zone_size_bytes"] % BLOCK or values["zone_capacity_bytes"] % BLOCK:
        raise ValueError("zone size/capacity must be multiples of 4096")
    if not 0 < values["zone_capacity_bytes"] <= values["zone_size_bytes"]:
        raise ValueError("zone capacity must be in (0, zone size]")
    if not 1 <= values["host_spare_zones"] < values["number_of_zones"]:
        raise ValueError("host spare count must be in [1, number_of_zones)")
    if not 1 <= values["max_open_zones"] <= values["max_active_zones"] <= values["number_of_zones"]:
        raise ValueError("require 1 <= max_open <= max_active <= number_of_zones")
    return {"schema": str(config.get("schema", "zns-ann-z0a-r2-config-v1")), **values}


def load_manifest(path: Path) -> tuple[dict[str, object], dict[str, dict[str, object]], list[dict[str, object]], dict[str, object]]:
    header = None
    trailer = None
    objects: dict[str, dict[str, object]] = {}
    pages: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        row = json.loads(line)
        kind = row.get("record_type")
        if kind == "manifest_header":
            if header is not None:
                raise ValueError("duplicate manifest header")
            header = row
        elif kind == "object":
            key = str(row["stable_object_id"])
            if key in objects:
                raise ValueError(f"duplicate object identity at line {line_number}: {key}")
            objects[key] = row
        elif kind == "initial_live_page":
            if row.get("initial_live") is not True:
                raise ValueError("non-live page present in initial-live manifest")
            pages.append(row)
        elif kind == "manifest_trailer":
            if trailer is not None:
                raise ValueError("duplicate manifest trailer")
            trailer = row
        else:
            raise ValueError(f"unknown manifest record at line {line_number}: {kind}")
    if header is None or trailer is None or trailer.get("status") != "complete":
        raise ValueError("manifest header/trailer closure absent")
    if int(header.get("logical_block_size", 0)) != BLOCK:
        raise ValueError("initial manifest is not a 4 KiB manifest")
    if int(trailer.get("object_count", -1)) != len(objects) or int(trailer.get("page_count", -1)) != len(pages):
        raise ValueError("manifest trailer counts do not close")
    seen: set[str] = set()
    per_object: dict[str, int] = {key: 0 for key in objects}
    logical_bytes = 0
    for page in pages:
        object_id = str(page["stable_object_id"])
        if object_id not in objects:
            raise ValueError(f"page references unknown object: {object_id}")
        offset = int(page["aligned_page_offset"])
        page_bytes = int(page["page_bytes"])
        expected_key = f"{object_id}:{offset}"
        if page.get("logical_page_key") != expected_key:
            raise ValueError(f"noncanonical logical page key: {page.get('logical_page_key')}")
        if expected_key in seen:
            raise ValueError(f"duplicate initial page key: {expected_key}")
        if offset < 0 or offset % BLOCK or not 1 <= page_bytes <= BLOCK:
            raise ValueError(f"bad page geometry: {expected_key}")
        if str(page["file_role"]) != str(objects[object_id]["file_role"]):
            raise ValueError(f"page/object role mismatch: {expected_key}")
        if int(page.get("initial_version", -1)) != 0:
            raise ValueError(f"initial version is not zero: {expected_key}")
        seen.add(expected_key)
        per_object[object_id] += 1
        logical_bytes += page_bytes
    for object_id, obj in objects.items():
        if int(obj["initial_live_pages"]) != per_object[object_id]:
            raise ValueError(f"object page count mismatch: {object_id}")
    if int(trailer.get("logical_bytes", -1)) != logical_bytes:
        raise ValueError("manifest logical byte total does not close")
    pages.sort(key=lambda row: (str(row["file_role"]), str(row["stable_object_id"]), int(row["aligned_page_offset"])))
    return header, objects, pages, trailer


def validate_snapshot(snapshot: Path, objects: dict[str, dict[str, object]]) -> dict[str, Path]:
    expected_names = {str(row["relative_path"]) for row in objects.values()}
    actual_names = {
        path.relative_to(snapshot).as_posix()
        for path in snapshot.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if actual_names != expected_names:
        raise ValueError(
            f"snapshot file set mismatch; missing={sorted(expected_names - actual_names)}, "
            f"extra={sorted(actual_names - expected_names)}"
        )
    paths: dict[str, Path] = {}
    for object_id, row in objects.items():
        path = (snapshot / str(row["relative_path"])).resolve(strict=True)
        if snapshot not in path.parents or not path.is_file() or path.is_symlink():
            raise ValueError(f"snapshot object escapes root or is not regular: {path}")
        stat = path.stat()
        if stat.st_size != int(row["size_bytes"]):
            raise ValueError(f"snapshot size mismatch: {path}")
        if sha256_path(path) != row["sha256"]:
            raise ValueError(f"snapshot hash mismatch (not the recorded pre-run image): {path}")
        paths[object_id] = path
    return paths


def exclusive_partial(final: Path) -> Path:
    if final.exists() or not final.parent.is_dir():
        raise FileExistsError(f"output exists or parent is absent: {final}")
    partial = final.with_name(f".{final.name}.partial.{os.getpid()}")
    if partial.exists():
        raise FileExistsError(f"stale partial output: {partial}")
    return partial


def read_page(stream: BinaryIO, offset: int, page_bytes: int) -> bytes:
    stream.seek(offset)
    payload = stream.read(page_bytes)
    if len(payload) != page_bytes:
        raise ValueError("short snapshot page read")
    return payload + bytes(BLOCK - page_bytes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--physical-map", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    config = load_config(args.config)
    header, objects, pages, trailer = load_manifest(args.manifest)
    snapshot = args.snapshot_root.resolve(strict=True)
    if not snapshot.is_dir():
        raise ValueError("snapshot root is not a directory")
    source_paths = validate_snapshot(snapshot, objects)

    capacity_blocks = int(config["zone_capacity_bytes"]) // BLOCK
    ordinary_zones = int(config["number_of_zones"]) - int(config["host_spare_zones"])
    if len(pages) > capacity_blocks * ordinary_zones:
        raise ValueError("initial image does not fit outside host spare zones")
    used_zones = (len(pages) + capacity_blocks - 1) // capacity_blocks
    if used_zones > int(config["max_active_zones"]):
        raise ValueError("canonical initial packing violates max_active_zones")

    image_partial = exclusive_partial(args.image)
    map_partial = exclusive_partial(args.physical_map)
    summary_partial = exclusive_partial(args.summary)
    open_streams: dict[str, BinaryIO] = {}
    try:
        with image_partial.open("xb") as image, map_partial.open("x", encoding="utf-8") as mapping:
            image.truncate(int(config["number_of_zones"]) * int(config["zone_size_bytes"]))
            map_header = {
                "record_type": "packing_header",
                "schema": SCHEMA,
                "run_id": header["run_id"],
                "system": header["system"],
                "materialization_unit": "full_4096_byte_logical_page_version",
                "partial_page_rule": "zero_pad_tail_to_4096_allocated_append_bytes",
                "sort_key": ["file_role", "stable_object_id", "aligned_page_offset"],
                "config": config,
            }
            mapping.write(json.dumps(map_header, sort_keys=True, separators=(",", ":")) + "\n")
            logical_bytes = allocated_bytes = padding_bytes = 0
            for packing_index, page in enumerate(pages):
                object_id = str(page["stable_object_id"])
                if object_id not in open_streams:
                    open_streams[object_id] = source_paths[object_id].open("rb")
                page_bytes = int(page["page_bytes"])
                offset = int(page["aligned_page_offset"])
                payload = read_page(open_streams[object_id], offset, page_bytes)
                zone_id = packing_index // capacity_blocks
                zone_offset = (packing_index % capacity_blocks) * BLOCK
                physical_offset = zone_id * int(config["zone_size_bytes"]) + zone_offset
                image.seek(physical_offset)
                image.write(payload)
                row = {
                    "record_type": "packed_page",
                    "packing_index": packing_index,
                    "page_key": page["logical_page_key"],
                    "stable_object_id": object_id,
                    "file_role": page["file_role"],
                    "aligned_page_offset": offset,
                    "page_bytes": page_bytes,
                    "allocated_append_bytes": BLOCK,
                    "padding_bytes": BLOCK - page_bytes,
                    "zone_id": zone_id,
                    "zone_offset": zone_offset,
                    "physical_image_offset": physical_offset,
                    "initial_version": int(page["initial_version"]),
                    "payload_sha256": hashlib.sha256(payload).hexdigest(),
                }
                mapping.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
                logical_bytes += page_bytes
                allocated_bytes += BLOCK
                padding_bytes += BLOCK - page_bytes
            trailer_row = {
                "record_type": "packing_trailer",
                "schema": SCHEMA,
                "status": "complete",
                "page_count": len(pages),
                "logical_page_bytes": logical_bytes,
                "initial_allocated_append_bytes": allocated_bytes,
                "padding_bytes": padding_bytes,
                "used_zone_count": used_zones,
                "initial_open_zone_count": 0,
                "initial_active_zone_count": used_zones,
                "host_spare_zone_ids": list(range(ordinary_zones, int(config["number_of_zones"]))),
            }
            mapping.write(json.dumps(trailer_row, sort_keys=True, separators=(",", ":")) + "\n")
            image.flush()
            os.fsync(image.fileno())
            mapping.flush()
            os.fsync(mapping.fileno())
        for stream in open_streams.values():
            stream.close()
        open_streams.clear()

        summary = {
            "schema": "zns-ann-z0a-r2-canonical-packing-summary-v1",
            "status": "pass",
            "run_id": header["run_id"],
            "system": header["system"],
            "manifest_sha256": sha256_path(args.manifest),
            "snapshot_root": str(snapshot),
            "snapshot_object_count": len(objects),
            "page_count": len(pages),
            "logical_page_bytes": int(trailer["logical_bytes"]),
            "initial_allocated_append_bytes": len(pages) * BLOCK,
            "padding_bytes": len(pages) * BLOCK - int(trailer["logical_bytes"]),
            "physical_image_logical_size_bytes": int(config["number_of_zones"]) * int(config["zone_size_bytes"]),
            "physical_map_sha256": sha256_path(map_partial),
            "materialization_unit": "full_4096_byte_logical_page_version",
        }
        with summary_partial.open("x", encoding="utf-8") as output:
            json.dump(summary, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(image_partial, args.image)
        os.replace(map_partial, args.physical_map)
        os.replace(summary_partial, args.summary)
    except BaseException:
        for stream in open_streams.values():
            stream.close()
        for partial in (image_partial, map_partial, summary_partial):
            try:
                partial.unlink()
            except FileNotFoundError:
                pass
        raise

    print(json.dumps({"status": "pass", "schema": SCHEMA, "pages": len(pages), "used_zones": used_zones}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"canonical_pack: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
