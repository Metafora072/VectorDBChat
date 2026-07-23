#!/usr/bin/env bash
set -euo pipefail

WORK_ROOT=/home/ubuntu/pz/VectorDB/chat/codex/work/2026-07-24/pq_rp_highdim_a0
# shellcheck source=../config.env
source "${WORK_ROOT}/config.env"

EXPECTED_SOURCE=/dev/nvme8n1
SOURCE="$(findmnt -T /home/ubuntu/pz/VectorDB/data -n -o SOURCE | head -n 1)"
[[ "${SOURCE}" == "${EXPECTED_SOURCE}" ]] ||
  { echo "hard stop: data mount is ${SOURCE}, expected ${EXPECTED_SOURCE}" >&2; exit 2; }

AVAILABLE="$(df -B1 --output=avail /home/ubuntu/pz/VectorDB/data | tail -n 1 | tr -d ' ')"
(( AVAILABLE >= 30000000000 )) ||
  { echo "hard stop: fewer than 30GB available" >&2; exit 2; }

RAW="${DATA_ROOT}/raw/cohere"
TMPDIR="${DATA_ROOT}/tmp"
mkdir -p "${RAW}" "${TMPDIR}" "${DATA_ROOT}/converted" "${DATA_ROOT}/manifests"
export TMPDIR

BASE_URL="https://huggingface.co/datasets/${COHERE_REPO}/resolve/${COHERE_REVISION}"
for name in README.md cohere_train.f32 cohere_test.f32 cohere_groundtruth.i32; do
  curl --fail --location --retry 4 --retry-delay 3 --continue-at - \
    --output "${RAW}/${name}" "${BASE_URL}/${name}"
done

{
  printf 'repository=%s\nrevision=%s\n' "${COHERE_REPO}" "${COHERE_REVISION}"
  printf 'resolved_source=%s\navailable_bytes_before=%s\n' "${SOURCE}" "${AVAILABLE}"
  sha256sum \
    "${RAW}/README.md" \
    "${RAW}/cohere_train.f32" \
    "${RAW}/cohere_test.f32" \
    "${RAW}/cohere_groundtruth.i32"
} > "${DATA_ROOT}/manifests/download_manifest.txt"
