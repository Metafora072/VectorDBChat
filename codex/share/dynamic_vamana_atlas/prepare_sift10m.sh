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
CONVERSION_MANIFEST="$RAW/conversion_provenance.json"
BASE_ROWS=10000000
QUERY_ROWS=${SIFT10M_QUERY_ROWS:-10000}
SEED=20260713

fail() { echo "prepare_sift10m: $*" >&2; exit 1; }
notify_owner() {
  [[ "${ATLAS_NOTIFY_EMAIL:-1}" == 1 ]] || return 0
  "$CHAT/formal/notify_owner.sh" "$1" "$2" || true
}
on_error() {
  local code=$?
  notify_owner "Dynamic Vamana SIFT10M preparation failed" "exit=$code root=$ROOT"
  exit "$code"
}
trap on_error ERR
require_nvme_path() {
  local canonical probe source majmin
  canonical=$(realpath -m "$1")
  case "$canonical" in
    /home/ubuntu/pz/VectorDB/data|/home/ubuntu/pz/VectorDB/data/*) ;;
    *) fail "refusing non-NVMe path: $1" ;;
  esac
  probe=$canonical
  while [[ ! -e "$probe" ]]; do probe=$(dirname "$probe"); done
  source=$(findmnt -rn -T "$probe" -o SOURCE | head -n1)
  majmin=$(findmnt -rn -T "$probe" -o MAJ:MIN | head -n1)
  [[ "$source" == "${ATLAS_NVME_SOURCE:-/dev/nvme8n1}" && "$majmin" == "${ATLAS_NVME_MAJMIN:-259:10}" ]] \
    || fail "path is not the expected experiment NVMe: $canonical ($source $majmin)"
}
check_free_space() {
  local free
  free=$(df -PB1 "$ROOT" | awk 'NR==2 {print $4}')
  [[ "$free" =~ ^[0-9]+$ ]] || fail "cannot determine free space"
  (( free >= ${ATLAS_MIN_FREE_BYTES:-300000000000} )) \
    || fail "NVMe free bytes $free below preparation guard"
}
download_if_missing() {
  local destination=$1 url=$2
  [[ -f "$destination" ]] && return 0
  [[ -n "$url" ]] || fail "missing $destination; set the corresponding SIFT10M_*_URL or *_INPUT"
  command -v curl >/dev/null || fail "curl is required to fetch an explicitly supplied source URL"
  mkdir -p "$(dirname "$destination")"
  if [[ -f "${destination}.partial.url" ]] && [[ "$(<"${destination}.partial.url")" != "$url" ]]; then
    fail "refusing to resume a partial download from a different URL: $destination"
  fi
  printf '%s' "$url" >"${destination}.partial.url"
  curl --fail --location --continue-at - --output "${destination}.partial" "$url"
  mv "${destination}.partial" "$destination"
  rm -f "${destination}.partial.url"
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
check_free_space

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
provenance_args=(--base-source "$base_input" --query-source "$query_input" \
  --base-fbin "$base_fbin" --query-fbin "$query_fbin" \
  --base-expected-sha256 "${SIFT10M_BASE_EXPECTED_SHA256:-}" \
  --query-expected-sha256 "${SIFT10M_QUERY_EXPECTED_SHA256:-}")

if [[ -f "$DATASET/DATA_PREPARED_OK" ]]; then
  [[ -f "$DATASET/manifest.json" && -f "$MANIFEST" ]] || fail "incomplete prepared marker; refuse overwrite"
  python3 "$CHAT/sift10m_provenance.py" verify --manifest "$MANIFEST" "${provenance_args[@]}"
  echo "already prepared and provenance-verified: $DATASET"
  exit 0
fi

if [[ -e "$base_fbin" || -e "$query_fbin" ]]; then
  [[ -f "$CONVERSION_MANIFEST" ]] || fail "canonical file exists without conversion provenance; refuse reuse"
  python3 "$CHAT/sift10m_provenance.py" verify --manifest "$CONVERSION_MANIFEST" "${provenance_args[@]}"
else
  check_free_space
  materialize_bvecs "$base_input" "$base_fbin" "$BASE_ROWS"
  materialize_bvecs "$query_input" "$query_fbin" "$QUERY_ROWS"
  python3 "$CHAT/sift10m_provenance.py" record --manifest "$CONVERSION_MANIFEST" \
    "${provenance_args[@]}" --base-url "${SIFT10M_BASE_URL:-}" --query-url "${SIFT10M_QUERY_URL:-}"
fi

if [[ -e "$DATASET/manifest.json" || -n "$(find "$DATASET" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  fail "dataset directory is non-empty without DATA_PREPARED_OK; choose a new ATLAS_ROOT or inspect it manually"
fi

check_free_space
python3 "$CHAT/prepare_dataset.py" \
  --name sift10m --source "$base_fbin" --query "$query_fbin" --output "$DATASET" \
  --total "$BASE_ROWS" --active 8000000 --seed "$SEED" --full-name full_10m.bin
python3 "$CHAT/prepare_update_smoke.py" --dataset "$DATASET" --count 100
python3 "$CHAT/hash_manifest.py" "$DATASET" "$ROOT/manifests/sift10m_dataset_sha256.json"

python3 "$CHAT/sift10m_provenance.py" record --manifest "$MANIFEST" \
  "${provenance_args[@]}" --base-url "${SIFT10M_BASE_URL:-}" --query-url "${SIFT10M_QUERY_URL:-}"
touch "$DATASET/DATA_PREPARED_OK"
notify_owner "Dynamic Vamana SIFT10M preparation complete" "dataset=$DATASET manifest=$MANIFEST"
echo "prepared: $DATASET"
