#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


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

accepted = json.loads((args.accepted / "build_manifest.json").read_text())
assert accepted["schema"] == "dynamic-vamana-write-attribution-m0-build-v5"
assert accepted["status"] == "pass"
profiler = args.build / "lib/libm0write.so"
assert sha256(profiler) == accepted["profiler_sha256"]

synthetic = json.loads((args.build / "selftest/m2-logical/profile.json").read_text())
assert synthetic["schema"] == "dynamic-vamana-neighbor-repair-m2-logical-v1"
assert synthetic["status"] == "complete"
assert synthetic["totals"]["replacements"] == 2
assert synthetic["totals"]["reverse_edge_repair_attempts"] == 5
assert synthetic["totals"]["neighbor_only_logical_page_events"] == 3
assert synthetic["totals"]["neighbor_only_submitted_page_touches"] == 3
assert synthetic["totals"]["stage_unique_neighbor_only_pages"] == 3
assert synthetic["closure"] == {
    "operation_page_set_mismatch_count": 0,
    "fanout_identity_mismatch_count": 0,
    "configuration_mismatch_count": 0,
    "logical_neighbor_only_events_equal_submitted_touches": True,
}
assert synthetic["page_touch_frequency"]["submitted_neighbor_only_pages"] == {"1": 3}

canonical_root = args.root / "build/w1-canonical-v6/install"
systems = {}
for system in ("DGAI", "OdinANN"):
    binary = args.build / f"install/{system}/w1_canary"
    canonical = canonical_root / f"{system}/w1_canary"
    assert binary.is_file() and canonical.is_file()
    systems[system] = {
        "instrumented_binary": str(binary.resolve()),
        "instrumented_sha256": sha256(binary),
        "canonical_binary": str(canonical.resolve()),
        "canonical_sha256": sha256(canonical),
        "binary_is_independent": sha256(binary) != sha256(canonical),
        "m2_source_patch": f"{system}_m2.patch",
    }
    assert systems[system]["binary_is_independent"]

manifest = {
    "schema": "dynamic-vamana-write-attribution-m0-build-v5",
    "status": "pass",
    "scope": "m2-neighbor-repair-decomposition-dual-system",
    "profiler_library": str(profiler.resolve()),
    "profiler_sha256": sha256(profiler),
    "profiler_identity_matches_accepted_v5": True,
    "logical_schema": "dynamic-vamana-neighbor-repair-m2-logical-v1",
    "logical_collector_sha256": sha256(args.build / "source-evidence/m2_metrics.h"),
    "systems": systems,
    "selftests": ["m2-memory-aggregation-exact-histogram-and-page-closure"],
}
(args.build / "build_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
(args.build / "M2_BUILD_OK").touch()
print(args.build / "build_manifest.json")
