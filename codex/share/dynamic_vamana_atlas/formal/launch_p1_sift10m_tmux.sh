#!/usr/bin/env bash
set -euo pipefail

ROOT=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
CHAT=${ATLAS_CHAT_ROOT:-/home/ubuntu/pz/VectorDB/chat/codex/share/dynamic_vamana_atlas}
SESSION=${P1_TMUX_SESSION:-p1-sift10m}
RUN_NAME=${ATLAS_RUN_NAME:-pilot3_sift10m}
LOG="$ROOT/results/$RUN_NAME/p1_controller/p1.log"
ENV_FILE="$ROOT/results/$RUN_NAME/p1_controller/p1.tmux.env"
BASE_URL=${SIFT10M_BASE_URL:-https://dl.fbaipublicfiles.com/billion-scale-ann-benchmarks/bigann/base.1B.u8bin}
QUERY_URL=${SIFT10M_QUERY_URL:-https://dl.fbaipublicfiles.com/billion-scale-ann-benchmarks/bigann/query.public.10K.u8bin}
SOURCE_FORMAT=${SIFT10M_SOURCE_FORMAT:-u8bin}

(( EUID == 0 )) || { echo "invoke this launcher through sudo; root-owned tmux avoids credential persistence" >&2; exit 2; }
tmux has-session -t "$SESSION" 2>/dev/null && { echo "tmux session already exists: $SESSION" >&2; exit 1; }
mkdir -p "$(dirname "$LOG")"
umask 077
{
  printf 'export ATLAS_ROOT=%q\n' "$ROOT"
  printf 'export ATLAS_CHAT_ROOT=%q\n' "$CHAT"
  printf 'export ATLAS_RUN_NAME=%q\n' "$RUN_NAME"
  printf 'export SIFT10M_SOURCE_FORMAT=%q\n' "$SOURCE_FORMAT"
  printf 'export SIFT10M_BASE_URL=%q\n' "$BASE_URL"
  printf 'export SIFT10M_QUERY_URL=%q\n' "$QUERY_URL"
  printf 'export SIFT10M_BASE_EXPECTED_SHA256=%q\n' "${SIFT10M_BASE_EXPECTED_SHA256:-}"
  printf 'export SIFT10M_QUERY_EXPECTED_SHA256=%q\n' "${SIFT10M_QUERY_EXPECTED_SHA256:-}"
  printf 'export F0_ATTEMPT=%q\n' "${F0_ATTEMPT:-p1-01}"
  printf 'export ATLAS_NOTIFY_EMAIL=%q\n' "${ATLAS_NOTIFY_EMAIL:-1}"
  printf 'export ATLAS_OPERATOR_USER=%q\n' "${ATLAS_OPERATOR_USER:-ubuntu}"
  printf 'export ATLAS_OPERATOR_UID=%q\n' "${ATLAS_OPERATOR_UID:-1000}"
  printf 'export ATLAS_OPERATOR_GID=%q\n' "${ATLAS_OPERATOR_GID:-1000}"
} >"$ENV_FILE"
printf -v command 'set -a; source %q; exec %q' "$ENV_FILE" "$CHAT/formal/run_p1_sift10m.sh"
tmux new-session -d -s "$SESSION" "$command"
echo "started tmux:$SESSION log=$LOG"
