#!/usr/bin/env python3
import csv
import os
import sys
import time

pid = int(sys.argv[1])
writer = csv.writer(sys.stdout)
writer.writerow(["ts_us", "tid", "wchan"])
while os.path.isdir(f"/proc/{pid}"):
    task_dir = f"/proc/{pid}/task"
    try:
        tids = os.listdir(task_dir)
    except FileNotFoundError:
        break
    now = time.time_ns() // 1000
    for tid in tids:
        try:
            with open(f"{task_dir}/{tid}/wchan", "r", encoding="utf-8") as f:
                writer.writerow([now, tid, f.read().strip()])
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    sys.stdout.flush()
    time.sleep(0.02)
