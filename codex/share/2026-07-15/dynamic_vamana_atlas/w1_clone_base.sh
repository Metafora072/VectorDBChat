#!/usr/bin/env bash
# Clone one immutable W0 index into a distinct NVMe W1 attempt directory.
set -euo pipefail

[[ ${W1_EXECUTE_AUTHORIZED:-0} == 1 ]] || { echo 'W1 gate not granted; refusing clone' >&2; exit 64; }
[[ $# == 2 ]] || { echo "usage: $0 SYSTEM ATTEMPT_DIR" >&2; exit 2; }
system=$1; target=$(realpath -m "$2")
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
case "$target" in "$root"/formal/pilot3_sift10m_w1/*) ;; *) echo 'attempt must be under formal/pilot3_sift10m_w1' >&2; exit 2;; esac
case "$system" in
  DGAI) base="$root/formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index";;
  OdinANN) base="$root/formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index";;
  *) echo "unsupported dynamic system: $system" >&2; exit 2;;
esac
[[ -f "$base/IMMUTABLE_BASE_OK" ]] || { echo "base is not immutable: $base" >&2; exit 1; }
[[ ! -e "$target" ]] || { echo "refusing to reuse/overwrite attempt: $target" >&2; exit 1; }
mkdir -p "$(dirname "$target")"
tmp="${target}.partial.$$"; trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp"
find "$base" -type f -printf '%P\t%s\t' -exec sha256sum {} \; >"${tmp}.base_before.tsv"
if ! cp -a --reflink=always "$base/." "$tmp/index" 2>/dev/null; then
  rm -rf "$tmp/index"; cp -a --reflink=auto "$base/." "$tmp/index"
  clone_mode=copy_or_filesystem_reflink_auto
else
  clone_mode=reflink
fi
find "$base" -type f -printf '%P\t%s\t' -exec sha256sum {} \; >"${tmp}.base_after.tsv"
cmp -s "${tmp}.base_before.tsv" "${tmp}.base_after.tsv" || { echo 'base hash changed during clone' >&2; exit 1; }
find "$tmp/index" -type f -printf '%P\t%s\t' -exec sha256sum {} \; >"${tmp}.clone_initial.tsv"
printf 'schema=dynamic-vamana-w1-clone-v1\nsystem=%s\nclone_mode=%s\nbase=%s\n' "$system" "$clone_mode" "$base" >"${tmp}.clone_manifest.txt"
mv "$tmp" "$target"; trap - EXIT
