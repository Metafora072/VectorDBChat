#!/usr/bin/env bash
# Prepare only the approved standard BIGANN/SIFT10M data artifacts. This script
# deliberately has no default URL: the operator must record the licensed source
# URL or provide already-downloaded standard .bvecs files.
set -euo pipefail

ROOT=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
CHAT=${ATLAS_CHAT_ROOT:-/home/ubuntu/pz/VectorDB/chat/codex/share/dynamic_vamana_atlas}
DATASET="$ROOT/datasets/sift10m"
RAW="$ROOT/raw/sift10m"
MANIFEST="$ROOT/manifests/sift10m_preparation.json"
BASE_ROWS=10000000
QUERY_ROWS=${SIFT10M_QUERY_ROWS:-10000}
SEED=20260713

fail() { echo "prepare_sift10m: $*" >&2; exit 1; }
require_nvme_path() {
  case "$1" in
    /home/ubuntu/pz/VectorDB/data/*) ;;
    *) fail "refusing non-NVMe path: $1" ;;
  esac
}
download_if_missing() {
  local destination=$1 url=$2
  [[ -f "$destination" ]] && return 0
  [[ -n "$url" ]] || fail "missing $destination; set the corresponding SIFT10M_*_URL or *_INPUT"
  command -v curl >/dev/null || fail "curl is required to fetch an explicitly supplied source URL"
  mkdir -p "$(dirname "$destination")"
  curl --fail --location --continue-at - --output "${destination}.partial" "$url"
  mv "${destination}.partial" "$destination"
}
materialize_bvecs() {
  local input=$1 output=$2 rows=$3
  [[ -f "$output" ]] && return 0
  python3 "$CHAT/convert_bvecs_to_fbin.py" \
    --input "$input" --output "$output" --rows "$rows" --dimension 128
}

require_nvme_path "$ROOT"
require_nvme_path "$RAW"
require_nvme_path "$DATASET"
export TMPDIR="$ROOT/tmp/sift10m-preparation"
require_nvme_path "$TMPDIR"
mkdir -p "$RAW" "$DATASET" "$ROOT/manifests" "$TMPDIR"

if [[ -f "$DATASET/DATA_PREPARED_OK" ]]; then
  [[ -f "$DATASET/manifest.json" && -f "$MANIFEST" ]] || fail "incomplete prepared marker; refuse overwrite"
  echo "already prepared: $DATASET"
  exit 0
fi

base_input=${SIFT10M_BASE_INPUT:-$RAW/bigann_base.bvecs}
query_input=${SIFT10M_QUERY_INPUT:-$RAW/bigann_query.bvecs}
if [[ ! -f "$base_input" ]]; then
  base_input="$RAW/bigann_base.bvecs"
  download_if_missing "$base_input" "${SIFT10M_BASE_URL:-}"
fi
if [[ ! -f "$query_input" ]]; then
  query_input="$RAW/bigann_query.bvecs"
  download_if_missing "$query_input" "${SIFT10M_QUERY_URL:-}"
fi
[[ "$base_input" == *.bvecs ]] || fail "only standard .bvecs input is accepted by this guarded preparation script"
[[ "$query_input" == *.bvecs ]] || fail "only standard .bvecs query input is accepted by this guarded preparation script"

base_fbin="$RAW/base.10m.fbin"
query_fbin="$RAW/query.fbin"
materialize_bvecs "$base_input" "$base_fbin" "$BASE_ROWS"
materialize_bvecs "$query_input" "$query_fbin" "$QUERY_ROWS"

if [[ -e "$DATASET/manifest.json" || -n "$(find "$DATASET" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  fail "dataset directory is non-empty without DATA_PREPARED_OK; choose a new ATLAS_ROOT or inspect it manually"
fi

python3 "$CHAT/prepare_dataset.py" \
  --name sift10m --source "$base_fbin" --query "$query_fbin" --output "$DATASET" \
  --total "$BASE_ROWS" --active 8000000 --seed "$SEED" --full-name full_10m.bin
python3 "$CHAT/prepare_update_smoke.py" --dataset "$DATASET" --count 100
python3 "$CHAT/hash_manifest.py" "$DATASET" "$ROOT/manifests/sift10m_dataset_sha256.json"

python3 - "$MANIFEST" "$base_input" "$query_input" "$base_fbin" "$query_fbin" <<'PY'
import json, os, sys, time
from pathlib import Path

output, base_source, query_source, base_fbin, query_fbin = map(Path, sys.argv[1:])
payload = {
    "schema": "dynamic-vamana-sift10m-preparation-v1",
    "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "corpus": "standard BIGANN/SIFT prefix, first 10,000,000 vectors",
    "base_source": str(base_source),
    "query_source": str(query_source),
    "base_source_url": os.environ.get("SIFT10M_BASE_URL"),
    "query_source_url": os.environ.get("SIFT10M_QUERY_URL"),
    "base_fbin": str(base_fbin),
    "query_fbin": str(query_fbin),
    "base_source_bytes": base_source.stat().st_size,
    "query_source_bytes": query_source.stat().st_size,
    "base_fbin_bytes": base_fbin.stat().st_size,
    "query_fbin_bytes": query_fbin.stat().st_size,
    "seed": 20260713,
}
output.write_text(json.dumps(payload, indent=2) + "\n")
PY
touch "$DATASET/DATA_PREPARED_OK"
echo "prepared: $DATASET"
