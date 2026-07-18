#!/usr/bin/env python3
import argparse,json
from pathlib import Path

def load(p): return json.loads(p.read_text())
def main():
    p=argparse.ArgumentParser(); p.add_argument('--raw',type=Path,required=True); p.add_argument('--accepted',type=Path,required=True); p.add_argument('--ledger',type=Path,required=True); p.add_argument('--meta',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    raw,accepted,ledger,meta=map(load,(a.raw,a.accepted,a.ledger,a.meta))
    checks={
      'raw_status':raw.get('status')=='pass','meta_status':meta.get('status')=='complete','ledger_status':ledger.get('status')=='complete',
      'zero_drops':raw.get('dropped_events')==ledger.get('dropped_events')==meta.get('dropped_events')==0,
      'request_count':raw.get('request_count')==accepted.get('request_count')==ledger.get('accepted_requests')==ledger.get('completed_requests'),
      'requested_bytes':raw.get('requested_bytes')==accepted.get('application_bytes')==ledger.get('requested_bytes'),
      'returned_bytes':raw.get('successful_returned_bytes')==ledger.get('returned_bytes')==accepted.get('application_bytes'),
      'page_events':raw.get('page_event_count')==accepted.get('page_event_count'),
      'request_page_closure':raw.get('request_to_page_byte_closure') is True,
      'no_failed_requests':raw.get('failed_requests')==ledger.get('failed_requests')==0,
      'sequence_timestamp_order':raw.get('submit_timestamp_sequence_inversions')==0 and raw.get('completion_timestamp_sequence_inversions')==0,
      'identity':meta.get('identity_errors')==0 and raw.get('object_count',0)>0,
    }
    out={'schema':'zns-ann-z0a-cross-ledger-closure-v1','status':'pass' if all(checks.values()) else 'fail','checks':checks,'raw':raw,'accepted':accepted}
    a.output.write_text(json.dumps(out,indent=2)+'\n')
    if out['status']!='pass': raise SystemExit(1)
if __name__=='__main__': main()
