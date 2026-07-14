#!/usr/bin/env bash
# Notification wrapper. MailSender owns the recipient and reads its own secret.
set -euo pipefail

[[ $# -eq 2 ]] || { echo "usage: $0 SUBJECT MESSAGE" >&2; exit 2; }
message=$2
if [[ -n "${P1_PHASE:-}" ]]; then
  message+=$'\n'
  message+="phase=${P1_PHASE}"
fi
if [[ -n "${P1_ESTIMATED_REMAINING:-}" ]]; then
  message+=$'\n'
  message+="estimated_remaining=${P1_ESTIMATED_REMAINING}"
fi
if [[ -n "${P1_EXPECTED_FINISH_UTC:-}" ]]; then
  message+=$'\n'
  message+="expected_finish_utc=${P1_EXPECTED_FINISH_UTC}"
fi
if [[ -n "${P1_EXPECTED_FINISH_SHANGHAI:-}" ]]; then
  message+=$'\n'
  message+="expected_finish_shanghai=${P1_EXPECTED_FINISH_SHANGHAI}"
fi
if (( EUID == 0 )); then
  runuser -u "${ATLAS_OPERATOR_USER:-ubuntu}" -- \
    python3 /home/ubuntu/.codex/skills/mailsender/scripts/mailsender.py \
      --subject "$1" --message "$message"
else
  python3 /home/ubuntu/.codex/skills/mailsender/scripts/mailsender.py \
    --subject "$1" --message "$message"
fi
