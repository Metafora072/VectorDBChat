#!/usr/bin/env python3
import csv
import datetime as dt
import glob
import json
import math
import os
import random
import re
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/p0_interference/formal")


def pct(vals, p):
    vals = sorted(vals)
    if not vals:
        return math.nan
    return vals[min(len(vals) - 1, max(0, math.ceil(p * len(vals)) - 1))]


def load_meta(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            out[k] = v
    return out


def app_metrics(run):
    rows = list(csv.DictReader(open(run / "ops.csv", encoding="utf-8")))
    meta = load_meta(run / "meta.txt")
    start = int(meta["measure_start_us"])
    end = int(meta["measure_end_us"])
    duration = 10.0
    result = {"run": run.name, "system": rows[0]["system"], "query_qps": float(meta["query_qps"]),
              "update_qps": float(meta["update_qps"]), "measure_wall_s": (end - start) / 1e6}
    for op in ("query", "update"):
        x = [r for r in rows if r["op"] == op]
        completed_in_window = sum(int(r["end_us"]) <= start + int(duration * 1e6) for r in x)
        result[f"{op}_count"] = len(x)
        result[f"{op}_throughput"] = completed_in_window / duration
        result[f"{op}_failure_rate"] = sum(r["status"] != "ok" for r in x) / len(x) if x else 0
        for field in ("total_us", "service_us", "queue_us"):
            vals = [float(r[field]) for r in x]
            for label, p in (("p50", .5), ("p95", .95), ("p99", .99)):
                result[f"{op}_{field}_{label}"] = pct(vals, p)
        if op == "query":
            result["recall_mean"] = statistics.mean(float(r["recall"]) for r in x) if x else math.nan
            result["query_ios_mean"] = statistics.mean(float(r["n_ios"]) for r in x) if x else math.nan
    return result, start, end


def iostat_metrics(run, start_us, end_us):
    samples = []
    current_ts = None
    headers = None
    for line in open(run / "iostat.txt", encoding="utf-8", errors="replace"):
        s = line.strip()
        if re.fullmatch(r"\d\d/\d\d/\d\d \d\d:\d\d:\d\d", s):
            current_ts = int(dt.datetime.strptime(s, "%m/%d/%y %H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp() * 1e6)
        elif s.startswith("Device"):
            headers = s.split()
        elif s.startswith("nvme8n1") and current_ts and headers and start_us <= current_ts <= end_us:
            vals = s.split()
            row = {headers[i]: float(vals[i]) for i in range(1, min(len(headers), len(vals)))}
            samples.append(row)
    wanted = ["r/s", "rkB/s", "r_await", "rareq-sz", "w/s", "wkB/s", "w_await", "wareq-sz", "aqu-sz", "%util"]
    return {f"device_{k}": statistics.mean(x[k] for x in samples if k in x) if samples else math.nan for k in wanted}


def wchan_metrics(run, start_us, end_us):
    counts = Counter()
    for r in csv.DictReader(open(run / "wchan.csv", encoding="utf-8")):
        if start_us <= int(r["ts_us"]) <= end_us:
            counts[r["wchan"]] += 1
    total = sum(counts.values())
    futex = sum(v for k, v in counts.items() if "futex" in k)
    aio = sum(v for k, v in counts.items() if "event" in k or "aio" in k)
    return {"wchan_samples": total, "wchan_futex_fraction": futex / total if total else math.nan,
            "wchan_aio_fraction": aio / total if total else math.nan, "wchan_top": counts.most_common(8)}


def pidstat_metrics(run, start_us, end_us):
    samples = []
    headers = None
    day = dt.datetime.fromtimestamp(start_us / 1e6, tz=dt.timezone.utc).date()
    for line in open(run / "pidstat.txt", encoding="utf-8", errors="replace"):
        s = line.strip()
        if s.startswith("# Time"):
            headers = s[2:].split()
            continue
        if not headers or not re.match(r"^\d\d:\d\d:\d\d\s", s):
            continue
        vals = s.split()
        if len(vals) != len(headers):
            continue
        tm = dt.datetime.strptime(vals[0], "%H:%M:%S").time()
        ts = int(dt.datetime.combine(day, tm, tzinfo=dt.timezone.utc).timestamp() * 1e6)
        if start_us <= ts <= end_us:
            samples.append(dict(zip(headers, vals)))
    wanted = ["%usr", "%system", "%wait", "%CPU", "kB_rd/s", "kB_wr/s", "cswch/s", "nvcswch/s"]
    return {"process_" + k: statistics.mean(float(x[k]) for x in samples if k in x) if samples else math.nan
            for k in wanted}


def bootstrap_ci(vals, seed=20260712):
    if not vals:
        return [math.nan, math.nan]
    rng = random.Random(seed)
    boots = sorted(statistics.mean(vals[rng.randrange(len(vals))] for _ in vals) for _ in range(10000))
    return [boots[249], boots[9749]]


def main():
    runs = []
    for p in sorted(ROOT.glob("*")):
        if not (p / "exit_status").exists() or (p / "exit_status").read_text().strip() != "0":
            continue
        app, start, end = app_metrics(p)
        app.update(iostat_metrics(p, start, end))
        app.update(pidstat_metrics(p, start, end))
        app.update(wchan_metrics(p, start, end))
        m = re.match(r"(dgai|odin)_q(\d+)_u(\d+)_rep(\d+)", p.name)
        app["rep"] = int(m.group(4))
        runs.append(app)

    by = {(r["system"], r["query_qps"], r["update_qps"], r["rep"]): r for r in runs}
    paired = []
    for r in runs:
        if r["query_qps"] <= 0 or r["update_qps"] <= 0:
            continue
        qkey = (r["system"], r["query_qps"], 0.0, r["rep"])
        ukey = (r["system"], 0.0, r["update_qps"], r["rep"])
        if qkey not in by or ukey not in by:
            continue
        qb = by[qkey]
        ub = by[ukey]
        paired.append({
            "system": r["system"], "query_qps": r["query_qps"], "update_qps": r["update_qps"], "rep": r["rep"],
            "query_p99_degradation_pct": 100 * (r["query_total_us_p99"] / qb["query_total_us_p99"] - 1),
            "query_p50_degradation_pct": 100 * (r["query_total_us_p50"] / qb["query_total_us_p50"] - 1),
            "query_throughput_change_pct": 100 * (r["query_throughput"] / qb["query_throughput"] - 1),
            "update_throughput_change_pct": 100 * (r["update_throughput"] / ub["update_throughput"] - 1),
            "recall_delta": r["recall_mean"] - qb["recall_mean"],
            "mixed_query_p99_us": r["query_total_us_p99"], "baseline_query_p99_us": qb["query_total_us_p99"],
            "mixed_update_throughput": r["update_throughput"], "baseline_update_throughput": ub["update_throughput"],
            "device_r_iops": r["device_r/s"], "device_w_iops": r["device_w/s"],
            "device_r_await_ms": r["device_r_await"], "device_w_await_ms": r["device_w_await"],
            "device_queue_depth": r["device_aqu-sz"], "device_util_pct": r["device_%util"],
            "process_cpu_pct": r["process_%CPU"], "process_usr_pct": r["process_%usr"],
            "process_sys_pct": r["process_%system"], "process_wait_pct": r["process_%wait"],
            "process_cswch_s": r["process_cswch/s"], "process_nvcswch_s": r["process_nvcswch/s"],
            "wchan_futex_fraction": r["wchan_futex_fraction"]
        })

    groups = []
    keys = sorted({(r["system"], r["query_qps"], r["update_qps"]) for r in paired})
    for key in keys:
        x = [r for r in paired if (r["system"], r["query_qps"], r["update_qps"]) == key]
        row = {"system": key[0], "query_qps": key[1], "update_qps": key[2], "reps": len(x)}
        for field in ("query_p99_degradation_pct", "query_p50_degradation_pct", "query_throughput_change_pct",
                      "update_throughput_change_pct", "recall_delta", "mixed_query_p99_us", "baseline_query_p99_us",
                      "mixed_update_throughput", "baseline_update_throughput", "device_r_iops", "device_w_iops",
                      "device_r_await_ms", "device_w_await_ms", "device_queue_depth", "device_util_pct",
                      "process_cpu_pct", "process_usr_pct", "process_sys_pct", "process_wait_pct",
                      "process_cswch_s", "process_nvcswch_s",
                      "wchan_futex_fraction"):
            vals = [r[field] for r in x]
            row[field] = statistics.mean(vals)
            if field in ("query_p99_degradation_pct", "update_throughput_change_pct", "recall_delta"):
                row[field + "_ci95"] = bootstrap_ci(vals)
        groups.append(row)

    out = {"runs": runs, "paired": paired, "groups": groups}
    output = ROOT.parent / "analysis.json"
    output.write_text(json.dumps(out, indent=2, allow_nan=True), encoding="utf-8")
    with open(ROOT.parent / "service_curves.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=groups[0].keys())
        w.writeheader(); w.writerows(groups)
    print(json.dumps(groups, indent=2, allow_nan=True))


if __name__ == "__main__":
    main()
