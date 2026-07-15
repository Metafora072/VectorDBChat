#!/usr/bin/env bash
# Execute all GT regressions and publish CP01 R02 GT only after every gate passes.
set -euo pipefail
[[ ${W1_RECOVERY_AUTHORIZED:-0} == 1 && $# == 3 ]] || { echo "usage: $0 ROOT RESULT_DIR GT_DIR" >&2; exit 64; }
root=$(realpath "$1"); result=$(realpath -m "$2"); gt=$(realpath -m "$3")
new=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
old=${ATLAS_W1_V1_CHAT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas}
tool="$root/build/DiskANN/apps/utils/compute_groundtruth"; cp01="$root/datasets/sift10m/w1_cp01"; query="$root/datasets/sift10m/query.bin"
[[ -x $tool && ! -e $gt ]] || { echo 'invalid/reused recovered GT target' >&2; exit 1; }
mkdir -p "$result/regressions" "$gt/tmp"
compute() {
  local base=$1 q=$2 out=$3 k=$4 log=$5
  OPENBLAS_NUM_THREADS=56 OMP_NUM_THREADS=56 LD_PRELOAD="$root/build/openblas-install/lib/libopenblas.so" \
    "$tool" --data_type float --dist_fn l2 --base_file "$base" --query_file "$q" --gt_file "$out" --K "$k" >"$log" 2>&1
  ! rg -q 'WARNING: found less than k GT entries' "$log" || { echo "less-than-K warning in $log" >&2; exit 1; }
}
remap() {
  local loc=$1 tags=$2 out=$3 report=$4 nq=$5 k=$6 count=$7
  python3 "$new/w1_remap_truthset_locations_to_tags.py" --location-truthset "$loc" --active-tags "$tags" --output "$out" --report "$report" --expected-nquery "$nq" --expected-k "$k" --expected-active-count "$count"
}

syn="$result/regressions/synthetic"
python3 "$new/w1_gt_recovery_inputs.py" synthetic --output-dir "$syn"
compute "$syn/base.bin" "$syn/query.bin" "$syn/locations.bin" 100 "$syn/compute.log"
python3 "$new/w1_validate_location_truthset.py" --truthset "$syn/locations.bin" --nquery 1 --k 100 --location-count 128 --output "$syn/location_validation.json"
remap "$syn/locations.bin" "$syn/tags.bin" "$syn/gt.bin" "$syn/remap.json" 1 100 128
python3 "$old/validate_groundtruth.py" --dataset "$syn" --groundtruth "$syn" --base-file "$syn/base.bin" --tags-file "$syn/tags.bin" --query-file "$syn/query.bin" --truthset-file "$syn/gt.bin" --checkpoint 1 --audit-query-ids 0 --output "$syn/validation.json" >/dev/null
python3 "$new/w1_assert_truthset_tag.py" --truthset "$syn/gt.bin" --tag 0 --query-row 0 --output "$syn/tag_zero.json"

cp0="$result/regressions/cp00"; mkdir -p "$cp0"
compute "$root/datasets/sift10m/active_cp00.bin" "$query" "$cp0/locations.bin" 100 "$cp0/compute.log"
python3 "$new/w1_validate_location_truthset.py" --truthset "$cp0/locations.bin" --nquery 10000 --k 100 --location-count 8000000 --output "$cp0/location_validation.json"
remap "$cp0/locations.bin" "$root/datasets/sift10m/active_cp00.tags.bin" "$cp0/gt_cp00" "$cp0/remap.json" 10000 100 8000000
cmp -s "$cp0/gt_cp00" "$root/groundtruth/sift10m/pilot3_sift10m_p1r07/gt_cp00" || { echo 'CP00 recovered GT is not byte-identical to frozen GT' >&2; exit 1; }
sha256sum "$cp0/gt_cp00" "$root/groundtruth/sift10m/pilot3_sift10m_p1r07/gt_cp00" >"$cp0/byte_identity.sha256"

target="$result/regressions/query7150"; mkdir -p "$target"
python3 "$new/w1_gt_recovery_inputs.py" targeted --query "$query" --qid 7150 --output "$target/query.bin"
compute "$cp01/active_cp01.bin" "$target/query.bin" "$target/locations.bin" 100 "$target/compute.log"
python3 "$new/w1_validate_location_truthset.py" --truthset "$target/locations.bin" --nquery 1 --k 100 --location-count 8000000 --output "$target/location_validation.json"
remap "$target/locations.bin" "$cp01/active_cp01.tags.bin" "$target/gt.bin" "$target/remap.json" 1 100 8000000
python3 "$old/validate_groundtruth.py" --dataset "$cp01" --groundtruth "$target" --base-file "$cp01/active_cp01.bin" --tags-file "$cp01/active_cp01.tags.bin" --query-file "$target/query.bin" --truthset-file "$target/gt.bin" --checkpoint 1 --audit-query-ids 0 --output "$target/validation.json" >/dev/null
python3 "$new/w1_assert_truthset_tag.py" --truthset "$target/gt.bin" --tag 0 --query-row 0 --output "$target/tag_zero.json"

compute "$cp01/active_cp01.bin" "$query" "$gt/tmp/gt_cp01_locations.tmp" 100 "$gt/gt_cp01.log"
python3 "$new/w1_validate_location_truthset.py" --truthset "$gt/tmp/gt_cp01_locations.tmp" --nquery 10000 --k 100 --location-count 8000000 --output "$gt/location_validation.json"
remap "$gt/tmp/gt_cp01_locations.tmp" "$cp01/active_cp01.tags.bin" "$gt/tmp/gt_cp01.candidate" "$gt/remap.json" 10000 100 8000000
audits=0,17,7150,9999,5493,695,892,8206,5597,4134,5328,6962,6016,4479,1337,8026,948,8915,2587,8272,8384,7,510,2828,8223,4949,3274,7399,8747,1266,3218,8480,6896,3945,4185,70
python3 "$old/validate_groundtruth.py" --dataset "$cp01" --groundtruth "$gt" --base-file "$cp01/active_cp01.bin" --tags-file "$cp01/active_cp01.tags.bin" --query-file "$query" --truthset-file "$gt/tmp/gt_cp01.candidate" --checkpoint 1 --audit-query-ids "$audits" --output "$gt/gt_cp01_validation.json" >/dev/null
python3 "$new/w1_compare_recovered_gt.py" --failed "$root/groundtruth/sift10m/w1/gt_cp01" --recovered "$gt/tmp/gt_cp01.candidate" --qid 7150 --output "$gt/failed_gt_comparison.json"
python3 "$new/w1_publish_recovered_gt.py" --candidate "$gt/tmp/gt_cp01.candidate" --output "$gt/gt_cp01" --remap-report "$gt/remap.json" --validation "$gt/gt_cp01_validation.json" --comparison "$gt/failed_gt_comparison.json" --location-validation "$gt/location_validation.json" --log "$gt/gt_cp01.log" --manifest "$gt/gt_cp01_manifest.json"
touch "$result/GT_RECOVERY_OK"
