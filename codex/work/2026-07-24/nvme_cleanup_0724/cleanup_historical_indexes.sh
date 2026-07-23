#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---manifest}"
DATA_MOUNT="/home/ubuntu/pz/VectorDB/data"
EXPECTED_SOURCE="/dev/nvme8n1"
EXPECTED_COUNT=232
EXPECTED_BYTES=746728136704
TMP_TARGET="/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/tmp"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
MANIFEST="${SCRIPT_DIR}/index_dirs_before.tsv"
TARGETS_NUL="${SCRIPT_DIR}/index_dirs_before.nul"

ROOTS=(
  "/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/formal"
  "/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/z0b_sequence_endpoint_reclaim_0719/work"
  "/home/ubuntu/pz/VectorDB/data/VectorDB/runs/insert_cost_scale_substage/formal"
  "/home/ubuntu/pz/VectorDB/data/VectorDB/recovered_system_disk_20260711/runs/insert_cost_closure"
)

die() {
  echo "ERROR: $*" >&2
  exit 1
}

validate_environment() {
  local source
  source="$(findmnt -T "${DATA_MOUNT}" -n -o SOURCE | head -n 1)"
  [[ "${source}" == "${EXPECTED_SOURCE}" ]] ||
    die "unexpected source for ${DATA_MOUNT}: ${source}"
  [[ -d "${DATA_MOUNT}" && ! -L "${DATA_MOUNT}" ]] ||
    die "invalid data mount"

  local root
  for root in "${ROOTS[@]}"; do
    [[ "${root}" == "${DATA_MOUNT}/"* ]] || die "root outside data mount: ${root}"
    [[ -d "${root}" && ! -L "${root}" ]] || die "invalid root: ${root}"
  done

  [[ "${TMP_TARGET}" == "${DATA_MOUNT}/VectorDB/dynamic_vamana_atlas/tmp" ]] ||
    die "unexpected tmp target"
  [[ ! -e "${TMP_TARGET}" || ( -d "${TMP_TARGET}" && ! -L "${TMP_TARGET}" ) ]] ||
    die "invalid tmp target"
}

build_manifest() {
  : > "${TARGETS_NUL}"
  local root
  for root in "${ROOTS[@]}"; do
    find "${root}" -xdev -type d -name index -prune -print0 >> "${TARGETS_NUL}"
  done

  local count=0
  local unique_total=0
  local path bytes mtime
  printf 'standalone_allocated_bytes\tmtime_utc\tpath\n' > "${MANIFEST}"
  while IFS= read -r -d '' path; do
    [[ "${path##*/}" == "index" ]] || die "non-index target: ${path}"
    [[ -d "${path}" && ! -L "${path}" ]] || die "invalid index target: ${path}"
    bytes="$(du -x -B1 -s -- "${path}" | awk '{print $1}')"
    mtime="$(date -u -r "${path}" '+%Y-%m-%dT%H:%M:%SZ')"
    printf '%s\t%s\t%s\n' "${bytes}" "${mtime}" "${path}" >> "${MANIFEST}"
    count=$((count + 1))
  done < "${TARGETS_NUL}"

  [[ "${count}" -eq "${EXPECTED_COUNT}" ]] ||
    die "target count ${count}, expected ${EXPECTED_COUNT}"

  # A single du invocation deliberately deduplicates hard-linked inodes shared
  # by different run directories. Summing standalone per-directory values would
  # over-count those inodes.
  local -a targets=()
  mapfile -d '' -t targets < "${TARGETS_NUL}"
  unique_total="$(
    du -x -B1 -s -- "${targets[@]}" |
      awk '{total += $1} END {printf "%.0f", total}'
  )"
  [[ "${unique_total}" -eq "${EXPECTED_BYTES}" ]] ||
    die "unique target bytes ${unique_total}, expected ${EXPECTED_BYTES}"

  df -B1 "${DATA_MOUNT}" > "${SCRIPT_DIR}/df_before.txt"
  findmnt -T "${DATA_MOUNT}" > "${SCRIPT_DIR}/mount_before.txt"
  printf 'validated_count=%s\nvalidated_unique_bytes=%s\n' \
    "${count}" "${unique_total}"
}

path_is_approved() {
  local path="$1"
  local root
  [[ "${path##*/}" == "index" ]] || return 1
  for root in "${ROOTS[@]}"; do
    [[ "${path}" == "${root}/"* ]] && return 0
  done
  return 1
}

delete_targets() {
  build_manifest

  local deleted_count=0
  local bytes mtime path
  while IFS=$'\t' read -r bytes mtime path; do
    [[ "${bytes}" == "standalone_allocated_bytes" ]] && continue
    path_is_approved "${path}" || die "unapproved manifest path: ${path}"
    [[ -d "${path}" && ! -L "${path}" ]] || die "target changed: ${path}"
    rm -rf -- "${path}"
    deleted_count=$((deleted_count + 1))
  done < "${MANIFEST}"

  [[ "${deleted_count}" -eq "${EXPECTED_COUNT}" ]] ||
    die "deleted count ${deleted_count}, expected ${EXPECTED_COUNT}"

  if [[ -e "${TMP_TARGET}" ]]; then
    [[ "${TMP_TARGET}" == "${DATA_MOUNT}/VectorDB/dynamic_vamana_atlas/tmp" ]] ||
      die "tmp target string changed"
    [[ -d "${TMP_TARGET}" && ! -L "${TMP_TARGET}" ]] ||
      die "tmp target changed"
    rm -rf -- "${TMP_TARGET}"
  fi

  df -B1 "${DATA_MOUNT}" > "${SCRIPT_DIR}/df_after.txt"
  printf 'deleted_count=%s\nvalidated_unique_index_bytes=%s\ntmp_target=%s\n' \
    "${deleted_count}" "${EXPECTED_BYTES}" "${TMP_TARGET}" \
    > "${SCRIPT_DIR}/cleanup_summary.txt"
}

validate_environment
case "${MODE}" in
  --manifest)
    build_manifest
    ;;
  --delete)
    delete_targets
    ;;
  *)
    die "usage: $0 [--manifest|--delete]"
    ;;
esac
