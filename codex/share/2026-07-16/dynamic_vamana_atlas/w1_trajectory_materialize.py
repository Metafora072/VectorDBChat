#!/usr/bin/env python3
"""Materialize and fully verify one trajectory checkpoint's vectors/probes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
from pathlib import Path

import numpy as np

from w1_trajectory_generate import durable_tree


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def head(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        raw = stream.read(8)
    if len(raw) != 8:
        raise ValueError(f"short header: {path}")
    return struct.unpack("<II", raw)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--checkpoint", type=int, choices=(5, 10, 20), required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    dataset, directory, pct = args.dataset.resolve(), args.directory.resolve(), args.checkpoint
    if directory.name != f"cp{pct:02d}" or not directory.is_dir():
        raise SystemExit("checkpoint directory identity mismatch")
    full = dataset / "full_10m.bin"
    tags_path = directory / f"active_cp{pct:02d}.tags.bin"
    vector_path = directory / f"active_cp{pct:02d}.bin"
    probe_path = directory / "visibility_probes.bin"
    validation_path = directory / "checkpoint_validation.json"
    manifest_path = directory / "checkpoint_manifest.json"
    if any(path.exists() for path in (vector_path, probe_path, validation_path, manifest_path)):
        raise SystemExit("checkpoint materialization overwrite refused")
    tag_n, tag_dim = head(tags_path); full_n, dim = head(full)
    if (tag_n, tag_dim) != (8_000_000, 1) or (full_n, dim) != (10_000_000, 128):
        raise SystemExit("checkpoint tag/full shape mismatch")
    tags = np.memmap(tags_path, dtype="<u4", mode="r", offset=8, shape=(tag_n,))
    corpus = np.memmap(full, dtype="<f4", mode="r", offset=8, shape=(full_n, dim))
    if int(tags.max()) >= full_n or np.unique(tags).size != tag_n or np.any(tags[1:] <= tags[:-1]):
        raise SystemExit("active tags are not unique ascending corpus tags")
    temporary = vector_path.with_name(vector_path.name + ".tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(struct.pack("<II", tag_n, dim))
            for start in range(0, tag_n, 16_384):
                np.asarray(corpus[tags[start:start + 16_384]], dtype="<f4").tofile(stream)
        os.replace(temporary, vector_path)
    finally:
        temporary.unlink(missing_ok=True)
    vn, vd = head(vector_path)
    vectors = np.memmap(vector_path, dtype="<f4", mode="r", offset=8, shape=(vn, vd))
    mapping_exact = True
    for start in range(0, tag_n, 16_384):
        if not np.array_equal(np.asarray(vectors[start:start + 16_384]),
                              np.asarray(corpus[tags[start:start + 16_384]])):
            mapping_exact = False; break
    if not mapping_exact:
        raise SystemExit("active vector row/tag mapping mismatch")
    spec = json.loads((directory / "visibility_probes.json").read_text())
    count = {5: 400_000, 10: 800_000, 20: 1_600_000}[pct]
    expected_positions = [j * (count - 1) // 8 for j in range(9)]
    probes = spec.get("probes", [])
    if spec.get("positions") != expected_positions or len(probes) != 18:
        raise SystemExit("visibility probe specification mismatch")
    probe_tags = np.asarray([int(row["query_tag"]) for row in probes], dtype="<u4")
    temporary = probe_path.with_name(probe_path.name + ".tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(struct.pack("<II", 18, dim)); np.asarray(corpus[probe_tags], dtype="<f4").tofile(stream)
        os.replace(temporary, probe_path)
    finally:
        temporary.unlink(missing_ok=True)
    pn, pd = head(probe_path)
    probe_vectors = np.memmap(probe_path, dtype="<f4", mode="r", offset=8, shape=(pn, pd))
    probe_mapping_exact = bool(np.array_equal(np.asarray(probe_vectors), np.asarray(corpus[probe_tags])))
    if not probe_mapping_exact:
        raise SystemExit("visibility probe row/tag mapping mismatch")
    validation = {"schema": "dynamic-vamana-w1-trajectory-checkpoint-validation-v1", "status": "pass",
                  "checkpoint_pct": pct, "active_cardinality": tag_n, "active_tags_unique": True,
                  "active_tags_order": "strictly ascending uint32", "active_vector_shape": [vn, vd],
                  "active_vector_row_tag_mapping_full_exact": mapping_exact, "probe_count": pn,
                  "probe_positions": expected_positions, "probe_vector_row_tag_mapping_full_exact": probe_mapping_exact,
                  "tag_zero_active": bool(np.any(tags == 0))}
    validation_path.write_text(json.dumps(validation, indent=2) + "\n")
    artifact_names = [f"replace_cp{pct:02d}.bin", f"replace_cp{pct:02d}.tsv", "derivation_validation.json",
                      f"active_cp{pct:02d}.tags.bin", f"active_cp{pct:02d}.bin",
                      "visibility_probes.bin", "visibility_probes.json", "checkpoint_validation.json"]
    artifacts = {name: {"size_bytes": (directory / name).stat().st_size, "sha256": sha(directory / name)}
                 for name in artifact_names}
    manifest = {"schema": "dynamic-vamana-w1-trajectory-checkpoint-manifest-v1", "status": "pass",
                "checkpoint_pct": pct, "replacement_count": count, "active_cardinality": tag_n,
                "artifact_directory": str(directory), "artifacts": artifacts}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    durable_tree(directory)


if __name__ == "__main__":
    main()
