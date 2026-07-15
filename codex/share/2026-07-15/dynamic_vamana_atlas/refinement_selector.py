#!/usr/bin/env python3
"""Choose the next measured integer L for one P2-M Recall-floor search."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def semantic_identity(row: dict) -> str:
    identity = dict(row.get("artifact_identity") or {})
    identity.pop("frozen_utc", None)
    return json.dumps(identity, sort_keys=True)


def load_groups(root: Path, system: str, tq: int) -> dict[int, dict]:
    grouped: dict[int, list[tuple[Path, dict]]] = defaultdict(list)
    for path in root.glob(f"{system}/tq{tq}/L*/r*/point.json"):
        row = json.loads(path.read_text())
        grouped[int(row["L"])].append((path, row))
    result = {}
    for l, values in grouped.items():
        if any(row.get("valid") is not True for _, row in values):
            raise SystemExit(f"invalid point in {root}/{system}/L{l}")
        identities = {semantic_identity(row) for _, row in values}
        if not identities or "{}" in identities or len(identities) != 1:
            raise SystemExit(f"artifact identity mismatch in {root}/{system}/L{l}")
        recalls = [float(row["recall_at_10"]) for _, row in values]
        result[l] = {"count": len(values), "median": statistics.median(recalls),
                     "minimum": min(recalls), "maximum": max(recalls),
                     "paths": [str(path) for path, _ in values], "identity": next(iter(identities))}
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--coarse-root", type=Path, required=True)
    p.add_argument("--refinement-root", type=Path, required=True)
    p.add_argument("--system", required=True)
    p.add_argument("--target", type=float, required=True)
    p.add_argument("--lower", type=int, required=True)
    p.add_argument("--upper", type=int, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    coarse = load_groups(args.coarse_root, args.system, 1)
    refine = load_groups(args.refinement_root, args.system, 1)
    groups = dict(coarse); groups.update(refine)
    for l in (args.lower, args.upper):
        if l not in groups or groups[l]["count"] < 3:
            payload = {"action": "measure", "L": l, "repeat_count": 3, "reason": "missing_initial_bracket"}
            args.output.write_text(json.dumps(payload, indent=2) + "\n"); return
    lows = [l for l, g in groups.items() if args.lower <= l <= args.upper and g["count"] >= 3 and g["median"] < args.target]
    highs = [l for l, g in groups.items() if args.lower <= l <= args.upper and g["count"] >= 3 and g["median"] >= args.target]
    if not lows or not highs:
        raise SystemExit("no measured lower/upper Recall bracket")
    lo, hi = max(lows), min(highs)
    if lo >= hi:
        raise SystemExit(f"invalid bracket lo={lo} hi={hi}")
    for l in (lo, hi):
        g = groups[l]
        if g["count"] == 3 and g["minimum"] < args.target <= g["maximum"]:
            payload = {"action": "measure", "L": l, "repeat_count": 5, "reason": "threshold_crossing_noise"}
            args.output.write_text(json.dumps(payload, indent=2) + "\n"); return
    if hi > lo + 1:
        mid = (lo + hi) // 2
        g = groups.get(mid)
        payload = {"action": "measure", "L": mid, "repeat_count": 3, "reason": "integer_bisection"}
        if g and g["count"] >= 3:
            raise SystemExit("bisection did not shrink bracket")
        args.output.write_text(json.dumps(payload, indent=2) + "\n"); return
    final = groups[hi]
    # A coarse-only high endpoint is valid bracket evidence but must be repeated
    # in the P2-M run before it may become an official Tq=1 result.
    if hi not in refine or refine[hi]["count"] < 3:
        payload = {"action": "measure", "L": hi, "repeat_count": 3, "reason": "materialize_final_refinement_point"}
    elif final["median"] > args.target + 0.005:
        payload = {"action": "unavailable", "L": hi, "reason": "unavailable_due_to_parameter_granularity", "median": final["median"]}
    else:
        payload = {"action": "selected", "L": hi, "median": final["median"], "minimum": final["minimum"],
                   "maximum": final["maximum"], "repeat_count": final["count"], "raw_paths": final["paths"]}
    args.output.write_text(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
