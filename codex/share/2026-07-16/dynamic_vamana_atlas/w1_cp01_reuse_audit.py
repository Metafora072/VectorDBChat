#!/usr/bin/env python3
"""Read-only, semantic and content audit of the preserved CP01 materialization."""
from __future__ import annotations

import argparse, hashlib, json, struct
from pathlib import Path
import numpy as np


FILES = ("replace_cp01_80k.bin", "replace_cp01_80k.tsv", "replace_cp01_manifest.json",
         "trace_validation.json", "active_cp01.tags.bin", "active_cp01.bin",
         "visibility_probes.bin", "visibility_probes.json")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def head(path: Path) -> tuple[int, int]:
    return struct.unpack("<II", path.open("rb").read(8))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--cp01", type=Path, required=True)
    p.add_argument("--parent-execution", type=Path, required=True)
    p.add_argument("--trace-revalidation", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise SystemExit("CP01 reuse audit output reuse refused")
    parent = json.loads(a.parent_execution.read_text())
    if parent.get("status") != "stopped_failed" or parent.get("stopped_phase") not in ("gt_validation", "gt_cp01_validation"):
        raise SystemExit("parent execution is not the approved GT-validation stop")
    cp01 = a.cp01.resolve(); corpus_path = a.root / "datasets/sift10m/full_10m.bin"
    artifacts = {}
    for name in FILES:
        path = cp01 / name
        if not path.is_file():
            raise SystemExit(f"missing preserved CP01 artifact: {name}")
        artifacts[name] = {"size_bytes": path.stat().st_size, "sha256": sha(path), "mtime_ns": path.stat().st_mtime_ns}
    trace_manifest = json.loads((cp01 / "replace_cp01_manifest.json").read_text())
    old_validation = json.loads((cp01 / "trace_validation.json").read_text())
    new_validation = json.loads(a.trace_revalidation.read_text())
    if not old_validation.get("valid") or not new_validation.get("valid"):
        raise SystemExit("old/new trace validation is not valid")
    if artifacts["replace_cp01_80k.bin"]["sha256"] != trace_manifest["binary_trace_sha256"]:
        raise SystemExit("preserved binary trace hash mismatch")
    if artifacts["active_cp01.tags.bin"]["sha256"] != trace_manifest["expected_cp01_active_set_sha256"]:
        raise SystemExit("preserved active-tag hash mismatch")
    nt, td = head(cp01 / "active_cp01.tags.bin"); nc, dim = head(corpus_path); na, ad = head(cp01 / "active_cp01.bin")
    if (nt, td, na, ad, nc, dim) != (8_000_000, 1, 8_000_000, 128, 10_000_000, 128):
        raise SystemExit("CP01/corpus shape mismatch")
    tags = np.memmap(cp01 / "active_cp01.tags.bin", dtype="<u4", mode="r", offset=8, shape=(nt,))
    if np.unique(tags).size != nt or int(np.count_nonzero(tags == 0)) != 1 or int(tags[0]) != 0:
        raise SystemExit("CP01 tags are not unique or tag 0 is not active at row 0")
    probes = json.loads((cp01 / "visibility_probes.json").read_text())
    if len(probes.get("positions", [])) != 9 or len(probes.get("probes", [])) != 18:
        raise SystemExit("CP01 visibility probe shape mismatch")
    active = np.memmap(cp01 / "active_cp01.bin", dtype="<f4", mode="r", offset=8, shape=(na, ad))
    corpus = np.memmap(corpus_path, dtype="<f4", mode="r", offset=8, shape=(nc, dim))
    rng = np.random.default_rng(20260716)
    rows = np.unique(np.concatenate((np.asarray([0], dtype=np.int64), rng.choice(nt, size=1024, replace=False)))).astype(np.int64)
    mismatches = []
    for lo in range(0, rows.size, 128):
        selected = rows[lo:lo + 128]
        same = np.all(np.asarray(active[selected]) == np.asarray(corpus[np.asarray(tags[selected], dtype=np.int64)]), axis=1)
        mismatches.extend(selected[~same].tolist())
    if mismatches:
        raise SystemExit(f"sampled CP01 vector/tag mismatch: {mismatches[:8]}")
    # Stronger than a sampled comparison: stream-reconstruct the entire active
    # vector file from the frozen corpus/tag mapping and compare SHA-256.
    semantic = hashlib.sha256(struct.pack("<II", nt, dim))
    for lo in range(0, nt, 16384):
        semantic.update(np.asarray(corpus[np.asarray(tags[lo:lo + 16384], dtype=np.int64)], dtype="<f4").tobytes())
    semantic_sha = semantic.hexdigest()
    if semantic_sha != artifacts["active_cp01.bin"]["sha256"]:
        raise SystemExit("full semantic CP01 vector reconstruction hash mismatch")
    parent_has_complete = bool(parent.get("cp01_artifacts"))
    report = {"schema": "dynamic-vamana-w1-cp01-reuse-validation-v1", "status": "pass", "read_only": True,
              "parent_execution": str(a.parent_execution.resolve()), "parent_execution_sha256": sha(a.parent_execution),
              "parent_manifest_complete_cp01_hashes_present": parent_has_complete,
              "parent_manifest_gap_note": None if parent_has_complete else "parent manifest was emitted before CP01 preparation; no historical per-file CP01 hash table exists",
              "compensating_full_semantic_reconstruction": True, "artifacts": artifacts,
              "trace_revalidation": str(a.trace_revalidation.resolve()), "active_cardinality": nt,
              "tag_zero_active": True, "tag_zero_row": 0, "probe_positions": 9, "probe_count": 18,
              "sample_seed": 20260716, "sampled_rows": int(rows.size), "sampled_vector_tag_mismatches": 0,
              "active_vector_sha256": artifacts["active_cp01.bin"]["sha256"],
              "semantic_reconstruction_sha256": semantic_sha, "full_vector_tag_mapping_exact": True}
    a.output.parent.mkdir(parents=True, exist_ok=True); a.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
