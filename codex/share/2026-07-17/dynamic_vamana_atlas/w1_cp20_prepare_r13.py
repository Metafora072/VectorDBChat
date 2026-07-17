#!/usr/bin/env python3
"""Derive and freeze the exact CP10->CP20 800K delta for R13."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path

import numpy as np


def load_helpers(path: Path):
    spec = importlib.util.spec_from_file_location("w1_cumulative_prepare_r13_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load cumulative preparation helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve(strict=True)
    output = args.output_root.absolute()
    if output.exists() or output.is_symlink():
        raise SystemExit("R13 derived input target is not fresh")
    if output.resolve(strict=False) != output:
        raise SystemExit("R13 derived input target is not canonical")

    h = load_helpers(args.helper.resolve(strict=True))
    dataset = root / "datasets/sift10m"
    trajectory = dataset / "w1_trajectory"
    master = trajectory / "master_replacements_1600k.bin"
    master_tsv = trajectory / "master_replacements_1600k.tsv"
    master_manifest = trajectory / "master_trace_manifest.json"
    cp10_trace = trajectory / "cp10/replace_cp10.bin"
    cp20_trace = trajectory / "cp20/replace_cp20.bin"
    cp10_active = trajectory / "cp10/active_cp10.tags.bin"
    cp20_active = trajectory / "cp20/active_cp20.tags.bin"
    cp10_manifest = trajectory / "cp10/checkpoint_manifest.json"
    cp20_manifest = trajectory / "cp20/checkpoint_manifest.json"
    cp20_probe_bin = trajectory / "cp20/visibility_probes.bin"
    cp20_probe_json = trajectory / "cp20/visibility_probes.json"
    full_path = dataset / "full_10m.bin"
    sources = [master, master_tsv, master_manifest, cp10_trace, cp20_trace,
               cp10_active, cp20_active, cp10_manifest, cp20_manifest,
               cp20_probe_bin, cp20_probe_json, full_path]
    identities = h.snapshot_sources(sources)

    deletes, inserts = h.read_trace(master)
    d10, i10 = h.read_trace(cp10_trace)
    d20, i20 = h.read_trace(cp20_trace)
    if deletes.size != 1_600_000 or d10.size != 800_000 or d20.size != 1_600_000:
        raise SystemExit("master/CP10/CP20 record counts differ from the frozen trajectory")
    if not (np.array_equal(d10, deletes[:800_000]) and np.array_equal(i10, inserts[:800_000])):
        raise SystemExit("frozen CP10 is not the first 800K master records")
    if not (np.array_equal(d20, deletes[:1_600_000]) and np.array_equal(i20, inserts[:1_600_000])):
        raise SystemExit("frozen CP20 is not the first 1.6M master records")

    delta_d = deletes[800_000:1_600_000].astype("<u4", copy=False)
    delta_i = inserts[800_000:1_600_000].astype("<u4", copy=False)
    if not (np.array_equal(np.concatenate((d10, delta_d)), d20)
            and np.array_equal(np.concatenate((i10, delta_i)), i20)):
        raise SystemExit("CP10 prefix plus R13 slice does not equal CP20 prefix")
    before = h.read_tags(cp10_active)
    expected = h.expected_active(before, delta_d, delta_i)
    frozen_cp20 = h.read_tags(cp20_active)
    if not np.array_equal(expected, frozen_cp20):
        raise SystemExit("CP10 plus R13 delta does not equal frozen CP20 active tags")

    output.mkdir(parents=True)
    full = h.vector_matrix(full_path)
    stage = h.write_stage(
        directory=output / "cp10_to_cp20", label="cp10_to_cp20",
        deletes=delta_d, inserts=delta_i, master_offset=800_000, full=full,
        expected_tags=None, checkpoint_deletes=None, checkpoint_inserts=None,
        checkpoint_positions=None, checkpoint_selection=None,
        source_identities=identities,
        frozen_global_probe_bin=cp20_probe_bin,
        frozen_global_probe_json=cp20_probe_json,
    )
    derived_d, derived_i = h.read_trace(output / "cp10_to_cp20/delta_cp10_to_cp20.bin")
    if not (np.array_equal(derived_d, delta_d) and np.array_equal(derived_i, delta_i)):
        raise SystemExit("derived R13 trace failed round-trip validation")
    manifest = {
        "schema": "dynamic-vamana-w1-cp20-r13-input-v1",
        "status": "pass",
        "classification": "input derivation only; exact master slice [800000:1600000]",
        "master_record_range": [800_000, 1_600_000],
        "incremental_replacements": 800_000,
        "primitive_mutations": 1_600_000,
        "cp10_prefix_plus_delta_equals_cp20_prefix": True,
        "cp10_active_plus_delta_equals_cp20_active": True,
        "final_active_cardinality": int(frozen_cp20.size),
        "final_active_tags_sha256": h.sha256(cp20_active),
        "stage": stage,
        "sources": identities,
    }
    h.atomic_json(output / "input_manifest.json", manifest)
    h.fsync_tree(output)
    h.freeze_tree(output)
    os.sync()


if __name__ == "__main__":
    main()
