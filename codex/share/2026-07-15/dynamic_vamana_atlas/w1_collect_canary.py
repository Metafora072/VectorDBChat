#!/usr/bin/env python3
"""Collect W1 markers and accounting; reject missing/ambiguous phase boundaries."""
from __future__ import annotations
import argparse,json
from pathlib import Path
REQUIRED=('clone_ready','index_loaded','ingest_begin','ingest_end','online_visibility_probe_begin','online_visibility_verified','publish_begin','publish_end','fresh_process_probe_begin','fresh_process_visibility_verified')
def main()->None:
 p=argparse.ArgumentParser();p.add_argument('--system',required=True);p.add_argument('--markers',type=Path,required=True);p.add_argument('--resources',type=Path,required=True);p.add_argument('--active-audit',type=Path,required=True);p.add_argument('--probe',type=Path,required=True);p.add_argument('--logical-payload-bytes',type=int,required=True);p.add_argument('--index-before-bytes',type=int,required=True);p.add_argument('--index-after-bytes',type=int,required=True);p.add_argument('--device',default='259:10');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 marker={}
 for line in a.markers.read_text().splitlines():
  row=json.loads(line); name=row.get('marker'); ns=row.get('monotonic_ns')
  if name in marker or name not in REQUIRED or not isinstance(ns,int):raise ValueError('invalid or duplicate marker')
  marker[name]=ns
 if set(marker)!=set(REQUIRED):raise ValueError('missing required markers')
 times=[marker[x] for x in REQUIRED]
 if times!=sorted(times):raise ValueError('markers are not monotonic')
 active=json.loads(a.active_audit.read_text());probe=json.loads(a.probe.read_text());res=json.loads(a.resources.read_text())
 if not active.get('valid') or not probe.get('valid') or res.get('returncode')!=0:raise ValueError('correctness/resource validation failed')
 n=80_000; d=lambda end:(marker[end]-marker['ingest_begin'])/1e9
 io=[]
 for sample in res.get('samples',[]):
  for row in sample.get('cgroup_io_stat',[]):
   if row.get('device')==a.device: io.append(row)
 if not io: raise ValueError(f'no cgroup I/O accounting for device {a.device}')
 first,last=io[0],io[-1]
 delta={key:int(last.get(key,0))-int(first.get(key,0)) for key in ('rbytes','wbytes','rios','wios')}
 report={'schema':'dynamic-vamana-w1-canary-collection-v1','system':a.system,'markers_monotonic_ns':marker,
  'ingestion_seconds':d('ingest_end'),'ingestion_throughput_ops_s':n/d('ingest_end'),
  'online_visibility_seconds':d('online_visibility_verified'),'online_visible_throughput_ops_s':n/d('online_visibility_verified'),
  'restart_visibility_seconds':d('fresh_process_visibility_verified'),'restart_visible_throughput_ops_s':n/d('fresh_process_visibility_verified'),
  'logical_replacements':n,'logical_inserted_vector_payload_bytes':a.logical_payload_bytes,
  'persistent_index_growth_bytes':a.index_after_bytes-a.index_before_bytes,
  'persistent_growth_per_payload':(a.index_after_bytes-a.index_before_bytes)/a.logical_payload_bytes,
  'resource_summary':{'peak_rss_kb':res.get('peak_process_tree_rss_kb'),'cgroup_memory_events':res.get('cgroup_memory_events_final'),'process_io':res.get('peak_process_tree_io_bytes'),'device':a.device,'device_delta':delta,
                      'read_iops':delta['rios']/d('fresh_process_visibility_verified'),'write_iops':delta['wios']/d('fresh_process_visibility_verified'),
                      'device_write_per_inserted_payload':delta['wbytes']/a.logical_payload_bytes},
  'active_tag_audit':active,'visibility_probe':probe}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
