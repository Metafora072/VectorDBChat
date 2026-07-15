#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, struct
from pathlib import Path
import numpy as np

p = argparse.ArgumentParser()
p.add_argument("--truthset", type=Path, required=True)
p.add_argument("--tag", type=int, required=True)
p.add_argument("--query-row", type=int, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
n, k = struct.unpack("<II", a.truthset.open("rb").read(8))
ids = np.memmap(a.truthset, dtype="<u4", mode="r", offset=8, shape=(n, k))
if not 0 <= a.query_row < n or a.tag not in set(map(int, ids[a.query_row])):
    raise SystemExit("required tag absent from truthset row")
a.output.write_text(json.dumps({"schema": "dynamic-vamana-truthset-required-tag-v1", "status": "pass", "query_row": a.query_row, "required_tag": a.tag, "present": True}, indent=2) + "\n")
