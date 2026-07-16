#!/usr/bin/env python3
"""Freeze and independently validate the accepted R05 DGAI attempt."""
from __future__ import annotations
import argparse, datetime, hashlib, json, math, re, statistics, struct
from pathlib import Path

ROOT = Path("/home/ubuntu/pz/VectorDB/data/VectorDB/dynamic_vamana_atlas")
MARKERS = ["clone_ready", "index_loaded", "ingest_begin", "ingest_end",
           "online_visibility_unsupported", "publish_begin", "publish_end",
           "fresh_process_probe_begin", "fresh_process_visibility_verified"]
GT_SHA = "4703d2d8a12c1c045c60de56819ccb058e91bc28e0f1883d18573f9917b32c28"

def sha(p: Path) -> str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(8<<20),b""): h.update(b)
    return h.hexdigest()

def load(p: Path): return json.loads(p.read_text())

def io_delta(d: dict, dev="259:10"):
    samples=d.get("samples",[])
    def row(s): return next((x for x in s.get("cgroup_io_stat",[]) if x.get("device")==dev),{})
    if not samples:return {"read_bytes":0,"write_bytes":0}
    a,b=row(samples[0]),row(samples[-1])
    return {"read_bytes":int(b.get("rbytes",0))-int(a.get("rbytes",0)),
            "write_bytes":int(b.get("wbytes",0))-int(a.get("wbytes",0))}

def queries(attempt: Path):
    out=[]
    for p in sorted(attempt.glob("*_L*_r*.metrics.json")):
        m=re.fullmatch(r"(pre_cp00|post_cp01)_L(\d+)_r(\d+)\.metrics\.json",p.name)
        if not m: continue
        phase,L,rep=m.groups(); metric=load(p); valid=load(p.with_name(p.name.replace(".metrics.json",".validation.json")))
        resource=load(p.with_name(p.name.replace(".metrics.json",".resources.json")))
        ids=p.with_name(p.name.replace(".metrics.json",".result_ids.bin"))
        n,k=struct.unpack("<II",ids.read_bytes()[:8])
        required=("qps","mean_latency_us","p50_latency_us","p95_latency_us","p99_latency_us","mean_ios","recall_at_10_percent")
        assert (n,k)==(10000,10) and ids.stat().st_size==8+n*k*4
        assert all(math.isfinite(float(metric[x])) for x in required)
        assert valid.get("all_result_ids_active") is True and 0<=float(valid["recall_at_10_normalized"])<=1
        assert resource.get("returncode")==0 and not any(int(x.get("cgroup_memory_events",{}).get(y,0)) for x in resource.get("samples",[]) for y in ("oom","oom_kill"))
        out.append({"phase":phase,"L":int(L),"repeat":int(rep),"recall_at_10":float(valid["recall_at_10_normalized"]),
                    "qps":float(metric["qps"]),"p99_latency_us":float(metric["p99_latency_us"]),**io_delta(resource)})
    assert len(out)==12
    for phase in ("pre_cp00","post_cp01"):
        for L in (64,128): assert len([x for x in out if x["phase"]==phase and x["L"]==L])==3
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",type=Path,default=ROOT); ap.add_argument("--output-json",type=Path,required=True)
    ap.add_argument("--output-tsv",type=Path,required=True); ap.add_argument("--report",type=Path,required=True); ap.add_argument("--expected-report",type=Path)
    a=ap.parse_args(); r=a.root.resolve(); rr=r/"results/pilot3_sift10m_w1_r05"; attempt=rr/"DGAI/cp01-05"; clone=r/"formal/pilot3_sift10m_w1_r05/DGAI/cp01-05"
    for p in (a.output_json,a.output_tsv):
        if p.exists(): raise SystemExit(f"freeze output overwrite refused: {p}")
    assert (attempt/"FORMAL_W1_CANARY_OK").is_file()
    execution=load(rr/"execution_manifest.json"); assert (execution.get("status"),execution.get("stopped_phase"),execution.get("exit_code"))==("stopped_failed","OdinANN_canary",1)
    names=[json.loads(x)["marker"] for x in (attempt/"markers.jsonl").read_text().splitlines() if x.strip()]; assert names==MARKERS
    canary=load(attempt/"canary.json"); active=load(attempt/"active_audit.json"); fresh=load(attempt/"fresh_probe.json")
    assert canary.get("schema")=="dynamic-vamana-w1-canary-collection-v3" and canary.get("online_visibility_supported") is False
    assert active.get("expected_exact_match") is True and active.get("active_tag_count")==8_000_000 and active.get("duplicate_count")==0
    rows=fresh.get("rows",[]); assert len(rows)==18 and all(x.get("passed") for x in rows)
    q=queries(attempt)
    base_audit=load(attempt/"base_immutability.json"); assert base_audit.get("status")=="pass"
    clone_manifest=load(clone/"clone_manifest.json"); assert clone_manifest.get("schema")=="dynamic-vamana-w1-clone-v3"
    assert clone_manifest.get("base_content_manifest_sha256")==clone_manifest.get("clone_content_manifest_sha256")
    resource=load(attempt/"resources.json"); assert resource.get("returncode")==0
    assert not any(int(x.get("cgroup_memory_events",{}).get(y,0)) for x in resource.get("samples",[]) for y in ("oom","oom_kill"))
    assert sha(r/"groundtruth/sift10m/w1_r02/gt_cp01")==GT_SHA
    bad=re.compile(r"fatal|assert|EBADF|negative CQE|I/O error",re.I)
    assert not bad.search("\n".join(p.read_text(errors="replace") for p in attempt.glob("*.log")))
    evidence=[]
    for p in sorted(x for x in attempt.rglob("*") if x.is_file()): evidence.append((p.relative_to(attempt).as_posix(),p.stat().st_size,sha(p)))
    tsv="relative_path\tsize_bytes\tsha256\n"+"".join(f"{n}\t{s}\t{h}\n" for n,s,h in evidence)
    a.output_tsv.parent.mkdir(parents=True,exist_ok=True); a.output_tsv.write_text(tsv)
    phase=canary["phase_device_accounting"]; stats={"ingestion_seconds":canary["ingestion_seconds"],"ingestion_ops_s":canary["ingestion_throughput_ops_s"],
      "restart_visibility_seconds":canary["restart_visibility_seconds"],"restart_visible_ops_s":canary["restart_visible_throughput_ops_s"],
      "persistent_growth_bytes":canary["persistent_index_growth_bytes"],"phase_device_accounting":phase,
      "elapsed_seconds":resource["elapsed_seconds"],"peak_process_tree_rss_bytes":int(resource.get("peak_process_tree_rss_kb",0))*1024,
      "cgroup_memory_peak_bytes":max([int(x.get("cgroup_memory_peak") or 0) for x in resource.get("samples",[])] or [0]),
      "clone":{"wall_seconds":clone_manifest["clone_wall_seconds"],"apparent_bytes":clone_manifest["clone_space"]["apparent_bytes"],"allocated_bytes":clone_manifest["clone_space"]["allocated_bytes"],"device_delta":clone_manifest["clone_device_delta"],"normalization_seconds":clone_manifest["normalization_elapsed_seconds"],"normalization_metadata_operations":clone_manifest["normalization_metadata_operations"]}}
    report={"schema":"dynamic-vamana-w1-r05-dgai-freeze-v1","status":"pass","frozen_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
      "source_run":"pilot3_sift10m_w1_r05","attempt":"cp01-05","gt_sha256":GT_SHA,"markers":names,"query_runs":q,"statistics":stats,
      "evidence_manifest":{"file_count":len(evidence),"sha256":sha(a.output_tsv)},"base_immutability":base_audit,"clone_manifest_sha256":sha(clone/"clone_manifest.json")}
    a.output_json.write_text(json.dumps(report,indent=2)+"\n")
    groups=[]
    for phase_name in ("pre_cp00","post_cp01"):
      for L in (64,128):
        xs=[x for x in q if x["phase"]==phase_name and x["L"]==L]
        groups.append(f"| {phase_name} | {L} | "+" / ".join(f"{x['recall_at_10']:.4f}" for x in xs)+f" | {statistics.median(x['qps'] for x in xs):.2f} | {statistics.median(x['p99_latency_us'] for x in xs):.1f} |")
    c=stats["clone"]
    md=["# Dynamic Vamana W1 R05 DGAI Partial Results","","R05 DGAI 是独立有效的 1% canary 证据；R05 后续 OdinANN pre-update stop 不使该 attempt 失效。R06 不重跑 DGAI。","","## Update 与资源","",f"- ingestion: `{stats['ingestion_seconds']:.6f}s`, `{stats['ingestion_ops_s']:.3f} ops/s`",f"- restart visibility: `{stats['restart_visibility_seconds']:.6f}s`, `{stats['restart_visible_ops_s']:.3f} ops/s`",f"- ingest NVMe R/W: `{phase['ingest_device_delta']['rbytes']}/{phase['ingest_device_delta']['wbytes']}` B",f"- publish NVMe R/W: `{phase['publish_device_delta']['rbytes']}/{phase['publish_device_delta']['wbytes']}` B",f"- end-to-end NVMe R/W: `{phase['end_to_end_device_delta']['rbytes']}/{phase['end_to_end_device_delta']['wbytes']}` B",f"- persistent growth: `{stats['persistent_growth_bytes']}` B",f"- update probe elapsed / peak RSS / cgroup peak: `{stats['elapsed_seconds']:.3f}s / {stats['peak_process_tree_rss_bytes']} B / {stats['cgroup_memory_peak_bytes']} B`",f"- mutable clone: `{c['wall_seconds']:.3f}s`, apparent/allocated `{c['apparent_bytes']}/{c['allocated_bytes']}` B, clone NVMe R/W `{c['device_delta'].get('rbytes',0)}/{c['device_delta'].get('wbytes',0)}` B",f"- permission normalization: `{c['normalization_seconds']:.6f}s`, `{c['normalization_metadata_operations']}` metadata operations","","## Pre/Post query raw values","","| Phase | L | Recall@10 (r1/r2/r3) | QPS median | P99 median(us) |","|---|---:|---|---:|---:|",*groups,"","Active set exact，fresh probes `18/18`，online visibility 对 DGAI 明确为 unsupported；所有 12 次查询均 exit 0、结果 active、metric finite 且真实读取 NVMe。完整逐文件冻结清单位于 R06 `preflight/r05_dgai_evidence_manifest.tsv`。",""]
    content="\n".join(md)
    if a.expected_report:
        assert a.expected_report.read_text()==content
    if a.report.exists() and a.report.read_text()!=content: raise SystemExit("partial report content mismatch")
    if not a.report.exists(): a.report.write_text(content)

if __name__=="__main__": main()
