#!/usr/bin/env python3
import argparse,json,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--name',required=True);p.add_argument('--reason');a=p.parse_args()
row={'marker':a.name,'monotonic_ns':time.monotonic_ns()}
if a.reason:row['reason']=a.reason
with a.output.open('a') as f:f.write(json.dumps(row)+'\n')
