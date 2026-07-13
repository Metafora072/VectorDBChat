#!/usr/bin/env bash
# P1 validation intentionally computes checkpoint-0 GT only. P3/P4 must
# regenerate the relevant checkpoint GT before evaluating churned indexes.
set -euo pipefail

ROOT=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
CHAT=${ATLAS_CHAT_ROOT:-/home/ubuntu/pz/VectorDB/chat/codex/share/dynamic_vamana_atlas}
DATASET="$ROOT/datasets/sift10m"
GT="$ROOT/groundtruth/sift10m"
RESULT="$ROOT/results/pilot3_sift10m/data_validation"

fail() { echo "validate_sift10m: $*" >&2; exit 1; }
case "$ROOT" in /home/ubuntu/pz/VectorDB/data/*) ;; *) fail "refusing non-NVMe root: $ROOT" ;; esac
export TMPDIR="$ROOT/tmp/sift10m-validation"
mkdir -p "$GT" "$RESULT" "$TMPDIR"

[[ -f "$DATASET/DATA_PREPARED_OK" ]] || fail "run prepare_sift10m.sh first"
if [[ -f "$RESULT/VALIDATED_CP00_OK" ]]; then
  [[ -f "$GT/gt_cp00" && -f "$RESULT/gt_validation_cp00.json" ]] || fail "incomplete validation marker"
  echo "already validated: $DATASET checkpoint 0"
  exit 0
fi

ATLAS_CHECKPOINTS=00 "$CHAT/compute_exact_gt.sh" "$DATASET" "$GT" \
  >"$RESULT/compute_gt_cp00.log" 2>&1
python3 "$CHAT/validate_groundtruth.py" --dataset "$DATASET" --groundtruth "$GT" \
  --output "$RESULT/gt_validation_cp00.json" --checkpoints 0
python3 "$CHAT/hash_manifest.py" "$GT" "$ROOT/manifests/sift10m_gt_cp00_sha256.json"
touch "$RESULT/VALIDATED_CP00_OK"
echo "validated: $DATASET checkpoint 0"
