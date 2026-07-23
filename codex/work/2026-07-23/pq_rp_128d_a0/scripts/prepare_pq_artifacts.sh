#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/ubuntu/pz/VectorDB/chat
DATA=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/datasets/sift1m/full_1m.bin
P10=/home/ubuntu/pz/VectorDB/data/VectorDB/p10_pq_corridor_a0_0723
OUT=/home/ubuntu/pz/VectorDB/data/VectorDB/pq_rp_128d_a0_0723
GRAPH="$ROOT/codex/work/2026-07-22/p07_page_bonus_a0/index/sift1m_disk.index"
GEN="$ROOT/codex/work/2026-07-22/p07_page_bonus_a0/trace_build/apps/utils/generate_pq"

mkdir -p "$OUT"

if [[ ! -e "$OUT/sift1m_pq16_pq_pivots.bin" ]]; then
    ln -s "$P10/sift1m_pq16_pq_pivots.bin" "$OUT/sift1m_pq16_pq_pivots.bin"
fi
if [[ ! -e "$OUT/sift1m_pq16_pq_compressed.bin" ]]; then
    ln -s "$P10/sift1m_pq16_pq_compressed.bin" "$OUT/sift1m_pq16_pq_compressed.bin"
fi

for bytes in 8 32; do
    prefix="$OUT/sift1m_pq${bytes}"
    if [[ ! -s "${prefix}_pq_pivots.bin" || ! -s "${prefix}_pq_compressed.bin" ]]; then
        "$GEN" float "$DATA" "$prefix" "$bytes" 0.1 0
    fi
done

for bytes in 8 16 32; do
    link="$OUT/sift1m_pq${bytes}_disk.index"
    if [[ ! -e "$link" ]]; then
        ln -s "$GRAPH" "$link"
    fi
done

python3 - "$OUT" <<'PY'
import json
import os
import struct
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest = {}
for code in (8, 16, 32):
    prefix = root / f"sift1m_pq{code}"
    compressed = Path(str(prefix) + "_pq_compressed.bin")
    with compressed.open("rb") as handle:
        rows, dim = struct.unpack("<II", handle.read(8))
    disk = Path(str(prefix) + "_disk.index")
    manifest[str(code)] = {
        "prefix": str(prefix),
        "points": rows,
        "code_bytes": dim,
        "pq_resident_bytes": compressed.stat().st_size - 8,
        "disk_index_realpath": os.path.realpath(disk),
        "disk_index_bytes": disk.stat().st_size,
    }
(root / "artifact_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
print(json.dumps(manifest, indent=2, sort_keys=True))
PY

