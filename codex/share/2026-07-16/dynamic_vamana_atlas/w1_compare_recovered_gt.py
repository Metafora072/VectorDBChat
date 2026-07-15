#!/usr/bin/env python3
"""Prove that recovery changes only the known query-7150 defective row."""
from __future__ import annotations

import argparse, json, struct
from pathlib import Path
import numpy as np


def truth(path: Path):
    n,k=struct.unpack("<II",path.open("rb").read(8)); ids=np.memmap(path,dtype="<u4",mode="r",offset=8,shape=(n,k)); ds=np.memmap(path,dtype="<f4",mode="r",offset=8+n*k*4,shape=(n,k)); return n,k,ids,ds


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--failed",type=Path,required=True); p.add_argument("--recovered",type=Path,required=True); p.add_argument("--qid",type=int,default=7150); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    n,k,old_i,old_d=truth(a.failed); n2,k2,new_i,new_d=truth(a.recovered)
    if (n,k)!=(n2,k2) or (n,k)!=(10000,100): raise SystemExit("truthset shape mismatch")
    mask=np.ones(n,dtype=bool); mask[a.qid]=False
    if np.asarray(old_i[mask]).tobytes() != np.asarray(new_i[mask]).tobytes() or np.asarray(old_d[mask]).tobytes() != np.asarray(new_d[mask]).tobytes():
        raise SystemExit("a non-7150 row changed bytewise during GT recovery")
    old_pairs={(int(i),float(d)) for i,d in zip(old_i[a.qid,:99],old_d[a.qid,:99])}; new_pairs={(int(i),float(d)) for i,d in zip(new_i[a.qid],new_d[a.qid])}
    if not old_pairs.issubset(new_pairs) or 0 not in set(map(int,new_i[a.qid])): raise SystemExit("query 7150 did not preserve old 99 entries and restore tag 0")
    report={"schema":"dynamic-vamana-w1-recovered-gt-comparison-v1","status":"pass","unchanged_rows_byte_identical":9999,"changed_query":a.qid,"old_valid_pairs_preserved":99,"tag_zero_restored":True,"old_invalid_tail":{"id":int(old_i[a.qid,99]),"distance":float(old_d[a.qid,99])}}
    a.output.write_text(json.dumps(report,indent=2)+"\n")


if __name__=="__main__":main()
