#!/usr/bin/env python3
"""Validate the structure of an exact location-ID truthset before tag remap."""
from __future__ import annotations

import argparse, json, struct
from pathlib import Path
import numpy as np


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--truthset", type=Path, required=True); p.add_argument("--nquery", type=int, required=True); p.add_argument("--k", type=int, required=True); p.add_argument("--location-count", type=int, required=True); p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    n, k = struct.unpack("<II", a.truthset.open("rb").read(8))
    if (n, k) != (a.nquery, a.k) or a.truthset.stat().st_size != 8 + n * k * 8: raise SystemExit("location truthset shape/size mismatch")
    ids = np.memmap(a.truthset, dtype="<u4", mode="r", offset=8, shape=(n, k)); dists = np.memmap(a.truthset, dtype="<f4", mode="r", offset=8+n*k*4, shape=(n,k))
    if int(ids.max()) >= a.location_count or np.any(np.diff(np.sort(np.asarray(ids),axis=1),axis=1)==0): raise SystemExit("invalid/duplicate location IDs")
    if not np.isfinite(dists).all() or np.any(dists[:,1:] < dists[:,:-1]): raise SystemExit("invalid location distances")
    report={"schema":"dynamic-vamana-location-truthset-validation-v1","status":"pass","nquery":n,"k":k,"location_count":a.location_count,"all_ids_in_range":True,"row_ids_unique":True,"distances_finite":True,"distances_monotonic":True}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(report,indent=2)+"\n")


if __name__ == "__main__": main()
