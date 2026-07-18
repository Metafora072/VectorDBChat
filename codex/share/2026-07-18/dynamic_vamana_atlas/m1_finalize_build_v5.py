#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--build", type=Path, required=True)
parser.add_argument("--accepted", type=Path, required=True)
args = parser.parse_args()

accepted = load(args.accepted / "build_manifest.json")
assert accepted["schema"] == "dynamic-vamana-write-attribution-m0-build-v5"
assert accepted["status"] == "pass"
profiler = args.build / "lib/libm0write.so"
assert sha256(profiler) == accepted["profiler_sha256"]

profiles = {name: load(args.build / f"selftest/{name}/profile.json") for name in ("empty", "posix", "boundary", "fdreuse", "aio", "filesystem-copy")}
assert profiles["empty"]["ledger_totals"] == {}
assert profiles["posix"]["ledger_totals"]["posix"] == {"requested_bytes": 4096, "request_count": 1}
assert sum(row["requested_bytes"] for row in profiles["boundary"]["buckets"]) == 4096
assert {Path(row["path"]).name for row in profiles["fdreuse"]["buckets"]} == {"index_disk.index", "index_pq_compressed.bin"}
assert profiles["aio"]["ledger_totals"]["async"] == {"requested_bytes": 4096, "request_count": 1}
assert all(row["entry"] != "sendfile" for row in profiles["aio"]["entry_totals"])
copy_result = load(args.build / "selftest/filesystem-copy/result.json")
copy_profile = profiles["filesystem-copy"]
sendfile_rows = [row for row in copy_profile["entry_totals"] if row["entry"] == "sendfile"]
assert len(sendfile_rows) == 1 and sendfile_rows[0]["request_count"] == 1
assert sendfile_rows[0]["requested_bytes"] == copy_result["source_before"]["size"]
assert copy_result["content_equal"] is True

canonical_root = args.root / "build/w1-canonical-v6/install"
systems = {}
for system in ("DGAI", "OdinANN"):
    binary = args.build / f"install/{system}/w1_canary"
    canonical = canonical_root / f"{system}/w1_canary"
    systems[system] = {
        "instrumented_binary": str(binary.resolve()),
        "instrumented_sha256": sha256(binary),
        "canonical_binary": str(canonical.resolve()),
        "canonical_sha256": sha256(canonical),
        "binary_is_independent": sha256(binary) != sha256(canonical),
        "source_patch": f"{system}_m0_v4.patch" if system == "DGAI" else "accepted-m0-v5-r01",
    }
    assert systems[system]["binary_is_independent"]
assert systems["OdinANN"]["instrumented_sha256"] == accepted["systems"]["OdinANN"]["instrumented_sha256"]

manifest = {
    "schema": "dynamic-vamana-write-attribution-m0-build-v5",
    "status": "pass",
    "scope": "m1-matched-size-dual-system",
    "profiler_library": str(profiler.resolve()),
    "profiler_sha256": sha256(profiler),
    "profiler_identity_matches_accepted_odin_r04": True,
    "strict_superset_of_dgai_r03_v4": True,
    "new_physical_entry": "sendfile",
    "systems": systems,
    "selftests": ["empty", "posix", "boundary", "fdreuse", "DGAI-aio-no-sendfile", "filesystem-copy-overwrite"],
}
(args.build / "build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
(args.build / "M1_V5_BUILD_OK").touch()
print(args.build / "build_manifest.json")
