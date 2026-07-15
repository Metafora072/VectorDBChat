#!/usr/bin/env bash
# GPT-authorized P2-M integer refinement followed by bounded P2-B Slim W0.
set -Eeuo pipefail

ROOT=${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}
CHAT=${ATLAS_CHAT_ROOT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-07-15/dynamic_vamana_atlas}
RUN_NAME=${ATLAS_RUN_NAME:-pilot3_sift10m_p2b}
OPERATOR_USER=${ATLAS_OPERATOR_USER:-ubuntu}
VALIDATION_RUN=pilot3_sift10m_p1r07
COARSE_ROOT="$ROOT/results/pilot3_sift10m_p2a_r1/raw"
RESULT_ROOT="$ROOT/results/$RUN_NAME"
LOG_DIR="$RESULT_ROOT/p2b_controller"
LOG="$LOG_DIR/p2b.log"
mkdir -p "$LOG_DIR" "$ROOT/tmp/$RUN_NAME" "$RESULT_ROOT" "$ROOT/manifests/$RUN_NAME/artifacts"
chown "$(id -u "$OPERATOR_USER"):$(id -g "$OPERATOR_USER")" "$LOG_DIR" "$ROOT/tmp/$RUN_NAME" "$RESULT_ROOT" "$ROOT/manifests/$RUN_NAME" "$ROOT/manifests/$RUN_NAME/artifacts"
exec > >(tee -a "$LOG") 2>&1

notify() { "$CHAT/formal/notify_owner.sh" "$1" "$2" || true; }
fail() { local code=$?; notify "Dynamic Vamana P2-B failed" "phase=${PHASE:-preflight} exit=$code log=$LOG; subsequent stages stopped"; exit "$code"; }
trap fail ERR
run_as_operator() { runuser -u "$OPERATOR_USER" --preserve-environment -- "$@"; }
export ATLAS_GT_DIR="$ROOT/groundtruth/sift10m/$VALIDATION_RUN" ATLAS_VALIDATION_RUN_NAME=$VALIDATION_RUN ATLAS_NOTIFY_EMAIL=1

next_repeat() {
  local stage=$1 system=$2 l=$3 tq=$4 repeat=1
  while [[ -e "$RESULT_ROOT/$stage/$system/tq${tq}/L$l/r$repeat" || -e "$ROOT/formal/$RUN_NAME/$stage/$system/tq${tq}/L$l/r$repeat" ]]; do ((repeat += 1)); done
  printf '%s\n' "$repeat"
}
valid_count() {
  local stage=$1 system=$2 l=$3 tq=$4 count=0 point
  for point in "$RESULT_ROOT/$stage/$system/tq${tq}/L$l"/r*/point.json; do
    [[ -f "$point" ]] || continue
    python3 - "$point" <<'PY' >/dev/null || { echo "invalid existing point: $point" >&2; return 1; }
import json, sys
raise SystemExit(0 if json.load(open(sys.argv[1])).get("valid") is True else 1)
PY
    ((count += 1))
  done
  printf '%s\n' "$count"
}
run_to_count() {
  local stage=$1 system=$2 l=$3 tq=$4 target=$5 count repeat
  count=$(valid_count "$stage" "$system" "$l" "$tq")
  (( count <= target )) || { echo "too many repeats for $stage/$system/L$l/Tq$tq" >&2; return 1; }
  while (( count < target )); do
    repeat=$(next_repeat "$stage" "$system" "$l" "$tq")
    echo "run stage=$stage system=$system L=$l Tq=$tq repeat=$repeat"
    P2A_STAGE="$stage" P2A_SYSTEM="$system" P2A_L="$l" P2A_TQ="$tq" P2A_REPEAT="$repeat" "$CHAT/formal/p2a_r1_query_point.sh"
    ((count += 1))
  done
}
freeze_system() {
  local system=$1 prefix bin patch source
  case "$system" in
    DiskANN) prefix="$ROOT/formal/pilot3_sift10m_p1r07/f0/DiskANN/p1r07-01/index/index"; bin="$ROOT/build/DiskANN/apps/search_disk_index"; patch=DiskANN_system_blas.patch; source="$ROOT/src/DiskANN-cpp_main" ;;
    DGAI) prefix="$ROOT/formal/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/index/index"; bin="$ROOT/build/DGAI/tests/search_disk_index"; patch=DGAI_mkl_cblas_compat.patch; source="$ROOT/src/DGAI-clean" ;;
    OdinANN) prefix="$ROOT/formal/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/index/index"; bin="$ROOT/build/OdinANN-uring/tests/search_disk_index"; patch=OdinANN_system_uring_cblas.patch; source="$ROOT/src/OdinANN-PipeANN" ;;
  esac
  run_as_operator python3 "$CHAT/freeze_artifact_identity.py" --system "$system" --binary "$bin" --index "${prefix}_disk.index" --query "$ROOT/datasets/sift10m/query.bin" --groundtruth "$ROOT/groundtruth/sift10m/$VALIDATION_RUN/gt_cp00" --compat-patch "$CHAT/patches/$patch" --source-repo "$source" --output "$ROOT/manifests/$RUN_NAME/artifacts/$system.json"
}
record_selection() {
  local system=$1 target=$2 selector=$3
  python3 - "$RESULT_ROOT/selected_refinement.json" "$system" "$target" "$selector" <<'PY'
import json, sys
from pathlib import Path
path, system, target, source = map(Path, sys.argv[1:])
payload = json.loads(source.read_text()); target = str(target)
data = json.loads(path.read_text()) if path.exists() else {"schema":"dynamic-vamana-p2b-selected-refinement-v1","points":{}}
data["points"].setdefault(target, {})[str(system)] = payload
path.write_text(json.dumps(data, indent=2) + "\n")
PY
}

PHASE=artifact-freeze
for system in DiskANN DGAI OdinANN; do freeze_system "$system"; done
notify "Dynamic Vamana P2-M started" "run=$RUN_NAME; integer matched-Recall refinement only"

PHASE=refinement
declare -A LOW HIGH
for key in DiskANN:0.93 DiskANN:0.95 DiskANN:0.97 DiskANN:0.98 DiskANN:0.99 DGAI:0.93 DGAI:0.95 DGAI:0.97 DGAI:0.98 DGAI:0.99 OdinANN:0.93 OdinANN:0.95 OdinANN:0.97 OdinANN:0.98 OdinANN:0.99; do
  case "$key" in
    DiskANN:0.93) LOW[$key]=20; HIGH[$key]=24 ;; DiskANN:0.95) LOW[$key]=24; HIGH[$key]=32 ;; DiskANN:0.97|DiskANN:0.98) LOW[$key]=40; HIGH[$key]=60 ;; DiskANN:0.99) LOW[$key]=60; HIGH[$key]=80 ;;
    DGAI:0.93|DGAI:0.95) LOW[$key]=40; HIGH[$key]=80 ;; DGAI:0.97) LOW[$key]=80; HIGH[$key]=120 ;; DGAI:0.98) LOW[$key]=120; HIGH[$key]=160 ;; DGAI:0.99) LOW[$key]=160; HIGH[$key]=240 ;;
    OdinANN:0.93|OdinANN:0.95|OdinANN:0.97) LOW[$key]=20; HIGH[$key]=40 ;; OdinANN:0.98|OdinANN:0.99) LOW[$key]=40; HIGH[$key]=80 ;;
  esac
done
for system in DiskANN DGAI OdinANN; do
  for target in 0.93 0.95 0.97 0.98 0.99; do
    key="$system:$target"; selector="$RESULT_ROOT/refinement_${system}_${target}.json"
    while :; do
      run_as_operator python3 "$CHAT/refinement_selector.py" --coarse-root "$COARSE_ROOT" --refinement-root "$RESULT_ROOT/refinement" --system "$system" --target "$target" --lower "${LOW[$key]}" --upper "${HIGH[$key]}" --output "$selector"
      action=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["action"])' "$selector")
      if [[ "$action" == measure ]]; then
        l=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["L"])' "$selector")
        n=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["repeat_count"])' "$selector")
        run_to_count refinement "$system" "$l" 1 "$n"; continue
      fi
      record_selection "$system" "$target" "$selector"; break
    done
  done
done

PHASE=refinement-gate
python3 - "$RESULT_ROOT/selected_refinement.json" <<'PY'
import json, sys
p=json.load(open(sys.argv[1]))["points"]
common=[float(t) for t, v in p.items() if all(v.get(s,{}).get("action")=="selected" for s in ("DiskANN","DGAI","OdinANN"))]
if len(common)<3 or not any(t>=.98 for t in common): raise SystemExit("insufficient common matched points")
print("common_matched_targets=" + ",".join(map(str,common)))
PY
touch "$LOG_DIR/P2M_MATCHED_RECALL_PASSED"

PHASE=p2b-tq16
for system in DiskANN DGAI OdinANN; do
  for target in 0.93 0.95 0.97 0.98 0.99; do
    l=$(python3 - "$RESULT_ROOT/selected_refinement.json" "$target" "$system" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))["points"][sys.argv[2]][sys.argv[3]]
print(d.get("L", ""))
PY
)
    [[ -n "$l" ]] || continue
    run_to_count tq16 "$system" "$l" 16 3
  done
done
python3 - "$RESULT_ROOT/selected_refinement.json" "$RESULT_ROOT/tq16" <<'PY'
import json, statistics, sys
from pathlib import Path
selected, root = json.load(open(sys.argv[1]))["points"], Path(sys.argv[2])
for target, systems in selected.items():
    floor = float(target)
    for system, choice in systems.items():
        if choice.get("action") != "selected": continue
        rows = [json.loads(p.read_text()) for p in root.glob(f"{system}/tq16/L{choice['L']}/r*/point.json")]
        if len(rows) != 3 or any(row.get("valid") is not True for row in rows):
            raise SystemExit(f"invalid Tq16 group {system}/{target}")
        median = statistics.median(float(row["recall_at_10"]) for row in rows)
        if not floor <= median <= floor + .005:
            raise SystemExit(f"Tq16 local refinement required for {system}/{target}: median={median}")
PY
touch "$LOG_DIR/P2B_TQ16_COMPLETE"
notify "Dynamic Vamana P2-B raw execution complete" "run=$RUN_NAME; result aggregation remains; no W1/churn started"
