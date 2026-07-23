#!/usr/bin/env bash
set -euo pipefail

HERE=$(cd -- "$(dirname -- "$0")" && pwd)
for script in "$HERE"/gen_fig*.py; do
    python3 "$script"
done

