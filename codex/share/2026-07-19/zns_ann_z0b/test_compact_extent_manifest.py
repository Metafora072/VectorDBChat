#!/usr/bin/env python3
"""Small end-to-end and fail-closed tests for compact_extent_manifest.py."""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

import compact_extent_manifest as manifest


NORMAL_RECORD = struct.Struct("<QQQQQQIIHHHH")


class CompactExtentManifestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="z0b-compact-selftest-")
        self.base = Path(self.temporary.name)
        self.root = self.base / "index"
        self.root.mkdir()
        (self.root / "a.bin").write_bytes(b"A" * 5000)
        (self.root / "gone.bin").write_bytes(b"G" * 4096)
        self.script = Path(manifest.__file__).resolve()
        self.run_id = "z0b-compact-selftest"
        self.initial_map = self.base / "INITIAL_EXTENTS.bin"
        self.initial_json = self.base / "INITIAL.json"
        self.registry = self.base / "objects.tsv"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_tool(self, *arguments: object, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["python3", str(self.script), *(str(value) for value in arguments)],
            check=False, capture_output=True, text=True,
        )
        if expect_success and result.returncode:
            self.fail(f"command failed ({result.returncode}): {result.stderr}")
        if not expect_success and not result.returncode:
            self.fail("expected command failure")
        return result

    def prepare(self) -> dict[str, object]:
        self.run_tool(
            "prepare", "--initial-root", self.root, "--run-id", self.run_id,
            "--system", "DGAI", "--object-map", self.registry,
            "--output", self.initial_map, "--summary", self.initial_json,
        )
        return json.loads(self.initial_json.read_text())

    def write_trace_inputs(self, initial: dict[str, object]) -> tuple[Path, Path, Path]:
        by_name = {row["relative_path"]: row for row in initial["objects"]}
        a_inc = int(by_name["a.bin"]["incarnation"])
        gone_inc = int(by_name["gone.bin"]["incarnation"])
        a_stat = (self.root / "a.bin").stat()
        gone_stat = (self.root / "gone.bin").stat()

        (self.root / "a.bin").write_bytes(b"C" * 4096)
        (self.root / "gone.bin").unlink()
        (self.root / "new.tmp").write_bytes(b"N" * 1000)
        new_stat = (self.root / "new.tmp").stat()
        new_inc = max(a_inc, gone_inc) + 1
        run_hash = manifest.fnv1a(self.run_id)

        objects = []
        for name, incarnation, stat, initial_object, role in (
            ("a.bin", a_inc, a_stat, True, 10),
            ("gone.bin", gone_inc, gone_stat, True, 10),
            ("new.tmp", new_inc, new_stat, False, 11),
        ):
            objects.append({
                "stable_object_id": f"{self.run_id}:{incarnation}",
                "incarnation": incarnation, "device_id": stat.st_dev,
                "inode": stat.st_ino, "ctime_ns": stat.st_ctime_ns,
                "initial": initial_object, "initial_role": role,
                "path": str((self.root / name).resolve()),
            })
        meta = {
            "schema": "zns-ann-z0a-trace-meta-v1", "status": "complete",
            "run_id": self.run_id, "run_hash": run_hash, "system": "DGAI",
            "index_root": str(self.root.resolve()), "record_count": 3,
            "capacity": 16, "buffer_peak_bytes": 1024,
            "lifecycle_record_count": 4, "lifecycle_dropped_events": 0,
            "dropped_events": 0, "identity_errors": 0, "objects": objects,
        }
        meta_path = self.base / "meta.json"
        meta_path.write_text(json.dumps(meta, sort_keys=True) + "\n")

        identity = {row["incarnation"]: row for row in objects}

        def event(seq: int, inc: int, old: int, new: int, source: int) -> dict[str, object]:
            row = identity[inc]
            return {
                "record_type": "lifecycle_event", "event_kind": "TRUNCATE",
                "global_seq": seq, "timestamp_ns": seq, "thread_seq": seq,
                "thread_id": 1, "run_hash": run_hash, "object_incarnation": inc,
                "device_id": row["device_id"], "inode": row["inode"],
                "path_hash": manifest.fnv1a(row["path"]),
                "old_size_bytes": old, "new_size_bytes": new,
                "status": 0, "flags": 3, "system": 1, "phase": 2,
                "source_entrypoint": source, "file_role": row["initial_role"],
            }

        lifecycle_rows = [
            {"record_type": "lifecycle_header", "schema": "zns-ann-z0a-r2-lifecycle-v1",
             "run_id": self.run_id, "run_hash": run_hash, "system": "DGAI",
             "record_count": 4, "capacity": 16, "dropped": 0},
            event(2, a_inc, 5000, 4096, 1),
            event(4, gone_inc, 4096, 0, 3),
            event(5, new_inc, 0, 0, 2),
            event(7, new_inc, 5137, 1000, 1),
            {"record_type": "lifecycle_trailer", "status": "complete", "record_count": 4},
        ]
        lifecycle_path = self.base / "lifecycle.jsonl"
        lifecycle_path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n"
                                          for row in lifecycle_rows))

        records = [
            (1, 11, a_inc, 0, 1, 1, 100, 0, 2, 10, 1, 0),
            (3, 12, a_inc, 0, 2, 1, 4096, 0, 2, 10, 1, 0),
            (6, 13, new_inc, 0, 3, 1, 3959, 0, 2, 11, 1, 0),
            (6, 13, new_inc, 4096, 3, 1, 1041, 1, 2, 11, 1, 0),
        ]
        normalized_path = self.base / "normalized.bin"
        with normalized_path.open("wb") as stream:
            stream.write(manifest.NORMAL_HEADER.pack(manifest.NORMAL_MAGIC, 1, NORMAL_RECORD.size,
                                                     len(records), 3))
            for record in records:
                stream.write(NORMAL_RECORD.pack(*record))
        return meta_path, lifecycle_path, normalized_path

    def close(self, suffix: str, meta: Path, lifecycle: Path, normalized: Path,
              expect_success: bool = True) -> tuple[Path, Path, subprocess.CompletedProcess[str]]:
        output = self.base / f"FINAL_EXTENTS_{suffix}.bin"
        summary = self.base / f"CLOSURE_{suffix}.json"
        result = self.run_tool(
            "close", "--initial-map", self.initial_map,
            "--initial-summary", self.initial_json, "--normalized", normalized,
            "--lifecycle", lifecycle, "--trace-meta", meta,
            "--final-root", self.root, "--output", output, "--summary", summary,
            "--temp-dir", self.base, "--chunk-records", 2,
            expect_success=expect_success,
        )
        return output, summary, result

    def test_lifecycle_content_closure_and_determinism(self) -> None:
        initial = self.prepare()
        raw = self.initial_map.read_bytes()
        header = manifest.HEADER.unpack(raw[:manifest.HEADER.size])
        digest_offset = manifest.HEADER.size + header[5] * manifest.OBJECT.size + header[6] * manifest.EXTENT.size
        initial_digests = [raw[digest_offset + index * 32:digest_offset + (index + 1) * 32]
                           for index in range(header[7])]
        self.assertEqual(initial_digests[1], hashlib.sha256(b"A" * 904 + bytes(3192)).digest())
        replay_view = self.base / "INITIAL_REPLAY_VIEW.bin"
        replay_summary = self.base / "INITIAL_REPLAY_VIEW.json"
        converter = self.script.with_name("initial_replay_view.py")
        converted = subprocess.run(
            ["python3", str(converter), "--authoritative", str(self.initial_map),
             "--initial-json", str(self.initial_json), "--output", str(replay_view),
             "--summary", str(replay_summary)], check=False, capture_output=True, text=True,
        )
        if converted.returncode:
            self.fail(f"initial replay-view conversion failed: {converted.stderr}")
        self.assertEqual(json.loads(replay_summary.read_text())["page_count"], 3)

        meta, lifecycle, normalized = self.write_trace_inputs(initial)
        first_map, first_json, _ = self.close("one", meta, lifecycle, normalized)
        second_map, second_json, _ = self.close("two", meta, lifecycle, normalized)
        self.assertEqual(first_map.read_bytes(), second_map.read_bytes())
        self.assertEqual(first_json.read_bytes(), second_json.read_bytes())

        closure = json.loads(first_json.read_text())
        self.assertEqual((closure["request_count"], closure["lifecycle_event_count"]), (3, 4))
        self.assertEqual((closure["object_count"], closure["page_count"]), (2, 2))
        self.assertTrue(closure["checks"]["final_page_identity_and_content_closed"])
        raw = first_map.read_bytes()
        header = manifest.HEADER.unpack(raw[:manifest.HEADER.size])
        digest_offset = manifest.HEADER.size + header[5] * manifest.OBJECT.size + header[6] * manifest.EXTENT.size
        final_digests = [raw[digest_offset + index * 32:digest_offset + (index + 1) * 32]
                         for index in range(header[7])]
        self.assertEqual(final_digests[1], hashlib.sha256(b"N" * 1000 + bytes(3096)).digest())

        bad_rows = [json.loads(line) for line in lifecycle.read_text().splitlines()]
        bad_rows[1]["path_hash"] ^= 1
        bad_lifecycle = self.base / "bad_lifecycle.jsonl"
        bad_lifecycle.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n"
                                         for row in bad_rows))
        bad_map, bad_json, result = self.close("bad", meta, bad_lifecycle, normalized, False)
        self.assertIn("lifecycle object identity mismatch", result.stderr)
        self.assertFalse(bad_map.exists())
        self.assertFalse(bad_json.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
