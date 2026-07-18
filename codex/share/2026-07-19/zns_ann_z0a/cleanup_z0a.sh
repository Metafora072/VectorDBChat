#!/usr/bin/env bash
set -euo pipefail

# Safe deletion helper for explicitly named, marker-owned Z0A run trees only.
# It is dry-run unless --execute is supplied.  No glob or parent cleanup exists.

PRODUCTION_ROOT=/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas/z0a_trace_model_preflight_0719
PRODUCTION_DEVICE=259:10
ROOT=$PRODUCTION_ROOT
EXPECTED_DEVICE=$PRODUCTION_DEVICE
EXECUTE=0
declare -a REQUESTED_PATHS=()

usage() {
  echo "usage: $0 [--execute] --path ABSOLUTE_Z0A_OWNED_DIRECTORY [--path ...]" >&2
  exit 64
}

while (($#)); do
  case "$1" in
    --execute) EXECUTE=1; shift ;;
    --path)
      (($# >= 2)) || usage
      REQUESTED_PATHS+=("$2")
      shift 2
      ;;
    *) usage ;;
  esac
done

((${#REQUESTED_PATHS[@]} > 0)) || usage

# Self-test is intentionally restricted to a /tmp directory with a distinctive
# prefix.  Production callers cannot override ROOT or EXPECTED_DEVICE.
if [[ ${Z0A_CLEANUP_SELFTEST_ROOT:-} ]]; then
  [[ $Z0A_CLEANUP_SELFTEST_ROOT == /tmp/z0a-cleanup-selftest.* ]] || {
    echo "cleanup_z0a: invalid self-test root" >&2
    exit 65
  }
  ROOT=$Z0A_CLEANUP_SELFTEST_ROOT
  [[ -d $ROOT && ! -L $ROOT ]] || { echo "cleanup_z0a: self-test root absent" >&2; exit 65; }
  EXPECTED_DEVICE=$(findmnt -rn -T "$ROOT" -o MAJ:MIN | tail -n 1)
fi

[[ -d $ROOT && ! -L $ROOT ]] || { echo "cleanup_z0a: root absent or symlink: $ROOT" >&2; exit 65; }
ROOT_REAL=$(realpath -e -- "$ROOT")
[[ $ROOT_REAL == "$ROOT" ]] || { echo "cleanup_z0a: root realpath mismatch: $ROOT_REAL" >&2; exit 65; }
ROOT_DEVICE=$(findmnt -rn -T "$ROOT_REAL" -o MAJ:MIN | tail -n 1)
[[ $ROOT_DEVICE == "$EXPECTED_DEVICE" ]] || {
  echo "cleanup_z0a: root device mismatch: $ROOT_DEVICE != $EXPECTED_DEVICE" >&2
  exit 65
}

declare -a VERIFIED_PATHS=()
for requested in "${REQUESTED_PATHS[@]}"; do
  [[ $requested == /* ]] || { echo "cleanup_z0a: path is not absolute: $requested" >&2; exit 65; }
  [[ $requested != *'*'* && $requested != *'?'* && $requested != *'['* ]] || {
    echo "cleanup_z0a: wildcard syntax rejected: $requested" >&2
    exit 65
  }
  [[ -d $requested && ! -L $requested ]] || {
    echo "cleanup_z0a: only existing non-symlink directories may be cleaned: $requested" >&2
    exit 65
  }
  candidate=$(realpath -e -- "$requested")
  [[ $candidate == "$ROOT_REAL"/* && $candidate != "$ROOT_REAL" ]] || {
    echo "cleanup_z0a: candidate escapes or equals Z0A root: $candidate" >&2
    exit 65
  }
  candidate_device=$(findmnt -rn -T "$candidate" -o MAJ:MIN | tail -n 1)
  [[ $candidate_device == "$EXPECTED_DEVICE" ]] || {
    echo "cleanup_z0a: candidate device mismatch: $candidate_device != $EXPECTED_DEVICE: $candidate" >&2
    exit 65
  }
  [[ -f $candidate/.z0a-owned && ! -L $candidate/.z0a-owned ]] || {
    echo "cleanup_z0a: ownership marker absent: $candidate/.z0a-owned" >&2
    exit 65
  }
  marker=$(sed -n '1p' "$candidate/.z0a-owned")
  [[ $marker == zns-ann-z0a-owned-v1 ]] || {
    echo "cleanup_z0a: invalid ownership marker: $candidate/.z0a-owned" >&2
    exit 65
  }
  # Reject nested mounts.  The candidate's own mount row is expected; any mount
  # whose target is below the candidate would make recursive cleanup unsafe.
  if findmnt -rn -R "$candidate" -o TARGET | awk -v root="$candidate" '$0 != root { found=1 } END { exit !found }'; then
    echo "cleanup_z0a: nested mount detected below candidate: $candidate" >&2
    exit 65
  fi
  VERIFIED_PATHS+=("$candidate")
done

for ((left = 0; left < ${#VERIFIED_PATHS[@]}; left++)); do
  for ((right = left + 1; right < ${#VERIFIED_PATHS[@]}; right++)); do
    a=${VERIFIED_PATHS[$left]}
    b=${VERIFIED_PATHS[$right]}
    [[ $a != "$b" && $a != "$b"/* && $b != "$a"/* ]] || {
      echo "cleanup_z0a: duplicate or overlapping cleanup paths rejected: $a ; $b" >&2
      exit 65
    }
  done
done

printf 'cleanup_z0a: mode=%s root=%s device=%s\n' "$([[ $EXECUTE == 1 ]] && echo execute || echo dry-run)" "$ROOT_REAL" "$EXPECTED_DEVICE"
printf 'cleanup_z0a: verified explicit path: %s\n' "${VERIFIED_PATHS[@]}"

if [[ $EXECUTE == 1 ]]; then
  for candidate in "${VERIFIED_PATHS[@]}"; do
    rm -rf --one-file-system -- "$candidate"
    [[ ! -e $candidate ]] || { echo "cleanup_z0a: deletion incomplete: $candidate" >&2; exit 66; }
    echo "cleanup_z0a: removed: $candidate"
  done
else
  echo "cleanup_z0a: dry-run only; pass --execute to remove the verified paths"
fi
