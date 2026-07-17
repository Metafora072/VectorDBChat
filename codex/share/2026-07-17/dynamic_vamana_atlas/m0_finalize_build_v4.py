#!/usr/bin/env python3
import argparse,hashlib,json
from pathlib import Path

ap=argparse.ArgumentParser();ap.add_argument('--build',type=Path,required=True);ap.add_argument('--canonical',type=Path,required=True);a=ap.parse_args()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(p.read_text())
tests={m:load(a.build/'selftest'/m/'profile.json') for m in ('empty','posix','boundary','fdreuse','aio')}
tests['uring-systemd']=load(a.build/'selftest/uring-systemd/profile.json')
assert tests['empty']['ledger_totals']=={}
assert tests['posix']['ledger_totals']['posix']=={'requested_bytes':4096,'request_count':1}
assert sum(x['requested_bytes'] for x in tests['boundary']['buckets'])==4096
assert {x['component'] for x in tests['boundary']['buckets']}=={'metadata','graph_vector_combined'}
assert {Path(x['path']).name for x in tests['fdreuse']['buckets']}=={'index_disk.index','index_pq_compressed.bin'}
assert tests['aio']['ledger_totals']['async']=={'requested_bytes':4096,'request_count':1}
assert tests['uring-systemd']['ledger_totals']['async']=={'requested_bytes':4096,'request_count':1}
systems={}
for s in ('DGAI','OdinANN'):
 b=a.build/'install'/s/'w1_canary';c=a.canonical/s/'w1_canary';systems[s]={'instrumented_binary':str(b.resolve()),'instrumented_sha256':sha(b),'canonical_binary':str(c.resolve()),'canonical_sha256':sha(c),'binary_is_independent':sha(b)!=sha(c),'source_patch':f'{s}_m0_v4.patch'};assert systems[s]['binary_is_independent']
m={'schema':'dynamic-vamana-write-attribution-m0-build-v4','status':'pass','profiler_library':str((a.build/'lib/libm0write.so').resolve()),'profiler_sha256':sha(a.build/'lib/libm0write.so'),'selftests':['empty','posix','boundary','fdreuse','aio','uring-systemd'],'systems':systems}
(a.build/'build_manifest.json').write_text(json.dumps(m,indent=2)+'\n');(a.build/'M0_V4_BUILD_OK').touch();print(a.build/'build_manifest.json')
