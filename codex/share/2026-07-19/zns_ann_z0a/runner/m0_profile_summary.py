#!/usr/bin/env python3
"""Canonicalize the accepted M0-v5 ledger for off/on comparisons."""
import argparse, json
from collections import Counter
from pathlib import Path


def main():
    p=argparse.ArgumentParser(); p.add_argument('--profile',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    d=json.loads(a.profile.read_text())
    if d.get('schema')!='dynamic-vamana-write-attribution-m0-v5': raise SystemExit('not accepted M0-v5 schema')
    totals=d.get('ledger_totals',{})
    phases=Counter(); roles=Counter(); page_events=0
    for row in d.get('buckets',[]):
        phases[row['phase']]+=int(row['request_touches'])
        roles[row['component']]+=int(row['request_touches'])
        page_events+=int(row['page_write_touches'])
    out={
      'schema':'zns-ann-z0a-accepted-profile-summary-v1','status':'pass',
      'application_bytes':sum(int(v['requested_bytes']) for v in totals.values()),
      'request_count':sum(int(v['request_count']) for v in totals.values()),
      'page_event_count':page_events,'phase_counts':dict(sorted(phases.items())),
      'role_counts':dict(sorted(roles.items())),'ledger_totals':totals,
    }
    a.output.write_text(json.dumps(out,indent=2)+'\n')

if __name__=='__main__': main()
