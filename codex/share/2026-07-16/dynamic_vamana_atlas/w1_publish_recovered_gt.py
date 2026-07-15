#!/usr/bin/env python3
"""Atomically publish a fully validated recovered CP01 truthset."""
from __future__ import annotations
import argparse, hashlib, json, os
from pathlib import Path

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()

p = argparse.ArgumentParser()
for name in ("candidate", "output", "remap_report", "validation", "comparison", "location_validation", "log", "manifest"):
    p.add_argument("--" + name.replace("_", "-"), dest=name, type=Path, required=True)
a = p.parse_args()
if a.output.exists() or a.manifest.exists():
    raise SystemExit("recovered GT publication reuse refused")
for path in (a.candidate, a.remap_report, a.validation, a.comparison, a.location_validation, a.log):
    if not path.is_file():
        raise SystemExit(f"missing publication prerequisite: {path}")
if "WARNING: found less than k GT entries" in a.log.read_text(errors="replace"):
    raise SystemExit("less-than-K warning blocks GT publication")
for path in (a.remap_report, a.comparison, a.location_validation):
    if json.loads(path.read_text()).get("status") != "pass":
        raise SystemExit(f"non-passing prerequisite: {path}")
validation = json.loads(a.validation.read_text())
checkpoints = validation.get("checkpoints", [])
checkpoint = checkpoints[0] if len(checkpoints) == 1 else {}
audits = checkpoint.get("independent_bruteforce_audits", [])
required_qids = {0, 17, 7150, 9999}
if not (checkpoint.get("nqueries") == 10000 and checkpoint.get("k") == 100
        and checkpoint.get("all_tags_active") is True and checkpoint.get("distances_finite") is True
        and checkpoint.get("distances_monotonic") is True and len(audits) == 36
        and required_qids.issubset({row.get("query_id") for row in audits})
        and all(row.get("tie_safe_top100") is True for row in audits)):
    raise SystemExit("final GT validation is not a pass")
candidate_sha = sha(a.candidate)
os.replace(a.candidate, a.output)
manifest = {"schema": "dynamic-vamana-w1-recovered-gt-manifest-v1", "status": "pass", "truthset_realpath": str(a.output.resolve()), "truthset_sha256": sha(a.output), "candidate_sha256_before_publish": candidate_sha, "atomic_publish": True, "remap_report_sha256": sha(a.remap_report), "validation_sha256": sha(a.validation), "comparison_sha256": sha(a.comparison), "location_validation_sha256": sha(a.location_validation), "compute_log_sha256": sha(a.log)}
if manifest["truthset_sha256"] != candidate_sha:
    raise SystemExit("GT hash changed during atomic publication")
a.manifest.write_text(json.dumps(manifest, indent=2) + "\n")
