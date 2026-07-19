#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")" && pwd)
out=${1:-"$root/bin"}
mkdir -p "$out"

flags=(-std=c++20 -O3 -DNDEBUG -Wall -Wextra -Wpedantic -Wno-deprecated-declarations)
g++ "${flags[@]}" "$root/native_replay.cpp" -lcrypto -o "$out/z0b_native_replay"
g++ "${flags[@]}" "$root/native_reference.cpp" -lcrypto -o "$out/z0b_native_reference"

echo "built $out/z0b_native_replay"
echo "built $out/z0b_native_reference"
