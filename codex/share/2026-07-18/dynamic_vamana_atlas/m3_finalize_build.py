#!/usr/bin/env python3
import argparse, hashlib, json
from pathlib import Path

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''): h.update(b)
    return h.hexdigest()

p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--build',type=Path,required=True); p.add_argument('--accepted',type=Path,required=True); a=p.parse_args()
accepted=json.loads((a.accepted/'build_manifest.json').read_text())
prof=a.build/'lib/libm0write.so'
assert accepted['status']=='pass' and sha(prof)==accepted['profiler_sha256']
systems={}
for system in ('DGAI','OdinANN'):
    binary=a.build/f'install/{system}/w1_canary'; canonical=a.root/f'build/w1-canonical-v6/install/{system}/w1_canary'
    assert binary.is_file() and canonical.is_file() and sha(binary)!=sha(canonical)
    systems[system]={'instrumented_binary':str(binary.resolve()),'instrumented_sha256':sha(binary),
      'canonical_binary':str(canonical.resolve()),'canonical_sha256':sha(canonical),'binary_is_independent':True,
      'm2_source_patch':f'{system}_m2.patch','m3_source_patch':f'{system}_m3.patch'}
manifest={'schema':'dynamic-vamana-write-attribution-m0-build-v5','status':'pass',
 'scope':'m3-write-supersession-lifecycle-dual-system','profiler_library':str(prof.resolve()),
 'profiler_sha256':sha(prof),'profiler_identity_matches_accepted_v5':True,
 'logical_schema':'dynamic-vamana-neighbor-repair-m2-logical-v1',
 'lifecycle_schema':'dynamic-vamana-write-supersession-m3-lifecycle-v1',
 'logical_collector_sha256':sha(a.build/'source-evidence/m2_metrics.h'),
 'lifecycle_collector_sha256':sha(a.build/'source-evidence/m3_lifecycle.h'),
 'systems':systems,'selftests':['m2-accepted-collector-reused','m3-lifecycle-classifier-known-answer']}
(a.build/'build_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n'); (a.build/'M3_BUILD_OK').touch(); print(a.build/'build_manifest.json')
