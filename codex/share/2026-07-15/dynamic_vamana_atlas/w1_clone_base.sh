#!/usr/bin/env bash
# Clone one immutable W0 index into a distinct NVMe W1 attempt directory.
set -euo pipefail

[[ ${W1_EXECUTE_AUTHORIZED:-0} == 1 || ${W1_FORMAL_PATH_AUTHORIZED:-0} == 1 ]] || { echo 'W1 gate not granted; refusing clone' >&2; exit 64; }
[[ $# == 3 ]] || { echo "usage: $0 SYSTEM BASE_INDEX_DIR ATTEMPT_DIR" >&2; exit 2; }
system=$1; base=$(realpath "$2"); target=$(realpath -m "$3")
root=$(realpath "${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}")
chat=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
case "$system" in DGAI|OdinANN) ;; *) echo "unsupported dynamic system: $system" >&2; exit 2;; esac
r03_expected="$root/formal/pilot3_sift10m_w1_r03/$system/cp01-03"
if [[ -n ${W1_ALLOWED_CLONE_SYSTEM:-} || -n ${W1_ALLOWED_CLONE_RUN:-} || -n ${W1_ALLOWED_CLONE_ATTEMPT:-} ]]; then
    for name in W1_ALLOWED_CLONE_TARGET W1_ALLOWED_CLONE_SYSTEM W1_ALLOWED_CLONE_RUN W1_ALLOWED_CLONE_ATTEMPT; do
      [[ -n ${!name:-} ]] || { echo "full clone capability missing: $name" >&2; exit 2; }
    done
    [[ $W1_ALLOWED_CLONE_RUN != */* && $W1_ALLOWED_CLONE_ATTEMPT != */* && $W1_ALLOWED_CLONE_SYSTEM != */* ]] || {
      echo 'clone capability components must be single path components' >&2; exit 2;
    }
    [[ $system == "$W1_ALLOWED_CLONE_SYSTEM" ]] || { echo 'system capability mismatch' >&2; exit 2; }
    expected_lexical="$root/formal/$W1_ALLOWED_CLONE_RUN/$W1_ALLOWED_CLONE_SYSTEM/$W1_ALLOWED_CLONE_ATTEMPT"
    expected_resolved=$(realpath -m "$expected_lexical")
    allowed_resolved=$(realpath -m "$W1_ALLOWED_CLONE_TARGET")
    [[ $expected_resolved == "$expected_lexical" ]] || { echo 'target parent contains a symlink escape' >&2; exit 2; }
    [[ $target == "$expected_lexical" && $target == "$allowed_resolved" ]] || {
      echo 'clone target/full capability mismatch' >&2; exit 2;
    }
    [[ $(basename "$target") == "$W1_ALLOWED_CLONE_ATTEMPT" ]] || { echo 'attempt basename mismatch' >&2; exit 2; }
else
  case "$target" in
    "$root"/formal/pilot3_w1_formal_path_replay_*/*/*) ;;
    "$root"/formal/pilot3_sift10m_w1/*/*) ;;
    "$r03_expected")
      [[ -n ${W1_ALLOWED_CLONE_TARGET:-} ]] || { echo 'R03 exact clone target capability absent' >&2; exit 2; }
      allowed=$(realpath -m "$W1_ALLOWED_CLONE_TARGET")
      [[ "$target" == "$allowed" && "$target" == "$r03_expected" ]] || { echo 'R03 clone target/capability mismatch' >&2; exit 2; }
      [[ $(basename "$target") == cp01-03 && $(basename "$(dirname "$target")") == "$system" ]] || { echo 'R03 system/attempt mismatch' >&2; exit 2; }
      ;;
    *) echo 'attempt must be under an explicit W1 replay, SIFT10M W1 path, or full capability' >&2; exit 2;;
  esac
fi
[[ -f "$base/IMMUTABLE_BASE_OK" || -f "$base/BUILD_OK" ]] || { echo "base lacks immutable/build marker: $base" >&2; exit 1; }
target_mount_probe=$target
while [[ ! -e $target_mount_probe ]]; do
  parent=$(dirname "$target_mount_probe")
  [[ $parent != "$target_mount_probe" ]] || { echo 'cannot resolve target mount ancestor' >&2; exit 1; }
  target_mount_probe=$parent
done
[[ $(findmnt -rn -T "$base" -o MAJ:MIN | awk 'NR==1{print;exit}') == "${ATLAS_NVME_MAJMIN:-259:10}" && $(findmnt -rn -T "$target_mount_probe" -o MAJ:MIN | awk 'NR==1{print;exit}') == "${ATLAS_NVME_MAJMIN:-259:10}" ]] || { echo 'base/target not on experiment NVMe' >&2; exit 1; }
[[ ! -e "$target" ]] || { echo "refusing to reuse/overwrite attempt: $target" >&2; exit 1; }
if [[ ${W1_CLONE_PREFLIGHT_ONLY:-0} == 1 ]]; then
  printf 'clone target preflight passed: system=%s target=%s\n' "$system" "$target"
  exit 0
fi
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
