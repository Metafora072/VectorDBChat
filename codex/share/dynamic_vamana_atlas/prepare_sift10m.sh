#!/usr/bin/env bash
# Prepare the approved BIGANN/SIFT10M corpus without writing outside experiment NVMe.
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
FORMAT=${SIFT10M_SOURCE_FORMAT:-u8bin}
OFFICIAL_BASE_URL=https://dl.fbaipublicfiles.com/billion-scale-ann-benchmarks/bigann/base.1B.u8bin
OFFICIAL_QUERY_URL=https://dl.fbaipublicfiles.com/billion-scale-ann-benchmarks/bigann/query.public.10K.u8bin

fail() { echo "prepare_sift10m: $*" >&2; exit 1; }
notify_owner() {
  [[ "${ATLAS_NOTIFY_EMAIL:-1}" == 1 ]] || return 0
  "$CHAT/formal/notify_owner.sh" "$1" "$2" || true
}
on_error() {
  local code=$?
  notify_owner "Dynamic Vamana SIFT10M preparation failed" "exit=$code root=$ROOT source_format=$FORMAT"
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
download_bvecs_if_missing() {
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
  python3 "$CHAT/convert_bvecs_to_fbin.py" --input "$1" --output "$2" --rows "$3" --dimension 128
}

require_nvme_path "$ROOT"
require_nvme_path "$RAW"
require_nvme_path "$DATASET"
export TMPDIR="$ROOT/tmp/sift10m-preparation"
require_nvme_path "$TMPDIR"
mkdir -p "$RAW" "$DATASET" "$ROOT/manifests" "$TMPDIR"
check_free_space

if [[ -f "$DATASET/DATA_PREPARED_OK" ]]; then
  [[ -f "$DATASET/manifest.json" && -f "$MANIFEST" ]] || fail "incomplete prepared marker; refuse overwrite"
  python3 "$CHAT/sift10m_provenance.py" verify-recorded --manifest "$MANIFEST"
  echo "already prepared and provenance-verified: $DATASET"
  exit 0
fi

base_fbin="$RAW/base.10m.fbin"
query_fbin="$RAW/query.fbin"
provenance_args=()

case "$FORMAT" in
  u8bin)
    base_url=${SIFT10M_BASE_URL:-$OFFICIAL_BASE_URL}
    query_url=${SIFT10M_QUERY_URL:-$OFFICIAL_QUERY_URL}
    base_input=${SIFT10M_BASE_INPUT:-$RAW/base.1B.prefix10m.u8bin}
    query_input=${SIFT10M_QUERY_INPUT:-$RAW/query.public.10K.u8bin}
    base_report="$RAW/base.1B.prefix10m.download.json"
    query_report="$RAW/query.public.10K.download.json"
    base_normalized="$RAW/base.10M.u8bin"
    query_normalized="$RAW/query.10K.u8bin"
    base_normalization="$RAW/base.10M.normalization.json"
    query_normalization="$RAW/query.10K.normalization.json"
    base_conversion="$RAW/base.10M.conversion.json"
    query_conversion="$RAW/query.10K.conversion.json"
    python3 "$CHAT/download_u8bin_prefix.py" --url "$base_url" --output "$base_input" \
      --bytes 1280000008 --report "$base_report"
    python3 "$CHAT/download_u8bin_prefix.py" --url "$query_url" --output "$query_input" \
      --bytes 1280008 --report "$query_report"
    check_free_space
    python3 "$CHAT/convert_u8bin_to_fbin.py" normalize --input "$base_input" --output "$base_normalized" \
      --source-rows 1000000000 --rows "$BASE_ROWS" --dimension 128 --report "$base_normalization"
    python3 "$CHAT/convert_u8bin_to_fbin.py" normalize --input "$query_input" --output "$query_normalized" \
      --source-rows "$QUERY_ROWS" --rows "$QUERY_ROWS" --dimension 128 --report "$query_normalization"
    python3 "$CHAT/convert_u8bin_to_fbin.py" convert --input "$base_normalized" --output "$base_fbin" \
      --rows "$BASE_ROWS" --dimension 128 --report "$base_conversion"
    python3 "$CHAT/convert_u8bin_to_fbin.py" convert --input "$query_normalized" --output "$query_fbin" \
      --rows "$QUERY_ROWS" --dimension 128 --report "$query_conversion"
    review_status=official-benchmark-source
    [[ "$base_url" == "$OFFICIAL_BASE_URL" && "$query_url" == "$OFFICIAL_QUERY_URL" ]] || review_status='operator-reviewed mirror'
    provenance_args=(--base-source "$base_input" --query-source "$query_input" --base-fbin "$base_fbin" --query-fbin "$query_fbin" \
      --base-expected-sha256 "${SIFT10M_BASE_EXPECTED_SHA256:-}" --query-expected-sha256 "${SIFT10M_QUERY_EXPECTED_SHA256:-}" \
      --source-format u8bin --source-review-status "$review_status" --base-normalized-u8bin "$base_normalized" --query-normalized-u8bin "$query_normalized" \
      --base-download-report "$base_report" --query-download-report "$query_report" --base-normalization-report "$base_normalization" --query-normalization-report "$query_normalization" \
      --base-conversion-report "$base_conversion" --query-conversion-report "$query_conversion" --conversion-tool "$CHAT/convert_u8bin_to_fbin.py" \
      --conversion-command 'uint8 value-preserving to float32; no normalization/reordering')
    record_base_url=$base_url
    record_query_url=$query_url
    ;;
  bvecs)
    base_input=${SIFT10M_BASE_INPUT:-$RAW/bigann_base.bvecs}
    query_input=${SIFT10M_QUERY_INPUT:-$RAW/bigann_query.bvecs}
    [[ -f "$base_input" ]] || download_bvecs_if_missing "$base_input" "${SIFT10M_BASE_URL:-}"
    [[ -f "$query_input" ]] || download_bvecs_if_missing "$query_input" "${SIFT10M_QUERY_URL:-}"
    [[ "$base_input" == *.bvecs && "$query_input" == *.bvecs ]] || fail "bvecs mode requires .bvecs inputs"
    materialize_bvecs "$base_input" "$base_fbin" "$BASE_ROWS"
    materialize_bvecs "$query_input" "$query_fbin" "$QUERY_ROWS"
    provenance_args=(--base-source "$base_input" --query-source "$query_input" --base-fbin "$base_fbin" --query-fbin "$query_fbin" \
      --base-expected-sha256 "${SIFT10M_BASE_EXPECTED_SHA256:-}" --query-expected-sha256 "${SIFT10M_QUERY_EXPECTED_SHA256:-}")
    record_base_url=${SIFT10M_BASE_URL:-}
    record_query_url=${SIFT10M_QUERY_URL:-}
    ;;
  *) fail "unsupported SIFT10M_SOURCE_FORMAT=$FORMAT (expected u8bin or bvecs)" ;;
esac

# Conversion is completed above before this point.  Record its provenance now;
# interrupted preparations are safely recomputed rather than trusted by name.
python3 "$CHAT/sift10m_provenance.py" record --manifest "$CONVERSION_MANIFEST" "${provenance_args[@]}" \
  --base-url "$record_base_url" --query-url "$record_query_url"

if [[ -e "$DATASET/manifest.json" || -n "$(find "$DATASET" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  fail "dataset directory is non-empty without DATA_PREPARED_OK; choose a new ATLAS_ROOT or inspect it manually"
fi

check_free_space
python3 "$CHAT/prepare_dataset.py" --name sift10m --source "$base_fbin" --query "$query_fbin" --output "$DATASET" \
  --total "$BASE_ROWS" --active 8000000 --seed "$SEED" --full-name full_10m.bin
python3 "$CHAT/prepare_update_smoke.py" --dataset "$DATASET" --count 100
python3 "$CHAT/hash_manifest.py" "$DATASET" "$ROOT/manifests/sift10m_dataset_sha256.json"
python3 "$CHAT/sift10m_provenance.py" record --manifest "$MANIFEST" "${provenance_args[@]}" \
  --base-url "$record_base_url" --query-url "$record_query_url"
touch "$DATASET/DATA_PREPARED_OK"
notify_owner "Dynamic Vamana SIFT10M preparation complete" "dataset=$DATASET manifest=$MANIFEST source_format=$FORMAT"
echo "prepared: $DATASET"
