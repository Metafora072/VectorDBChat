#!/usr/bin/env python3
"""Fail-closed W1 marker and phase-scoped NVMe accounting collector."""
from __future__ import annotations
import argparse, json
from pathlib import Path

COMMON = ('clone_ready','index_loaded','ingest_begin','ingest_end','publish_begin','publish_end','fresh_process_probe_begin','fresh_process_visibility_verified')
ODIN = ('online_visibility_probe_begin','online_visibility_verified')

def delta(left: dict, right: dict, seconds: float) -> dict:
    keys=('rbytes','wbytes','rios','wios')
    return {**{k:int(right.get(k,0))-int(left.get(k,0)) for k in keys}, 'wall_seconds':seconds}

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('--system',choices=('DGAI','OdinANN'),required=True); p.add_argument('--markers',type=Path,required=True); p.add_argument('--resources',type=Path,required=True); p.add_argument('--active-audit',type=Path,required=True); p.add_argument('--probe',type=Path,required=True); p.add_argument('--logical-payload-bytes',type=int,required=True); p.add_argument('--logical-replacements',type=int,default=80000); p.add_argument('--index-before-bytes',type=int,required=True); p.add_argument('--index-after-bytes',type=int,required=True); p.add_argument('--device',default='259:10'); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    if a.logical_replacements <= 0 or a.logical_payload_bytes <= 0: raise ValueError('logical replacement/payload counts must be positive')
    markers={}
    for line in a.markers.read_text().splitlines():
        row=json.loads(line); name=row.get('marker'); stamp=row.get('monotonic_ns')
        if not isinstance(name,str) or not isinstance(stamp,int) or name in markers: raise ValueError('invalid/duplicate marker')
        markers[name]=(stamp,row)
    required=set(COMMON) | (set(ODIN) if a.system=='OdinANN' else {'online_visibility_unsupported'})
    if set(markers) != required: raise ValueError(f'marker schema mismatch: {set(markers)^required}')
    ordered=COMMON[:4] + (ODIN if a.system=='OdinANN' else ('online_visibility_unsupported',)) + COMMON[4:]
    if [markers[k][0] for k in ordered] != sorted(markers[k][0] for k in ordered): raise ValueError('nonmonotonic marker order')
    if a.system=='DGAI' and markers['online_visibility_unsupported'][1].get('reason')!='requires_final_merge_and_reload': raise ValueError('missing DGAI unsupported reason')
    res=json.loads(a.resources.read_text()); active=json.loads(a.active_audit.read_text()); probe=json.loads(a.probe.read_text())
    if res.get('returncode') != 0 or not active.get('valid') or not probe.get('valid'): raise ValueError('failed correctness/resource prerequisite')
    snapshots=[]
    for sample in res.get('samples',[]):
        for row in sample.get('cgroup_io_stat',[]):
            if row.get('device')==a.device and isinstance(sample.get('monotonic_ns'),int): snapshots.append((sample['monotonic_ns'],row))
    if len(snapshots)<2: raise ValueError('no phase-addressable cgroup I/O samples')
    def snap(marker: str) -> dict: return min(snapshots,key=lambda item:abs(item[0]-markers[marker][0]))[1]
    begin=snap('ingest_begin'); end=snap('fresh_process_visibility_verified'); ingest_end=snap('ingest_end'); publish_begin=snap('publish_begin'); publish_end=snap('publish_end'); fresh_begin=snap('fresh_process_probe_begin')
    ns=lambda x:(markers[x][0]-markers['ingest_begin'][0])/1e9
    phases={'ingest_device_delta':delta(begin,ingest_end,ns('ingest_end')),'publish_device_delta':delta(publish_begin,publish_end,(markers['publish_end'][0]-markers['publish_begin'][0])/1e9),'fresh_process_probe_device_delta':delta(fresh_begin,end,(markers['fresh_process_visibility_verified'][0]-markers['fresh_process_probe_begin'][0])/1e9),'end_to_end_device_delta':delta(begin,end,ns('fresh_process_visibility_verified'))}
    if a.system=='OdinANN': phases['online_probe_device_delta']=delta(snap('online_visibility_probe_begin'),snap('online_visibility_verified'),(markers['online_visibility_verified'][0]-markers['online_visibility_probe_begin'][0])/1e9)
    else: phases['online_probe_device_delta']=None
    report={'schema':'dynamic-vamana-w1-canary-collection-v2','system':a.system,'logical_replacements':a.logical_replacements,'markers':{k:v[0] for k,v in markers.items()},'online_visibility_supported':a.system=='OdinANN','online_visibility_seconds':ns('online_visibility_verified') if a.system=='OdinANN' else None,'online_visible_throughput_ops_s':a.logical_replacements/ns('online_visibility_verified') if a.system=='OdinANN' else None,'ingestion_seconds':ns('ingest_end'),'ingestion_throughput_ops_s':a.logical_replacements/ns('ingest_end'),'restart_visibility_seconds':ns('fresh_process_visibility_verified'),'restart_visible_throughput_ops_s':a.logical_replacements/ns('fresh_process_visibility_verified'),'phase_device_accounting':phases,'publish_write_per_inserted_payload':phases['publish_device_delta']['wbytes']/a.logical_payload_bytes,'persistent_index_growth_bytes':a.index_after_bytes-a.index_before_bytes,'persistent_growth_per_payload':(a.index_after_bytes-a.index_before_bytes)/a.logical_payload_bytes,'active_tag_audit':active,'visibility_probe':probe}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__': main()
