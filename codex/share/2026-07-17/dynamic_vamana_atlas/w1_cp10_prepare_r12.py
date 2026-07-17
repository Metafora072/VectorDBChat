#!/usr/bin/env python3
"""Derive and freeze the exact CP05->CP10 400K delta for R12."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path

import numpy as np


def load_helpers(path: Path):
    spec = importlib.util.spec_from_file_location("w1_cumulative_prepare_r12_helpers", path)
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
        raise SystemExit("R12 derived input target is not fresh")
    if output.resolve(strict=False) != output:
        raise SystemExit("R12 derived input target is not canonical")

    h = load_helpers(args.helper.resolve(strict=True))
    dataset = root / "datasets/sift10m"
    trajectory = dataset / "w1_trajectory"
    master = trajectory / "master_replacements_1600k.bin"
    master_tsv = trajectory / "master_replacements_1600k.tsv"
    master_manifest = trajectory / "master_trace_manifest.json"
    cp05_trace = trajectory / "cp05/replace_cp05.bin"
    cp10_trace = trajectory / "cp10/replace_cp10.bin"
    cp05_active = trajectory / "cp05/active_cp05.tags.bin"
    cp10_active = trajectory / "cp10/active_cp10.tags.bin"
    cp05_manifest = trajectory / "cp05/checkpoint_manifest.json"
    cp10_manifest = trajectory / "cp10/checkpoint_manifest.json"
    cp10_probe_bin = trajectory / "cp10/visibility_probes.bin"
    cp10_probe_json = trajectory / "cp10/visibility_probes.json"
    full_path = dataset / "full_10m.bin"
    sources = [master, master_tsv, master_manifest, cp05_trace, cp10_trace,
               cp05_active, cp10_active, cp05_manifest, cp10_manifest,
               cp10_probe_bin, cp10_probe_json, full_path]
    identities = h.snapshot_sources(sources)

    deletes, inserts = h.read_trace(master)
    d05, i05 = h.read_trace(cp05_trace)
    d10, i10 = h.read_trace(cp10_trace)
    if deletes.size != 1_600_000 or d05.size != 400_000 or d10.size != 800_000:
        raise SystemExit("master/CP05/CP10 record counts differ from the frozen trajectory")
    if not (np.array_equal(d05, deletes[:400_000]) and np.array_equal(i05, inserts[:400_000])):
        raise SystemExit("frozen CP05 is not the first 400K master records")
    if not (np.array_equal(d10, deletes[:800_000]) and np.array_equal(i10, inserts[:800_000])):
        raise SystemExit("frozen CP10 is not the first 800K master records")

    delta_d = deletes[400_000:800_000].astype("<u4", copy=False)
    delta_i = inserts[400_000:800_000].astype("<u4", copy=False)
    if not (np.array_equal(np.concatenate((d05, delta_d)), d10)
            and np.array_equal(np.concatenate((i05, delta_i)), i10)):
        raise SystemExit("CP05 prefix plus R12 slice does not equal CP10 prefix")
    before = h.read_tags(cp05_active)
    expected = h.expected_active(before, delta_d, delta_i)
    frozen_cp10 = h.read_tags(cp10_active)
    if not np.array_equal(expected, frozen_cp10):
        raise SystemExit("CP05 plus R12 delta does not equal frozen CP10 active tags")

    output.mkdir(parents=True)
    full = h.vector_matrix(full_path)
    stage = h.write_stage(
        directory=output / "cp05_to_cp10", label="cp05_to_cp10",
        deletes=delta_d, inserts=delta_i, master_offset=400_000, full=full,
        expected_tags=None, checkpoint_deletes=None, checkpoint_inserts=None,
        checkpoint_positions=None, checkpoint_selection=None,
        source_identities=identities,
        frozen_global_probe_bin=cp10_probe_bin,
        frozen_global_probe_json=cp10_probe_json,
    )
    derived_d, derived_i = h.read_trace(output / "cp05_to_cp10/delta_cp05_to_cp10.bin")
    if not (np.array_equal(derived_d, delta_d) and np.array_equal(derived_i, delta_i)):
        raise SystemExit("derived R12 trace failed round-trip validation")
    manifest = {
        "schema": "dynamic-vamana-w1-cp10-r12-input-v1",
        "status": "pass",
        "classification": "input derivation only; exact master slice [400000:800000]",
        "master_record_range": [400_000, 800_000],
        "incremental_replacements": 400_000,
        "primitive_mutations": 800_000,
        "cp05_prefix_plus_delta_equals_cp10_prefix": True,
        "cp05_active_plus_delta_equals_cp10_active": True,
        "final_active_cardinality": int(frozen_cp10.size),
        "final_active_tags_sha256": h.sha256(cp10_active),
        "stage": stage,
        "sources": identities,
    }
    h.atomic_json(output / "input_manifest.json", manifest)
    h.fsync_tree(output)
    h.freeze_tree(output)
    os.sync()


if __name__ == "__main__":
    main()
