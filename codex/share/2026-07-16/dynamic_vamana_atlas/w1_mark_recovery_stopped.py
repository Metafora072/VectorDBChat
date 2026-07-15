#!/usr/bin/env python3
"""Atomically mark an R02 execution stopped after a fail-closed stage error."""
from __future__ import annotations
import argparse, datetime, json, os
from pathlib import Path

def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--phase", required=True); p.add_argument("--exit-code", type=int, required=True); a = p.parse_args()
    if not a.manifest.is_file(): return
    data = json.loads(a.manifest.read_text()); data.update({"status": "stopped_failed", "stopped_phase": a.phase,
        "exit_code": a.exit_code, "stopped_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    temp = a.manifest.with_suffix(a.manifest.suffix + f".tmp.{os.getpid()}")
    temp.write_text(json.dumps(data, indent=2) + "\n"); os.replace(temp, a.manifest)

if __name__ == "__main__": main()
