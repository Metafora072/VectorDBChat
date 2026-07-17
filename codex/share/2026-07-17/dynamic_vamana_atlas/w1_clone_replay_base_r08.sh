#!/usr/bin/env bash
# Clone one exact R08 immutable replay base into its exact mutable attempt.
set -euo pipefail

[[ ${W1_CP05_R08_CUMULATIVE_AUTHORIZED:-0} == 1 && ${W1_FORMAL_PATH_AUTHORIZED:-0} == 1 ]] || { echo 'R08 replay clone gate not granted' >&2; exit 64; }
[[ $# == 3 ]] || { echo "usage: $0 SYSTEM BASE_INDEX_DIR ATTEMPT_DIR" >&2; exit 2; }
system=$1; base=$(realpath "$2"); target=$(realpath -m "$3")
root=$(realpath "${ATLAS_ROOT:-/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas}")
chat=${ATLAS_W1_V1_CHAT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-08-15/dynamic_vamana_atlas}
r02=${ATLAS_W1_R02_CHAT:-/home/ubuntu/pz/VectorDB/chat/codex/share/2026-08-16/dynamic_vamana_atlas}
case "$system" in DGAI|OdinANN) ;; *) echo "unsupported dynamic system: $system" >&2; exit 2;; esac
for name in W1_ALLOWED_CLONE_TARGET W1_ALLOWED_CLONE_SYSTEM W1_ALLOWED_CLONE_RUN W1_ALLOWED_CLONE_ATTEMPT; do
  [[ -n ${!name:-} ]] || { echo "R08 replay clone capability missing: $name" >&2; exit 2; }
done
expected_run=pilot3_w1_cp05_trajectory_replay_r08
expected_attempt=sequential-cp80-08
expected_base="$root/formal/pilot3_w1_cp05_replay_bases_v1/$system/cp00/index"
expected_target="$root/formal/$expected_run/$system/$expected_attempt"
[[ $W1_ALLOWED_CLONE_RUN == "$expected_run" && $W1_ALLOWED_CLONE_ATTEMPT == "$expected_attempt" \
  && $W1_ALLOWED_CLONE_SYSTEM == "$system" && $(realpath -m "$W1_ALLOWED_CLONE_TARGET") == "$expected_target" \
  && $target == "$expected_target" && $base == "$expected_base" ]] || {
  echo 'R08 replay clone identity mismatch' >&2; exit 2;
}
[[ -f "$(dirname "$base")/IMMUTABLE_REPLAY_BASE_OK" ]] || { echo 'R08 immutable replay marker absent' >&2; exit 1; }
python3 "$r02/w1_replay_base_recovery.py" verify --root "$root" --system "$system"
target_mount_probe=$target
while [[ ! -e $target_mount_probe ]]; do
  parent=$(dirname "$target_mount_probe")
  [[ $parent != "$target_mount_probe" ]] || { echo 'cannot resolve target mount ancestor' >&2; exit 1; }
  target_mount_probe=$parent
done
[[ $(findmnt -rn -T "$base" -o MAJ:MIN | awk 'NR==1{print;exit}') == "${ATLAS_NVME_MAJMIN:-259:10}" && $(findmnt -rn -T "$target_mount_probe" -o MAJ:MIN | awk 'NR==1{print;exit}') == "${ATLAS_NVME_MAJMIN:-259:10}" ]] || { echo 'base/target not on experiment NVMe' >&2; exit 1; }
[[ ! -e "$target" ]] || { echo "refusing to reuse/overwrite attempt: $target" >&2; exit 1; }
if [[ ${W1_CLONE_PREFLIGHT_ONLY:-0} == 1 ]]; then
  printf 'clone target preflight passed: system=%s target=%s\n' "$system" "$target"
  exit 0
fi
if [[ -n ${W1_MUTABLE_FAILURE_INJECTION:-} && ${W1_MUTABLE_TEST_MODE:-0} != 1 ]]; then
  echo 'mutable failure injection requires explicit test mode' >&2; exit 2
fi
mkdir -p "$(dirname "$target")"
tmp="${target}.partial.$$"; published_incomplete=0
cleanup_partial() {
  if [[ -d $tmp ]]; then find -P "$tmp" -type d -exec chmod u+rwx {} + 2>/dev/null || true; fi
  rm -rf "$tmp"
  if (( published_incomplete == 1 )); then
    if [[ -d $target ]]; then find -P "$target" -type d -exec chmod u+rwx {} + 2>/dev/null || true; fi
    rm -rf "$target"
  fi
}
trap cleanup_partial EXIT
mkdir "$tmp"
clone_started_ns=$(date +%s%N); free_before_clone=$(df -PB1 "$root" | awk 'NR==2{print $4}')
cgroup_rel=$(awk -F: '$1=="0"{print $3}' /proc/self/cgroup)
io_stat_path="/sys/fs/cgroup${cgroup_rel}/io.stat"
if [[ -r $io_stat_path ]]; then cp "$io_stat_path" "$tmp/clone_io_before.txt"; else : >"$tmp/clone_io_before.txt"; fi
python3 "$chat/w1_file_manifest.py" --root "$base" --output "$tmp/base_content_before.tsv"
cp "$tmp/base_content_before.tsv" "$tmp/base_before.tsv"
if ! cp -a --reflink=always "$base/." "$tmp/index" 2>/dev/null; then
  if [[ -d $tmp/index ]]; then find -P "$tmp/index" -type d -exec chmod u+rwx {} +; fi
  rm -rf "$tmp/index"; cp -a --reflink=auto "$base/." "$tmp/index"
  clone_mode=copy_or_filesystem_reflink_auto
else
  clone_mode=reflink
fi
clone_completed_ns=$(date +%s%N)
if [[ -r $io_stat_path ]]; then cp "$io_stat_path" "$tmp/clone_io_after_copy.txt"; else : >"$tmp/clone_io_after_copy.txt"; fi
python3 "$chat/w1_file_manifest.py" --root "$base" --output "$tmp/base_content_after_clone.tsv"
cmp -s "$tmp/base_content_before.tsv" "$tmp/base_content_after_clone.tsv" || { echo 'base content changed during clone' >&2; exit 1; }
python3 "$chat/w1_file_manifest.py" --root "$tmp/index" --output "$tmp/clone_content_before.tsv"
cp "$tmp/clone_content_before.tsv" "$tmp/clone_initial.tsv"
cmp -s "$tmp/base_content_before.tsv" "$tmp/clone_content_before.tsv" || { echo 'clone/base content manifest mismatch' >&2; exit 1; }

python3 "$r02/w1_mode_manifest.py" write --root "$base" --output "$tmp/base_mode_before.tsv"
python3 "$r02/w1_mode_manifest.py" write --root "$base" --output "$tmp/base_mode_after_clone.tsv"
cmp -s "$tmp/base_mode_before.tsv" "$tmp/base_mode_after_clone.tsv" || { echo 'base mode changed during clone' >&2; exit 1; }
python3 "$r02/w1_mode_manifest.py" write --root "$tmp/index" --output "$tmp/clone_mode_before.tsv"
python3 "$r02/w1_mode_manifest.py" compare --left "$tmp/base_mode_before.tsv" --right "$tmp/clone_mode_before.tsv" --policy-only
[[ ${W1_MUTABLE_FAILURE_INJECTION:-} != after_copy ]] || { echo 'injected after_copy failure' >&2; exit 97; }

owner=${W1_MUTABLE_CLONE_OWNER:-ubuntu}
owner_uid=$(id -u "$owner"); owner_gid=$(id -g "$owner")
if [[ $(stat -c '%u:%g' "$tmp") != "$owner_uid:$owner_gid" ]]; then
  chown "$owner_uid:$owner_gid" "$tmp"
fi
chmod 700 "$tmp"
export W1_CLONE_HELPER_PID=$$
python3 "$r02/w1_prepare_mutable_clone.py" --clone-root "$tmp/index" --base-root "$base" --owner "$owner" \
  --system "$system" --output-manifest "$tmp/normalization.json"
python3 "$chat/w1_file_manifest.py" --root "$tmp/index" --output "$tmp/clone_content_after.tsv"
cmp -s "$tmp/clone_content_before.tsv" "$tmp/clone_content_after.tsv" || { echo 'normalization changed clone content' >&2; exit 1; }
python3 "$r02/w1_mode_manifest.py" write --root "$tmp/index" --output "$tmp/clone_mode_after.tsv"
python3 "$r02/w1_mode_manifest.py" verify-private --manifest "$tmp/clone_mode_after.tsv" --owner "$owner"

audit_cmd=(python3 "$r02/w1_writable_clone_audit.py" --clone-root "$tmp/index" --base-root "$base" --owner "$owner" --output "$tmp/mutable_clone_audit.json")
if (( EUID == owner_uid )); then
  "${audit_cmd[@]}"
else
  runuser -u "$owner" -- env W1_MUTABLE_FAILURE_INJECTION="${W1_MUTABLE_FAILURE_INJECTION:-}" "${audit_cmd[@]}"
fi
python3 "$chat/w1_file_manifest.py" --root "$base" --output "$tmp/base_content_after_audit.tsv"
cmp -s "$tmp/base_content_before.tsv" "$tmp/base_content_after_audit.tsv" || { echo 'base content changed during mutable audit' >&2; exit 1; }
python3 "$r02/w1_mode_manifest.py" write --root "$base" --output "$tmp/base_mode_after_audit.tsv"
cmp -s "$tmp/base_mode_before.tsv" "$tmp/base_mode_after_audit.tsv" || { echo 'base mode changed during mutable audit' >&2; exit 1; }
if [[ -r $io_stat_path ]]; then cp "$io_stat_path" "$tmp/clone_io_after_audit.txt"; else : >"$tmp/clone_io_after_audit.txt"; fi

python3 - "$tmp" "$system" "$base" "$target" "$clone_mode" "$owner_uid" "$owner_gid" "$clone_started_ns" "$clone_completed_ns" "$free_before_clone" <<'PY'
import hashlib,json,os,shutil,sys,time
from pathlib import Path
tmp,system,base,target,clone_mode,uid,gid=Path(sys.argv[1]),sys.argv[2],sys.argv[3],sys.argv[4],sys.argv[5],int(sys.argv[6]),int(sys.argv[7])
clone_started,clone_completed,free_before=int(sys.argv[8]),int(sys.argv[9]),int(sys.argv[10])
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
norm=json.loads((tmp/'normalization.json').read_text()); audit=json.loads((tmp/'mutable_clone_audit.json').read_text())
space=lambda p:{'apparent_bytes':sum(x.stat().st_size for x in Path(p).rglob('*') if x.is_file()),'allocated_bytes':sum(x.stat().st_blocks*512 for x in Path(p).rglob('*') if x.is_file())}
def device_row(path):
 rows={}
 for line in path.read_text().splitlines():
  parts=line.split(); rows[parts[0]]={k:int(v) for k,v in (item.split('=',1) for item in parts[1:])}
 return rows.get(os.environ.get('ATLAS_NVME_MAJMIN','259:10'),{})
io_before=device_row(tmp/'clone_io_before.txt'); io_after=device_row(tmp/'clone_io_after_copy.txt')
clone_delta={key:io_after.get(key,0)-io_before.get(key,0) for key in set(io_before)|set(io_after)}
proc_before=norm['proc_io_before']; proc_after=norm['proc_io_after']
proc_delta={key:proc_after.get(key,0)-proc_before.get(key,0) for key in set(proc_before)|set(proc_after)}
report={'schema':'dynamic-vamana-w1-clone-v3','system':system,'base_realpath':str(Path(base).resolve()),'target_realpath':str(Path(target).resolve(strict=False)),'clone_mode':clone_mode,
 'base_content_manifest_sha256':sha(tmp/'base_content_before.tsv'),'clone_content_manifest_sha256':sha(tmp/'clone_content_after.tsv'),
 'base_mode_manifest_sha256':sha(tmp/'base_mode_before.tsv'),'clone_mode_before_sha256':sha(tmp/'clone_mode_before.tsv'),'clone_mode_after_sha256':sha(tmp/'clone_mode_after.tsv'),
 'mutable_policy':'owner_private_tree_v1','owner_uid':uid,'owner_gid':gid,'directory_mode':'0700','file_mode':'0600',
 'regular_file_open_tests':audit['regular_file_open_tests'],'directory_create_rename_tests':audit['directory_create_rename_tests'],
 'base_write_denial_tests':audit['base_file_write_denial_tests']+audit['base_directory_write_denial_tests'],
 'normalization_started_ns':norm['normalization_started_ns'],'normalization_completed_ns':norm['normalization_completed_ns'],
 'normalization_elapsed_seconds':norm['elapsed_seconds'],'normalization_proc_io_before':norm['proc_io_before'],'normalization_proc_io_after':norm['proc_io_after'],
 'normalization_proc_io_delta':proc_delta,'normalization_metadata_operations':norm['metadata_operations'],
 'normalization_ownership_changes':norm['ownership_changes'],'normalization_mode_changes':norm['mode_changes'],
 'clone_started_ns':clone_started,'clone_completed_ns':clone_completed,'clone_wall_seconds':(clone_completed-clone_started)/1e9,
 'clone_device':os.environ.get('ATLAS_NVME_MAJMIN','259:10'),'clone_device_delta':clone_delta,
 'clone_cgroup_io_before':(tmp/'clone_io_before.txt').read_text().splitlines(),'clone_cgroup_io_after_copy':(tmp/'clone_io_after_copy.txt').read_text().splitlines(),
 'clone_cgroup_io_after_audit':(tmp/'clone_io_after_audit.txt').read_text().splitlines(),
 'clone_space':space(tmp/'index'),'free_space_before_clone':free_before,'free_space_before_publish':shutil.disk_usage(tmp).free}
(tmp/'clone_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
PY
mv "$tmp" "$target"; published_incomplete=1
python3 "$chat/w1_file_manifest.py" --root "$target/index" --output "$target/final_content.tsv"
cmp -s "$target/clone_content_after.tsv" "$target/final_content.tsv" || { echo 'published clone content mismatch' >&2; exit 1; }
python3 "$r02/w1_mode_manifest.py" write --root "$target/index" --output "$target/final_mode.tsv"
cmp -s "$target/clone_mode_after.tsv" "$target/final_mode.tsv" || { echo 'published clone mode mismatch' >&2; exit 1; }
python3 "$r02/w1_mode_manifest.py" verify-private --manifest "$target/final_mode.tsv" --owner "$owner"
python3 "$chat/w1_file_manifest.py" --root "$base" --output "$target/base_content_after_publish.tsv"
cmp -s "$target/base_content_before.tsv" "$target/base_content_after_publish.tsv" || { echo 'base content changed at publish' >&2; exit 1; }
python3 "$r02/w1_mode_manifest.py" write --root "$base" --output "$target/base_mode_after_publish.tsv"
cmp -s "$target/base_mode_before.tsv" "$target/base_mode_after_publish.tsv" || { echo 'base mode changed at publish' >&2; exit 1; }
python3 - "$target/clone_manifest.json" "$target" <<'PY'
import json,shutil,sys
from pathlib import Path
p,target=Path(sys.argv[1]),Path(sys.argv[2]); d=json.loads(p.read_text()); d['free_space_after_publish']=shutil.disk_usage(target).free; p.write_text(json.dumps(d,indent=2)+'\n')
PY
published_incomplete=0; trap - EXIT
