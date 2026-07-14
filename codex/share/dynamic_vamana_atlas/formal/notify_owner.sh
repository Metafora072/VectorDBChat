#!/usr/bin/env bash
# Notification wrapper. MailSender owns the recipient and reads its own secret.
set -euo pipefail

[[ $# -eq 2 ]] || { echo "usage: $0 SUBJECT MESSAGE" >&2; exit 2; }
python3 /home/ubuntu/.codex/skills/mailsender/scripts/mailsender.py \
  --subject "$1" --message "$2"
