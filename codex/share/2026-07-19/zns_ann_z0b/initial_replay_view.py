#!/usr/bin/env python3
"""Validate authoritative Z0BEXT1 initial extents and derive Z0BMAP1.

Z0BMAP1 is deliberately only a compact replay view.  Z0BEXT1 plus its
summary remains the authoritative page/content closure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path


PAGE = 4096
EXT_MAGIC = b"Z0BEXT1\0"
EXT_HEADER = struct.Struct("<8sIIIIQQQQQ")
OBJECT = struct.Struct("<QQQQQQHHI")
EXTENT = struct.Struct("<QQQQIIHHI")
PAGE_DIGEST_BYTES = 32
VIEW_HEADER = struct.Struct("<8sIIQQ")
VIEW_RECORD = struct.Struct("<QQIHH")


def fail(message: str) -> None:
    raise ValueError(message)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    if path.exists() or temporary.exists():
        fail(f"refusing output reuse: {path}")
    with temporary.open("x") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def convert(args: argparse.Namespace) -> dict[str, object]:
    source = args.authoritative.resolve(strict=True)
    summary_path = args.initial_json.resolve(strict=True)
    summary = json.loads(summary_path.read_text())
    if summary.get("schema") != "zns-ann-z0b-compact-initial-v1" or summary.get("status") != "pass":
        fail("authoritative initial summary schema/status mismatch")
    source_sha = sha256_path(source)
    if summary.get("binary_sha256") != source_sha:
        fail("authoritative binary SHA-256 mismatch")

    with source.open("rb") as stream:
        raw = stream.read(EXT_HEADER.size)
        if len(raw) != EXT_HEADER.size:
            fail("short authoritative header")
        fields = EXT_HEADER.unpack(raw)
        magic, version, hbytes, obytes, ebytes, object_count, extent_count, page_count, logical_bytes, run_hash = fields
        if (magic, version, hbytes, obytes, ebytes) != (EXT_MAGIC, 1, EXT_HEADER.size, OBJECT.size, EXTENT.size):
            fail("authoritative ABI mismatch")
        expected_size = EXT_HEADER.size + object_count * OBJECT.size + extent_count * EXTENT.size + page_count * PAGE_DIGEST_BYTES
        if source.stat().st_size != expected_size:
            fail("authoritative byte/count closure mismatch")
        expected_header = (
            int(summary.get("object_count", -1)), int(summary.get("extent_count", -1)),
            int(summary.get("page_count", -1)), int(summary.get("logical_bytes", -1)),
            int(summary.get("run_hash", -1)),
        )
        if (object_count, extent_count, page_count, logical_bytes, run_hash) != expected_header:
            fail("authoritative header/summary mismatch")

        objects = [OBJECT.unpack(stream.read(OBJECT.size)) for _ in range(object_count)]
        extents = [EXTENT.unpack(stream.read(EXTENT.size)) for _ in range(extent_count)]
        digest_offset = stream.tell()
        stream.seek(0, 2)
        if stream.tell() - digest_offset != page_count * PAGE_DIGEST_BYTES:
            fail("authoritative digest section mismatch")

    summary_objects = summary.get("objects")
    if not isinstance(summary_objects, list) or len(summary_objects) != object_count:
        fail("authoritative object summary count mismatch")
    expected_incarnations = sorted(int(row[0]) for row in objects)
    if [int(row[0]) for row in objects] != expected_incarnations or len(set(expected_incarnations)) != object_count:
        fail("authoritative objects are not strict incarnation order")
    by_incarnation = {int(row.get("incarnation", -1)): row for row in summary_objects}
    if len(by_incarnation) != object_count:
        fail("duplicate/missing summary incarnation")

    descriptors: list[tuple[int, int, int, int]] = []
    seen_extent = 0
    calculated_pages = calculated_logical = 0
    for obj in objects:
        incarnation, path_hash, size_bytes, first_extent, count, pages, role, flags, reserved = obj
        meta = by_incarnation.get(incarnation)
        if meta is None:
            fail(f"missing summary object {incarnation}")
        if (path_hash, size_bytes, pages, role) != (
            int(meta.get("path_hash", -1)), int(meta.get("size_bytes", -1)),
            int(meta.get("page_count", -1)), int(meta.get("role", -1)),
        ):
            fail(f"object identity/size/role mismatch: {incarnation}")
        expected_pages = (size_bytes + PAGE - 1) // PAGE
        expected_count = int(expected_pages > 0)
        if (pages != expected_pages or count != expected_count or first_extent != seen_extent or
                flags != 3 or reserved != 0):
            fail(f"invalid initial object descriptor: {incarnation}")
        if count:
            extent = extents[first_extent]
            last_valid = size_bytes - (pages - 1) * PAGE
            expected_extent = (incarnation, 0, pages, 0, 0, last_valid, role, 0, 0)
            if extent != expected_extent:
                fail(f"invalid initial extent: {incarnation}")
            descriptors.append((role, incarnation, pages, last_valid))
        seen_extent += count
        calculated_pages += pages
        calculated_logical += size_bytes
    if seen_extent != extent_count or calculated_pages != page_count or calculated_logical != logical_bytes:
        fail("initial object/extent aggregate mismatch")

    descriptors.sort(key=lambda row: (row[0], row[1]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp.{os.getpid()}")
    if args.output.exists() or temporary.exists():
        fail(f"refusing output reuse: {args.output}")
    digest = hashlib.sha256()
    with temporary.open("xb") as out:
        header = VIEW_HEADER.pack(b"Z0BMAP1", 1, VIEW_RECORD.size, page_count, run_hash)
        out.write(header)
        digest.update(header)
        emitted = 0
        prior: tuple[int, int, int] | None = None
        for role, incarnation, pages, last_valid in descriptors:
            for page in range(pages):
                offset = page * PAGE
                key = (role, incarnation, offset)
                if prior is not None and key <= prior:
                    fail("derived view is not strict canonical order")
                prior = key
                valid = last_valid if page + 1 == pages else PAGE
                record = VIEW_RECORD.pack(incarnation, offset, valid, role, 0)
                out.write(record)
                digest.update(record)
                emitted += 1
        if emitted != page_count:
            fail("derived replay-view page count mismatch")
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, args.output)

    result = {
        "schema": "zns-ann-z0b-initial-replay-view-v1",
        "status": "pass",
        "run_id": summary.get("run_id"),
        "run_hash": run_hash,
        "system": summary.get("system"),
        "authoritative_binary": str(source),
        "authoritative_binary_sha256": source_sha,
        "authoritative_summary": str(summary_path),
        "authoritative_summary_sha256": sha256_path(summary_path),
        "replay_view_sha256": digest.hexdigest(),
        "object_count": object_count,
        "page_count": page_count,
        "logical_bytes": logical_bytes,
        "allocated_bytes": page_count * PAGE,
        "record_bytes": VIEW_RECORD.size,
        "sequence_only": True,
        "temporal_fields_consumed": False,
        "authoritative_content_digests_preserved_in_source": True,
        "warning": "Z0BMAP1 is a derived replay view; Z0BEXT1 and its summary remain authoritative.",
    }
    atomic_json(args.summary, result)
    return {"status": "pass", "pages": page_count, "logical_bytes": logical_bytes,
            "allocated_bytes": page_count * PAGE}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authoritative", type=Path, required=True)
    parser.add_argument("--initial-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    print(json.dumps(convert(parser.parse_args()), sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"initial_replay_view: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
