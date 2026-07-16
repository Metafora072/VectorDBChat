#!/usr/bin/env python3
"""Derive one checkpoint prefix and active/probe metadata from the master trace."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np

from w1_trajectory_generate import ACTIVE, CHECKPOINTS, atomic_tags, atomic_trace, atomic_tsv, durable_tree, read_trace, sha


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--checkpoint", type=int, choices=(5, 10, 20), required=True)
    args = parser.parse_args()
    trajectory, pct = args.trajectory.resolve(), args.checkpoint
    directory = trajectory / f"cp{pct:02d}"
    if directory.exists(): raise SystemExit("checkpoint derivation overwrite refused")
    manifest = json.loads((trajectory / "master_trace_manifest.json").read_text())
    prefix = json.loads((trajectory / "cp01_prefix_validation.json").read_text())
    if manifest.get("status") != "pass" or prefix.get("status") != "pass":
        raise SystemExit("master trace/prefix is not validated")
    master = trajectory / "master_replacements_1600k.bin"
    if sha(master) != manifest["master_binary_sha256"]:
        raise SystemExit("master trace identity mismatch")
    deletes, inserts = read_trace(master); count = CHECKPOINTS[pct]
    cp_deletes, cp_inserts = deletes[:count], inserts[:count]
    directory.mkdir()
    trace_bin = directory / f"replace_cp{pct:02d}.bin"; trace_tsv = directory / f"replace_cp{pct:02d}.tsv"
    atomic_trace(trace_bin, cp_deletes, cp_inserts); atomic_tsv(trace_tsv, cp_deletes, cp_inserts)
    mask = np.ones(ACTIVE, dtype=np.bool_); mask[cp_deletes] = False
    active = np.sort(np.concatenate((np.flatnonzero(mask).astype("<u4"), cp_inserts))).astype("<u4")
    if active.size != ACTIVE or np.unique(active).size != ACTIVE:
        raise SystemExit("checkpoint active cardinality invalid")
    active_path = directory / f"active_cp{pct:02d}.tags.bin"; atomic_tags(active_path, active)
    positions = [j * (count - 1) // 8 for j in range(9)]
    probes = []
    for position in positions:
        probes.extend([
            {"ordinal": len(probes), "op_seq": position, "kind": "insert", "query_tag": int(cp_inserts[position]), "expected_tag": int(cp_inserts[position])},
            {"ordinal": len(probes) + 1, "op_seq": position, "kind": "delete", "query_tag": int(cp_deletes[position]), "forbidden_tag": int(cp_deletes[position])},
        ])
    probe_spec = {"schema": "dynamic-vamana-w1-trajectory-probes-v1", "checkpoint_pct": pct,
                  "replacement_count": count, "selection": "floor(j*(N-1)/8), j=0..8",
                  "positions": positions, "probe_count": 18, "probes": probes}
    (directory / "visibility_probes.json").write_text(json.dumps(probe_spec, indent=2) + "\n")
    report = {"schema": "dynamic-vamana-w1-trajectory-checkpoint-derivation-v1", "status": "pass",
              "checkpoint_pct": pct, "replacement_count": count, "master_trace_sha256": sha(master),
              "trace_sha256": sha(trace_bin), "trace_tsv_sha256": sha(trace_tsv),
              "active_tags_sha256": sha(active_path), "active_cardinality": ACTIVE,
              "active_tag_order": "strictly ascending", "probe_positions": positions,
              "delete_unique": np.unique(cp_deletes).size == count, "insert_unique": np.unique(cp_inserts).size == count,
              "delete_original_domain_only": bool(np.all(cp_deletes < 8_000_000)),
              "insert_pool_domain_only": bool(np.all((cp_inserts >= 8_000_000) & (cp_inserts < 10_000_000)))}
    if not all(report[key] is True for key in ("delete_unique", "insert_unique", "delete_original_domain_only", "insert_pool_domain_only")):
        raise SystemExit("checkpoint derivation semantic validation failed")
    (directory / "derivation_validation.json").write_text(json.dumps(report, indent=2) + "\n")
    durable_tree(directory)


if __name__ == "__main__": main()
