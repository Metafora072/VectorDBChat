#!/usr/bin/env python3
import argparse, hashlib, json
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''): h.update(b)
 return h.hexdigest()
p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
dg=a.root/'build/write-supersession-m3-v1-r01/DGAI/src/tests/build_disk_index.cpp'; od=a.root/'build/write-supersession-m3-v1-r01/OdinANN/src/tests/build_disk_index.cpp'
measured={'DGAI-R32':{'build_seconds':2402.299944796134,'peak_rss_bytes':138574192*1024,'final_index_bytes':14131068900,'evidence':str((a.root/'results/pilot3_sift10m_p1r08/f0/DGAI/p1r08-dgai-01/build_resources.json').resolve())},
 'OdinANN-R96':{'build_seconds':1486.9920104711782,'peak_rss_bytes':11172760*1024,'final_index_bytes':8480140468,'evidence':str((a.root/'results/pilot3_sift10m_p1r08/f0/OdinANN/p1r08-odin-01/build_resources.json').resolve())}}
audit={'schema':'dynamic-vamana-m3-matched-r-comparability-audit-v1','status':'complete','actual_builds_started':False,
 'explicit_R_support':{'DGAI':{'supported':[32,96],'evidence':str(dg.resolve()),'sha256':sha(dg),'cli':'build_disk_index ... <R> <L> <B> <M> <T> ...'},
  'OdinANN':{'supported':[32,96],'evidence':str(od.resolve()),'sha256':sha(od),'cli':'build_disk_index ... <R> <L_or_L1> <PQ_bytes> <M> <T> ...'}},
 'runtime_parameter_matching':{'feasible':True,'code_change':'small canary/driver parameter plumbing; no core index format change',
  'parameters':['R','L','C','beam_width','alpha'],'caveat':'Names can be matched numerically, but candidate generation, pruning and I/O-engine semantics remain system-specific.'},
 'record_layout':{'formula_attr0_float128':'512 + 4*(R+1) bytes','R32':{'record_bytes':644,'records_per_4k_page':6},'R96':{'record_bytes':900,'records_per_4k_page':4},
  'same_R_graph_vector_record_equal':True,'remaining_layout_differences':['PQ neighbor representation/files','metadata and tags','DGAI combined graph/vector conventions vs Odin neighbor handler','publish shadow-copy path']},
 'input_matching':{'same_build_input':True,'same_active_set':True,'input':'datasets/sift10m/active_cp00.bin','active_count':8000000},
 'measured_reference_builds':measured,
 'factorial_estimate':{'DGAI-R32':{'time_minutes':[40,45],'peak_ram_gib':[132,140],'final_space_gib':[13,15],'confidence':'measured'},
  'DGAI-R96':{'time_minutes':[60,120],'peak_ram_gib':[160,220],'final_space_gib':[16,19],'confidence':'extrapolated; must preflight >=220 GiB RAM'},
  'OdinANN-R32':{'time_minutes':[15,25],'peak_ram_gib':[8,12],'final_space_gib':[5,7],'confidence':'extrapolated'},
  'OdinANN-R96':{'time_minutes':[24,30],'peak_ram_gib':[10,13],'final_space_gib':[7,9],'confidence':'measured'},
  'four_base_total':{'sequential_time_hours':[2.3,3.7],'persistent_space_gib':[41,50],'recommended_nvme_headroom_gib':100,'code_change':'parameterized build wrappers plus matched runtime-driver configuration; no algorithm change'}},
 'remaining_confounds':['search/candidate path','pruning implementation','I/O engine (libaio vs io_uring)','page cache keying and neighbor handler','publish/save implementation','default L/C/beam/alpha semantics'],
 'can_answer':['effect of R/layout fanout within each implementation','whether cross-system write gap remains under matched numerical configuration'],
 'cannot_answer':['online visibility as a causal mechanism','a single isolated algorithmic factor across different implementations','performance of a future coalescing design'],
 'research_judgment':'Technically feasible and necessary before any cross-system causal claim, but not needed to answer M3 within-implementation pre-submit supersession opportunity.'}
a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(audit,indent=2)+'\n'); print(a.output)
