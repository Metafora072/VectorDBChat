#!/usr/bin/env bash
# Lightweight source-format gate; it never requests the 10M prefix.
set -euo pipefail

ROOT=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
CHAT=${ATLAS_CHAT_ROOT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas}
BASE_URL=${SIFT10M_BASE_URL:-https://dl.fbaipublicfiles.com/billion-scale-ann-benchmarks/bigann/base.1B.u8bin}
OUT="$ROOT/results/pilot3_sift10m/source_canary"
RAW="$OUT/base.first2.raw.u8bin"
NORMALIZED="$OUT/base.first2.normalized.u8bin"
FBIN="$OUT/base.first2.fbin"

case "$(realpath -m "$ROOT")" in /home/ubuntu/pz/VectorDB/data|/home/ubuntu/pz/VectorDB/data/*) ;; *) exit 2 ;; esac
mkdir -p "$OUT"
python3 "$CHAT/download_u8bin_prefix.py" --url "$BASE_URL" --output "$RAW" --bytes 264 \
  --report "$OUT/download.json"
python3 "$CHAT/convert_u8bin_to_fbin.py" normalize --input "$RAW" --output "$NORMALIZED" \
  --source-rows 1000000000 --rows 2 --dimension 128 --report "$OUT/normalization.json"
python3 "$CHAT/convert_u8bin_to_fbin.py" convert --input "$NORMALIZED" --output "$FBIN" \
  --rows 2 --dimension 128 --report "$OUT/conversion.json"
python3 - "$RAW" "$NORMALIZED" "$FBIN" <<'PY'
import struct
import sys
from pathlib import Path
import numpy as np

raw, normalized, fbin = map(Path, sys.argv[1:])
assert struct.unpack("<II", raw.read_bytes()[:8]) == (1_000_000_000, 128)
assert struct.unpack("<II", normalized.read_bytes()[:8]) == (2, 128)
assert raw.read_bytes()[8:] == normalized.read_bytes()[8:]
values = np.fromfile(fbin, dtype="<f4", offset=8).reshape(2, 128)
source = np.frombuffer(raw.read_bytes()[8:], dtype=np.uint8).reshape(2, 128)
assert np.array_equal(values, source.astype("<f4"))
PY
touch "$OUT/SOURCE_CANARY_OK"
echo "u8bin source canary passed: $OUT"
