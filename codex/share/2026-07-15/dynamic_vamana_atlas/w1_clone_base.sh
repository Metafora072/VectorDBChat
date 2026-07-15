#!/usr/bin/env bash
# Clone one immutable W0 index into a distinct NVMe W1 attempt directory.
set -euo pipefail

[[ ${W1_EXECUTE_AUTHORIZED:-0} == 1 || ${W1_FORMAL_PATH_AUTHORIZED:-0} == 1 ]] || { echo 'W1 gate not granted; refusing clone' >&2; exit 64; }
[[ $# == 3 ]] || { echo "usage: $0 SYSTEM BASE_INDEX_DIR ATTEMPT_DIR" >&2; exit 2; }
system=$1; base=$(realpath "$2"); target=$(realpath -m "$3")
root=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
case "$target" in
  "$root"/formal/pilot3_w1_formal_path_replay_*/*/*) ;;
  "$root"/formal/pilot3_sift10m_w1/*/*) ;;
  *) echo 'attempt must be under an explicit W1 replay or SIFT10M W1 path' >&2; exit 2;;
esac
case "$system" in DGAI|OdinANN) ;; *) echo "unsupported dynamic system: $system" >&2; exit 2;; esac
[[ -f "$base/IMMUTABLE_BASE_OK" || -f "$base/BUILD_OK" ]] || { echo "base lacks immutable/build marker: $base" >&2; exit 1; }
[[ $(findmnt -rn -T "$base" -o MAJ:MIN | awk 'NR==1{print;exit}') == "${ATLAS_NVME_MAJMIN:-259:10}" && $(findmnt -rn -T "$(dirname "$target")" -o MAJ:MIN | awk 'NR==1{print;exit}') == "${ATLAS_NVME_MAJMIN:-259:10}" ]] || { echo 'base/target not on experiment NVMe' >&2; exit 1; }
[[ ! -e "$target" ]] || { echo "refusing to reuse/overwrite attempt: $target" >&2; exit 1; }
mkdir -p "$(dirname "$target")"
tmp="${target}.partial.$$"; trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp"
python3 "$chat/w1_file_manifest.py" --root "$base" --output "$tmp/base_before.tsv"
if ! cp -a --reflink=always "$base/." "$tmp/index" 2>/dev/null; then
  rm -rf "$tmp/index"; cp -a --reflink=auto "$base/." "$tmp/index"
  clone_mode=copy_or_filesystem_reflink_auto
else
  clone_mode=reflink
fi
python3 "$chat/w1_file_manifest.py" --root "$base" --output "$tmp/base_after.tsv"
cmp -s "$tmp/base_before.tsv" "$tmp/base_after.tsv" || { echo 'base hash changed during clone' >&2; exit 1; }
python3 "$chat/w1_file_manifest.py" --root "$tmp/index" --output "$tmp/clone_initial.tsv"
cmp -s "$tmp/base_before.tsv" "$tmp/clone_initial.tsv" || { echo 'clone/base content manifest mismatch' >&2; exit 1; }
printf '{"schema":"dynamic-vamana-w1-clone-v2","system":"%s","clone_mode":"%s","base":"%s"}\n' "$system" "$clone_mode" "$base" >"$tmp/clone_manifest.json"
mv "$tmp" "$target"; trap - EXIT
