#!/usr/bin/env python3
import argparse, json, statistics
from pathlib import Path


def load(p): return json.loads(p.read_text())


def interval(values):
    return {'min': min(values), 'median': statistics.median(values), 'max': max(values)}


def overlaps(left, right):
    return max(min(left), min(right)) <= min(max(left), max(right))


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); ap.add_argument('--output',type=Path,required=True); a=ap.parse_args()
    rows=[]
    for d in sorted(a.root.glob('z0a-*')):
        status=load(d/'run_status.json'); accepted=load(d/'accepted_summary.json'); active=load(d/'active_audit.json')
        row={**status,'active_status':active['status'],**{f'accepted_{k}':v for k,v in accepted.items() if k not in ('schema','status')}}
        if status['mode']=='on':
            trace=load(d/'trace_summary.json'); closure=load(d/'closure.json')
            row.update({f'trace_{k}':v for k,v in trace.items() if k not in ('schema','status')}); row['closure_status']=closure['status']
        rows.append(row)
    gates={}; passed=True
    for system in ('DGAI','OdinANN'):
        group=[r for r in rows if r['system']==system]
        off=[r['wall_seconds'] for r in group if r['mode']=='off']; on=[r['wall_seconds'] for r in group if r['mode']=='on']
        if len(off)<3 or len(off)!=len(on): raise SystemExit(f'{system}: expected equal off/on counts, at least 3 each')
        overhead=(statistics.median(on)/statistics.median(off)-1)*100
        onrows=[r for r in group if r['mode']=='on']
        exact=all(r['trace_dropped_events']==0 and r['trace_request_to_page_byte_closure'] and r['closure_status']=='pass' and r['active_status']=='pass' for r in onrows)
        fields=('accepted_application_bytes','accepted_request_count','accepted_page_event_count')
        exact_structure=len({tuple(r[f] for f in fields)+(json.dumps(r['accepted_phase_counts'],sort_keys=True),) for r in group})==1
        offrows=[r for r in group if r['mode']=='off']; onrows=[r for r in group if r['mode']=='on']
        intrinsic_off_variation=any(len({r[f] for r in offrows})>1 for f in fields)
        phase_names_identical=len({tuple(sorted(r['accepted_phase_counts'])) for r in group})==1
        overlap={f:overlaps([r[f] for r in offrows],[r[f] for r in onrows]) for f in fields}
        distribution_compatible=intrinsic_off_variation and phase_names_identical and all(overlap.values())
        structure=exact_structure or distribution_compatible
        gates[system]={
            'off_wall_seconds': interval(off),
            'on_wall_seconds': interval(on),
            'overhead_percent': overhead,
            'zero_drop_and_closure': exact,
            'write_phase_structure_exactly_identical': exact_structure,
            'intrinsic_trace_off_variation': intrinsic_off_variation,
            'phase_names_identical': phase_names_identical,
            'off_on_metric_ranges_overlap': overlap,
            'write_phase_structure_observationally_compatible': structure,
            'structure_rule': 'exact equality, or overlapping off/on ranges when trace-off itself is nondeterministic',
            'pass': exact and structure and abs(overhead)<=5.0,
        }
        passed &= gates[system]['pass']
    out={'schema':'zns-ann-z0a-run-summary-v1','status':'pass' if passed else 'fail','rows':rows,'instrumentation_gates':gates}
    a.output.write_text(json.dumps(out,indent=2)+'\n')
    if not passed: raise SystemExit(1)


if __name__=='__main__': main()
