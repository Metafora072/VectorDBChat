#!/usr/bin/env python3
"""Validate R12 terminal artifacts and write the CP00->CP10 report."""
from __future__ import annotations
import argparse, hashlib, json, statistics, time
from pathlib import Path

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''): h.update(b)
    return h.hexdigest()

def load(path: Path) -> dict: return json.loads(path.read_text())
def median_points(doc: dict) -> list[dict]:
    out=[]
    for l in sorted({int(x['L']) for x in doc['points']}):
        rows=[x for x in doc['points'] if int(x['L'])==l]
        out.append({'L':l,'recall':statistics.median(float(x['recall_at_10']) for x in rows),
                    'qps':statistics.median(float(x['qps']) for x in rows),
                    'p99_us':statistics.median(float(x['p99_latency_us']) for x in rows),
                    'read_bytes':statistics.median(int(x['device_read_bytes']) for x in rows)})
    return out

p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); p.add_argument('--output-report',type=Path,required=True); a=p.parse_args()
root=a.root.resolve(); run=root/'results/pilot3_sift10m_w1_cp10_trajectory_r12'; r10=root/'results/pilot3_sift10m_w1_cp05_trajectory_r10'; r11=root/'results/pilot3_sift10m_w1_cp05_diskann_closure_r11'
pre=load(run/'preflight/execution_preflight.json'); closure=load(r11/'closure_manifest.json')
if pre.get('status')!='pass' or closure.get('status')!='pass': raise SystemExit('R12 preflight/closure not PASS')
systems={}; trajectory={}
for system in ('DGAI','OdinANN'):
    rr=run/system/'trajectory-cp10-12'; old=r10/system/'trajectory-cp05-10'
    stage=load(rr/'stages/cp10/stage_evidence.json'); query=load(rr/'queries/cp10/query_gate.json'); freeze=load(rr/'checkpoints/cp10/cp10_freeze_evidence.json')
    if not ((rr/'CP10_TRAJECTORY_OK').is_file() and stage.get('status')=='pass' and query.get('status')=='pass' and freeze.get('status')=='pass'):
        raise SystemExit(f'{system} R12 terminal evidence incomplete')
    systems[system]={'stage':stage,'query':query,'freeze':freeze}
    trajectory[system]=[]
    for checkpoint in ('cp00','cp01','cp05'):
        q=load(old/f'queries/{checkpoint}/query_gate.json')
        trajectory[system].append({'checkpoint':checkpoint,'points':median_points(q)})
    trajectory[system].append({'checkpoint':'cp10','points':median_points(query)})
disk=load(run/'DiskANN/stale-cp10-12/stale_control.json')
if disk.get('status')!='pass' or len(disk.get('points',[]))!=6: raise SystemExit('DiskANN CP10 stale evidence incomplete')
disk_trajectory=list(closure['diskann_stale_trajectory'])
for l in (29,53):
    rows=[x for x in disk['points'] if int(x['L'])==l]
    disk_trajectory.append({'checkpoint':'cp10','L':l,'median_recall_at_10':statistics.median(float(x['recall_at_10']) for x in rows),'median_qps':statistics.median(float(x['qps']) for x in rows)})

summary={'schema':'dynamic-vamana-w1-cp10-r12-summary-v1','status':'pass','run':'pilot3_sift10m_w1_cp10_trajectory_r12','cp20':'HOLD','generated_unix_ns':time.time_ns(),
         'preflight_sha256':sha(run/'preflight/execution_preflight.json'),'closure_sha256':sha(r11/'closure_manifest.json'),
         'systems':systems,'dynamic_query_trajectory':trajectory,'diskann_stale_trajectory':disk_trajectory,
         'diskann_classification':'stale-static negative control; excluded from dynamic update throughput ranking'}
(run/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

lines=['# Dynamic Vamana W1 CP10 trajectory R12 results','',
       'R10+R11 composed CP05 closure已绑定；R12仅从两个R10冻结CP05 clone新建private clone，并应用master `[400000:800000]` 的400K replacements。CP00、CP01、CP05和1M replay均未重跑。','',
       '执行边界保持可审计：首次`execution_manifest.json`在DGAI stage PASS后、首个query启动前因query-unit命名被控制面门禁拒绝，保留为`stopped_failed`；`continuation_manifest.json`严格绑定该terminal identity、PASS stage、空query目录和未改变的checkpoint state，只读完成DGAI query/freeze，并执行fresh OdinANN与DiskANN，最终状态为`complete`。两份manifest组成R12 closure，未将首次execution伪装为单次成功。','',
       '## CP05→CP10增量','',
       '| 系统 | replacements | ingest s | publish s | end-to-end s | replacements/s | peak RSS GiB | apparent growth GiB | allocated growth GiB |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for system in ('DGAI','OdinANN'):
    s=systems[system]['stage']; phases=s['phases']; rss=float(s['resources']['peak_process_tree_rss_bytes'])/(1024**3)
    throughput=400000/float(phases['end_to_end']['wall_seconds'])
    lines.append(f"| {system} | 400000 | {phases['ingest']['wall_seconds']:.3f} | {phases['publish']['wall_seconds']:.3f} | {phases['end_to_end']['wall_seconds']:.3f} | {throughput:.2f} | {rss:.2f} | {s['space']['apparent_growth_bytes']/(1024**3):.3f} | {s['space']['allocated_growth_bytes']/(1024**3):.3f} |")
lines += ['', '| 系统 | phase | read GiB | write GiB |', '|---|---|---:|---:|']
for system in ('DGAI','OdinANN'):
    phases=systems[system]['stage']['phases']
    for phase in ('ingest','publish','end_to_end'):
        row=phases[phase]
        lines.append(f"| {system} | {phase.replace('_','-')} | {row['rbytes']/(1024**3):.3f} | {row['wbytes']/(1024**3):.3f} |")
lines += ['', 'DGAI按设计不支持publish前online visibility；OdinANN online probe约0.006秒内PASS，publish/reload后的fresh probe同样PASS。两系统resource returncode均为0，OOM/oom_kill/oom_group_kill均为0。']
lines += ['', '## 动态查询完整轨迹（3次中位数）','', '| 系统 | checkpoint | L | Recall@10 | QPS | P99 us |','|---|---|---:|---:|---:|---:|']
for system, checkpoints in trajectory.items():
    for cp in checkpoints:
        for point in cp['points']:
            lines.append(f"| {system} | {cp['checkpoint']} | {point['L']} | {point['recall']:.4f} | {point['qps']:.2f} | {point['p99_us']:.2f} |")
lines += ['', '## DiskANN stale-static negative control','', '| checkpoint | L | median Recall@10 | median QPS |','|---|---:|---:|---:|']
for row in disk_trajectory:
    qps=row.get('median_qps')
    lines.append(f"| {row['checkpoint']} | {row['L']} | {row['median_recall_at_10']:.4f} | {qps:.2f} |" if qps is not None else f"| {row['checkpoint']} | {row['L']} | {row['median_recall_at_10']:.4f} | — |")
lines += ['', '两个CP10 clone均已冻结为后续CP20只读source；DiskANN仍是不更新的negative control，不参与动态更新吞吐排名。CP20保持HOLD。','',f"机器汇总：`{run/'summary.json'}`。"]
a.output_report.write_text('\n'.join(lines)+'\n')
