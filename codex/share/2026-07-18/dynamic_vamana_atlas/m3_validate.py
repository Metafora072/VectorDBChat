#!/usr/bin/env python3
import argparse, hashlib, json, math
from pathlib import Path

def load(p): return json.loads(p.read_text())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''): h.update(b)
    return h.hexdigest()
def weighted(hist): return sum(int(k)*int(v) for k,v in hist.items())
def count(hist): return sum(int(v) for v in hist.values())

p=argparse.ArgumentParser(); p.add_argument('--system',choices=('DGAI','OdinANN'),required=True); p.add_argument('--size',type=int,choices=(50000,400000),required=True)
p.add_argument('--physical-summary',type=Path,required=True); p.add_argument('--m2-logical',type=Path,required=True); p.add_argument('--m2-run-summary',type=Path,required=True)
p.add_argument('--lifecycle',type=Path,required=True); p.add_argument('--m2-baseline',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
physical,logical,m2run,life,baseline=map(load,(a.physical_summary,a.m2_logical,a.m2_run_summary,a.lifecycle,a.m2_baseline))
base=next(r for r in baseline['points'] if r['system']==a.system and r['size']==a.size)
base_physical=load(Path(base['physical_summary']))
roles={r['role']:r for r in physical['application_writes']['logical_roles']}; neighbor_bytes=int(roles['neighbor_repair']['requested_bytes'])
bucket=next(r for r in physical['application_writes']['buckets'] if r['phase']=='insert_neighbor_repair' and r['component']=='graph_vector_combined')
t=life['totals']; c=life['generation_classes']; h=life['histograms']; cl=life['closure']
direct=int(c['superseded_before_enqueue'])+int(c['superseded_while_queued'])
repeat=int(t['generated'])-int(c['no_prior_version'])
wall_ratio=physical['wall_time']['ingest_seconds']/base_physical['wall_time']['ingest_seconds']
write_ratio=neighbor_bytes/base['physical_neighbor_repair_only_bytes']
hist_names={'queue_depth_tasks','queue_depth_pages','per_page_queued_versions','per_page_inflight_versions',
 'generation_to_submit_operation_distance','generation_to_submit_batch_distance','later_versions_during_inflight',
 'same_page_versions_per_128_record_batch','versions_per_page_between_barriers','versions_per_barrier'}
gates={
 'physical_formal_pass':physical['status']=='pass' and all(physical['gates'].values()),
 'm2_logical_pass':m2run['status']=='pass' and logical['status']=='complete',
 'lifecycle_complete':life['status']=='complete',
 'identity_exact':life['identity']['system']==a.system and life['identity']['device']==bucket['device'] and life['identity']['inode']==bucket['inode'] and Path(life['identity']['path']).resolve()==Path(bucket['path']).resolve(),
 'generation_class_closure':sum(map(int,c.values()))==int(t['generated'])==int(cl['class_sum']),
 'lifecycle_submit_completion_closure':int(t['enqueued'])==int(t['submitted'])==int(t['completed'])==int(t['generated']),
 'physical_page_touch_closure':int(t['submitted'])==int(t['completed'])==neighbor_bytes//4096 and neighbor_bytes%4096==0,
 'version_monotonicity_and_containment':cl['stale_or_fork_events']==0 and cl['unproven_presubmit_containment']==0,
 'queue_accounting':cl['queue_underflow']==0 and cl['inflight_underflow']==0,
 'all_histograms_present':set(h)==hist_names and all(h[n] for n in hist_names),
 'submit_histogram_counts':count(h['generation_to_submit_operation_distance'])==int(t['submitted']) and count(h['generation_to_submit_batch_distance'])==int(t['submitted']),
 'page_state_histogram_counts':count(h['per_page_queued_versions'])==int(t['enqueued']) and count(h['per_page_inflight_versions'])==int(t['submitted']),
 'batch_histogram_weight_closure':weighted(h['same_page_versions_per_128_record_batch'])==int(t['generated']),
 'barrier_histogram_weight_closure':weighted(h['versions_per_page_between_barriers'])==int(t['generated']) and weighted(h['versions_per_barrier'])==int(t['generated']),
 'instrumentation_ingest_wall_within_25pct':0.75<=wall_ratio<=1.25,
 'instrumentation_neighbor_write_within_10pct':0.90<=write_ratio<=1.10,
}
report={'schema':'dynamic-vamana-write-supersession-m3-run-v1','status':'pass' if all(gates.values()) else 'fail','system':a.system,'size':a.size,
 'physical_summary':str(a.physical_summary.resolve()),'physical_summary_sha256':sha(a.physical_summary),'lifecycle':str(a.lifecycle.resolve()),'lifecycle_sha256':sha(a.lifecycle),
 'm2_run_summary':str(a.m2_run_summary.resolve()),'m2_run_summary_sha256':sha(a.m2_run_summary),
 'totals':t,'generation_classes':c,'histograms':h,'directly_supersedable_before_submit_versions':direct,
 'directly_supersedable_before_submit_bytes':direct*4096,'directly_supersedable_bytes_per_replacement':direct*4096/a.size,
 'stage_repeat_versions':repeat,'presubmit_fraction_of_repeats':direct/repeat if repeat else 0,
 'already_avoided_versions':0,'already_avoided_reason':'ConcurrentQueue has no page-key deduplication; page lock prevents a later same-page version from being generated before completion.',
 'perturbation':{'baseline_ingest_seconds':base_physical['wall_time']['ingest_seconds'],'m3_ingest_seconds':physical['wall_time']['ingest_seconds'],'ingest_ratio':wall_ratio,
   'baseline_neighbor_bytes':base['physical_neighbor_repair_only_bytes'],'m3_neighbor_bytes':neighbor_bytes,'neighbor_write_ratio':write_ratio,
   'preregistered_thresholds':{'ingest_wall_ratio':[0.75,1.25],'neighbor_write_ratio':[0.90,1.10]}},'gates':gates}
a.output.write_text(json.dumps(report,indent=2)+'\n')
if report['status']!='pass': raise SystemExit('M3 lifecycle/perturbation gate failed')
print(a.output)
