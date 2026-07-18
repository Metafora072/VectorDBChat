#!/usr/bin/env python3
import argparse,hashlib,json
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('--build',type=Path,required=True);ap.add_argument('--canonical',type=Path,required=True);a=ap.parse_args()
def load(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
copy=load(a.build/'selftest/filesystem-copy/profile.json');result=load(a.build/'selftest/filesystem-copy/result.json');rows=[x for x in copy['entry_totals'] if x['entry']=='sendfile'];assert len(rows)==1 and rows[0]['request_count']==1 and rows[0]['requested_bytes']==result['source_before']['size'];assert copy['ledger_totals']['posix']['requested_bytes']==result['source_before']['size'];assert len(copy['buckets'])==1 and copy['buckets'][0]['path'].endswith('index_shadow_disk.index.tags');assert copy['buckets'][0]['device']==result['destination_after']['device'] and copy['buckets'][0]['inode']==result['destination_after']['inode'];assert result['content_equal'] is True
before=list(map(int,(a.build/'selftest/filesystem-copy/destination_before.txt').read_text().split()));after=list(map(int,(a.build/'selftest/filesystem-copy/destination_after.txt').read_text().split()));assert before[:2]==after[:2] and after[2]==result['source_before']['size'];assert {Path(x['path']).name for x in copy['buckets']}=={'index_shadow_disk.index.tags'}
zero=load(a.build/'selftest/filesystem-copy-zero/profile.json');assert zero['ledger_totals']=={} and load(a.build/'selftest/filesystem-copy-zero/result.json')['content_equal'] is True
fd=load(a.build/'selftest/fdreuse/profile.json');assert len({(x['device'],x['inode']) for x in fd['buckets']})==2
aio=load(a.build/'selftest/aio/profile.json');assert all(x['entry']!='sendfile' for x in aio['entry_totals'])
uring=load(a.build/'selftest/uring-systemd/profile.json');assert uring['ledger_totals']['async']=={'requested_bytes':4096,'request_count':1} and all(x['entry']!='sendfile' for x in uring['entry_totals'])
b=a.build/'install/OdinANN/w1_canary';c=a.canonical/'OdinANN/w1_canary';row={'instrumented_binary':str(b.resolve()),'instrumented_sha256':sha(b),'canonical_binary':str(c.resolve()),'canonical_sha256':sha(c),'binary_is_independent':sha(b)!=sha(c),'source_patch':'OdinANN_m0_v4.patch'};assert row['binary_is_independent']
m={'schema':'dynamic-vamana-write-attribution-m0-build-v5','status':'pass','profiler_library':str((a.build/'lib/libm0write.so').resolve()),'profiler_sha256':sha(a.build/'lib/libm0write.so'),'strict_superset_of_r03':True,'new_physical_entry':'sendfile','systems':{'OdinANN':row},'selftests':['empty','posix','boundary','fdreuse','aio','uring-systemd','filesystem-copy-overwrite','filesystem-copy-zero-return','DGAI-aio-no-sendfile']};(a.build/'build_manifest.json').write_text(json.dumps(m,indent=2)+'\n');(a.build/'M0_V5_BUILD_OK').touch();print(a.build/'build_manifest.json')
