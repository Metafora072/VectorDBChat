#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path

def load(p:Path): return json.loads(p.read_text())
def sha(p:Path):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''): h.update(b)
 return h.hexdigest()
def device_row(s,d):
 for r in s.get('cgroup_io_stat',[]):
  if r.get('device')==d:return {k:int(v) for k,v in r.items() if k!='device'}
 return {}
def markers(p):
 out={}
 for line in p.read_text().splitlines():
  if line.strip():
   r=json.loads(line); n=r['marker']
   if n in out: raise ValueError(f'duplicate marker {n}')
   out[n]=int(r['monotonic_ns'])
 return out
def manifest(p):
 out={}
 for line in p.read_text().splitlines():
  name,size,digest=line.split('\t');out[name]=(int(size),digest)
 return out

def main():
 ap=argparse.ArgumentParser()
 for n in ('system','size','input_manifest','build_manifest','profile','resources','markers','active_audit','fresh_probe','base_before','base_after','mode_before','mode_after','index_before','index_after','output'):
  ap.add_argument('--'+n.replace('_','-'),required=True,type=int if n=='size' else Path if n not in ('system',) else str)
 ap.add_argument('--online-probe',type=Path);ap.add_argument('--device',default='259:10');a=ap.parse_args()
 if a.system not in ('DGAI','OdinANN'):raise SystemExit('bad system')
 inputs,build,profile,res=map(load,(a.input_manifest,a.build_manifest,a.profile,a.resources));active,fresh=load(a.active_audit),load(a.fresh_probe);online=load(a.online_probe) if a.online_probe else None;t=markers(a.markers)
 required=['clone_ready','index_loaded','ingest_begin','ingest_end','publish_begin','publish_end']
 if not all(x in t for x in required) or not all(t[x]<t[y] for x,y in zip(required,required[1:])):raise SystemExit('marker gate failed')
 buckets=profile.get('buckets',[]); totals=profile.get('ledger_totals',{}); entries=profile.get('entry_totals',[]);roles=profile.get('logical_roles',[])
 async_entry='linux_aligned.execute_io.libaio' if a.system=='DGAI' else 'linux_aligned.execute_io.io_uring'
 audited=[{'entry':async_entry,'ledger':'async'}]+[{'entry':x,'ledger':'posix'} for x in ('write','pwrite','pwrite64','writev','pwritev','fdatasync/fsync')]+[{'entry':'insert_rmw_role','ledger':'logical'}]
 observed={(x['ledger'],x['entry']):int(x['request_count']) for x in entries}
 for x in audited:x['triggered']=observed.get((x['ledger'],x['entry']),0)>0 if x['ledger']!='logical' else bool(roles);x['status']='triggered' if x['triggered'] else 'not_triggered_by_workload'
 source_complete=observed.get(('async',async_entry),0)>0 and bool(roles) and all(x['ledger'] in ('async','posix','logical') for x in audited)
 physical=sum(int(v['requested_bytes']) for k,v in totals.items() if k in ('async','posix'))
 bucket_physical=sum(int(x['requested_bytes']) for x in buckets if x['ledger'] in ('async','posix'))
 entry_physical=sum(int(x['requested_bytes']) for x in entries if x['ledger'] in ('async','posix'))
 no_double=physical==bucket_physical==entry_physical and len({(x['ledger'],x['entry']) for x in entries})==len(entries)
 clear_phases={'insert_neighbor_repair','delete','publish_save','metadata'};clear_components={'graph','vector','graph_vector_combined','delete_tombstone','metadata'}
 update=[x for x in buckets if x['phase'] not in ('load','visibility','other')]
 denom=sum(int(x['requested_bytes']) for x in update); attributed=sum(int(x['requested_bytes']) for x in update if x['phase'] in clear_phases and x['component'] in clear_components);coverage=attributed/denom if denom else 0.0
 before,after=manifest(a.index_before),manifest(a.index_after);changed=sorted(k for k in set(before)|set(after) if before.get(k)!=after.get(k));recorded={Path(x['path']).name for x in buckets if int(x['requested_bytes'])>0};changed_covered=bool(changed) and all(x in recorded for x in changed)
 samples=res.get('samples',[]);d0=device_row(samples[0],a.device);d1=device_row(samples[-1],a.device);delta={k:d1.get(k,0)-d0.get(k,0) for k in set(d0)|set(d1)} if len(samples)>=2 else {}
 mem=res.get('cgroup_memory_events_final',{});frozen=a.base_before.read_bytes()==a.base_after.read_bytes() and a.mode_before.read_bytes()==a.mode_after.read_bytes()
 correctness=active.get('valid') is True and active.get('expected_exact_match') is True and fresh.get('valid') is True and (a.system!='OdinANN' or online and online.get('valid') is True)
 input_ok=inputs.get('status')=='pass' and inputs.get('size')==a.size and inputs.get('master_record_range')==[800000,800000+a.size] and inputs.get('active_count')==8000000
 br=build['systems'][a.system];build_ok=build.get('status')=='pass' and br.get('binary_is_independent') is True and build.get('schema')=='dynamic-vamana-write-attribution-m0-build-v4'
 paths_ok=all(str(x['path']).startswith(profile['index_root']+'/') and int(x['device'])>0 and int(x['inode'])>0 for x in buckets)
 nofail=res.get('returncode')==0 and int(mem.get('oom',0))==0 and int(mem.get('oom_kill',0))==0
 gates={'input_exact':input_ok,'independent_v4_binary':build_ok,'correctness':correctness,'frozen_source_unchanged':frozen,'source_entry_complete':source_complete,'no_physical_double_count':no_double,'changed_files_covered':changed_covered,'ledger_classification_ge_90pct':coverage>=.90,'private_live_fd_identity':paths_ok,'positive_device_write_sanity':int(delta.get('wbytes',0))>0,'no_oom_fatal_failure':nofail,'logical_role_observed':bool(roles)}
 phase={};component={};ledger={}
 for x in buckets:
  n=int(x['requested_bytes']);phase[x['phase']]=phase.get(x['phase'],0)+n;component[x['component']]=component.get(x['component'],0)+n;ledger[x['ledger']]=ledger.get(x['ledger'],0)+n
 wall={'load_seconds':(t['index_loaded']-t['clone_ready'])/1e9,'ingest_seconds':(t['ingest_end']-t['ingest_begin'])/1e9,'publish_seconds':(t['publish_end']-t['publish_begin'])/1e9,'end_to_end_seconds':(t['publish_end']-t['ingest_begin'])/1e9}
 if a.system=='OdinANN':wall['online_visibility_probe_seconds']=(t['online_visibility_verified']-t['online_visibility_probe_begin'])/1e9
 report={'schema':'dynamic-vamana-write-attribution-m0-run-v4','status':'pass' if all(gates.values()) else 'fail','system':a.system,'size':a.size,'trace_range':[800000,800000+a.size],'wall_time':wall,'instrumented_binary_sha256':br['instrumented_sha256'],'canonical_binary_sha256':br['canonical_sha256'],'application_writes':{'physical_total_bytes':physical,'async':totals.get('async',{'requested_bytes':0,'request_count':0}),'posix':totals.get('posix',{'requested_bytes':0,'request_count':0}),'classification_coverage':coverage,'phase_totals':phase,'component_totals':component,'ledger_totals':ledger,'buckets':buckets,'logical_roles':roles},'source_entry_audit':audited,'changed_index_files':changed,'recorded_index_files':sorted(recorded),'device_delta':delta,'peak_rss_kb':res.get('peak_process_tree_rss_kb'),'memory_events':mem,'correctness':{'active_set_exact':active.get('valid'),'fresh_visibility_query_smoke':fresh.get('valid'),'online_visibility':online.get('valid') if online else 'unsupported_by_current_DGAI_path','frozen_source_unchanged':frozen},'gates':gates,'evidence_sha256':{k:sha(v) for k,v in {'input_manifest':a.input_manifest,'profile':a.profile,'resources':a.resources,'markers':a.markers,'active_audit':a.active_audit,'fresh_probe':a.fresh_probe,'index_before':a.index_before,'index_after':a.index_after}.items()}}
 if a.online_probe:report['evidence_sha256']['online_probe']=sha(a.online_probe)
 a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
 if report['status']!='pass':raise SystemExit('M0 V4 run gate failed: '+','.join(k for k,v in gates.items() if not v))
if __name__=='__main__':main()
