# Dynamic Vamana W1-C：1% Replace-New 正式执行门禁

**日期**：2026-07-15
**上游报告**：`codex/share/2026-07-15/dynamic_vamana_w1_formal_execution_preflight_0715.md`
**裁决**：**PREFLIGHT PASS；CONDITIONAL FORMAL EXECUTION AUTHORIZED**

---

# 1. 已通过的执行基础

以下项目通过审查：

* formal 与 micro 使用同一状态机；
* F7–F12 已关闭；
  -正式 SIFT10M F0 base 路径正确；
* CP01 artifact map 正确；
  -full corpus 显式传递；
  -clone 白名单正确；
* DGAI/OdinANN canonical binaries 可从 clean checkout 重建；
  -两次 clean build byte-identical；
* OdinANN 使用 `IO_ENGINE=uring`；
* CMake、compile definition 和 `ldd` 均证明没有回退 AIO；
* formal preflight 为只读操作；
* r07 canonical 1M replay 通过；
  -全局 flock、systemd scope、CPU/NUMA 与 phase-I/O accounting 均已验证。

当前不再要求提交第三轮纯基础设施审查。

完成第 2 节的最后修订，并通过第 3 节的自动门禁后，可以直接执行正式 W1-C。

---

# 2. 正式执行前的最后修订

## 2.1 修正 DGAI ingestion 边界

当前 DGAI driver 的顺序为：

```text
ingest_begin
→ get_atlas_trace
→ insertion_kernel
→ deletion_kernel
→ ingest_end
```

必须改为：

```text
get_atlas_trace
→ ingest_begin
→ insertion_kernel
→ deletion_kernel
→ ingest_end
```

统一定义：

```text
ingestion time =
全部原生 insert/delete API 执行时间
```

该区间不包含：

* trace 文件解析；
  -插入向量从 full corpus 读取；
  -index clone；
  -index load；
  -merge/save；
  -query/probe。

OdinANN 保持相同口径。

DGAI driver 修改后：

1. 更新 driver patch SHA256；
   2.执行两次 clean canonical build；
   3.两次 DGAI `w1_canary` 必须 byte-identical；
   4.更新 frozen binary SHA256；
   5.重新运行 artifact verification。

该修改只改变 marker 位置，不改变更新算法。

---

## 2.2 增加 pre-update Recall 门禁

formal 模式在 private clone 上执行三次 pre-update query 后，必须先汇总 median Recall，门禁通过后才允许进入 update。

固定要求：

| 系统      |   L | 合法 median Recall@10 |
| ------- | --: | ------------------: |
| DGAI    |  64 |    `[0.950, 0.955]` |
| DGAI    | 128 |    `[0.980, 0.985]` |
| OdinANN |  29 |    `[0.950, 0.955]` |
| OdinANN |  46 |    `[0.980, 0.985]` |

同时要求：

* 三次运行全部 valid；
* binary/index/query/GT identity 一致；
  -无 fatal、I/O error 或 OOM；
  -设备读取非零；
  -返回 tag 均属于 checkpoint-0 active set。

任何一个配置未通过：

```text
停止该系统
→ 不执行 update
→ 保留 clone 和查询证据
→ 不执行后续系统
```

不得扩大区间或更换 L。

---

## 2.3 执行时重新运行 preflight

历史 `formal_preflight.json` 只证明先前时刻的状态。

正式执行取得 global flock 后、写入任何 CP01 文件前，必须重新运行只读检查，输出：

```text
results/pilot3_sift10m_w1/preflight/execution_preflight.json
```

重新验证：

* canonical binary SHA256；
* OdinANN io_uring identity；
  -两个 F0 base 的完整 manifest SHA256；
  -full corpus/query/CP00 active tags/CP00 GT/source trace SHA256；
  -compute-groundtruth binary SHA256；
  -NVMe major:minor；
  -至少 150 GB 可用空间；
  -systemd/NUMA/cgroup runtime；
* CP01 目录不存在；
* checkpoint-1 GT 目录不存在；
  -DGAI/OdinANN formal attempt 不存在；
  -DiskANN stale-control 结果不存在；
  -没有已有 W1 session、scope 或进程。

执行 preflight 和正式工作必须持有同一个 flock，中间不能释放。

---

## 2.4 完善 DiskANN stale-static control

DiskANN stale control 继续使用 checkpoint-0 immutable index 和 checkpoint-1 GT，参数：

```text
L = 29, 53
Tq = 1
每点三次
```

必须在独立 systemd scope 中运行：

```text
AllowedCPUs=0-23
numactl --physcpubind=0-23 --membind=0
CPU/Memory/IO accounting enabled
```

冻结并验证：

* DiskANN query binary SHA256；
* checkpoint-0 index manifest；
  -query SHA256；
  -checkpoint-1 GT SHA256。

每次运行要求：

* exit code 0；
  -Recall 可解析且有限；
  -无 fatal/assertion/I/O error/OOM；
  -真实 NVMe read bytes 大于 0；
  -result shape 正确。

由于它是 stale negative control：

-允许结果中出现 checkpoint-1 已删除 tag；
-不得要求结果全部属于 checkpoint-1 active set；
-必须明确标记为 `stale-static negative control`；
-不得与动态系统的 update throughput 放在同一排名中。

---

## 2.5 Preparation 与 GT 资源隔离

CP01 materialization 和 exact GT 也放入独立 scope。

推荐：

```text
CPU = 0-55
memory policy = interleave 0,1
CPU/Memory/IO accounting enabled
```

它们属于实验准备开销，不与 DGAI/OdinANN update cost 比较。

分别保存：

```text
cp01_preparation_resources.json
gt_cp01_resources.json
```

记录 wall time、peak RSS、cgroup memory peak、memory.events 和 NVMe I/O。

---

# 3. 最后自动门禁

完成第 2 节修改后，执行：

```text
canonical DGAI rebuild
→ artifact verification
→ 1M/16-op formal-path replay
```

replay 必须使用：

-更新后的 DGAI marker；

* canonical DGAI/OdinANN-uring binaries；
  -新的 pre-update Recall gate；
* shared formal runner；
* global flock；
  -完整 pre/update/post 流程。

要求：

* DGAI/OdinANN pre-update gate 通过；
  -两套状态机正确；
  -live/fresh probes 全部通过；
  -active set exact match；
  -base integrity 通过；
  -phase I/O 可解析；
  -无 OOM；
  -成功标记完整。

该 replay 通过后，可以在同一次已授权流程中直接启动正式 W1-C，无需再次等待 Gpt。

---

# 4. 正式执行顺序

唯一允许的顺序：

```text
acquire global flock
→ fresh execution preflight
→ CP01 trace preparation
→ CP01 trace validation
→ CP01 active-vector materialization
→ checkpoint-1 exact GT
→ GT validation
→ DGAI pre-update query gate
→ DGAI 80K update canary
→ DGAI fresh-state correctness
→ DGAI post-update queries
→ DGAI final validation
→ OdinANN pre-update query gate
→ OdinANN 80K update canary
→ OdinANN live/fresh correctness
→ OdinANN post-update queries
→ OdinANN final validation
→ DiskANN stale-static control
→ final report
→ stop
```

任一阶段失败：

* 立即停止；
  -不执行后续阶段；
  -保留全部 attempt；
  -不自动重试；
  -不删除失败产物；
  -不改变参数；
  -不续写失败 clone。

---

# 5. 正式更新配置

## 5.1 Trace

```text
80,000 unique deletes
80,000 unique inserts
seed = 20260713
final active cardinality = 8,000,000
```

必须使用已审查的 deterministic trace 和九个 probe positions。

## 5.2 Query policy

更新前使用 checkpoint-0 GT，更新后使用 checkpoint-1 GT。

固定参数：

| 系统            | 0.95 policy | 0.98 policy |
| ------------- | ----------: | ----------: |
| DGAI          |        L=64 |       L=128 |
| OdinANN       |        L=29 |        L=46 |
| DiskANN stale |        L=29 |        L=53 |

动态系统 post-update：

```text
Tq = 1
完整 10K queries
每个 L 三次
```

不进行 checkpoint-1 Recall refinement。

---

# 6. 正式结果必须包含

## 6.1 Correctness

* trace manifest；
  -checkpoint-1 active-set hash；
  -checkpoint-1 GT validation；
* DGAI persisted active-tag exact audit；
* OdinANN persisted active-tag exact audit；
* DGAI fresh probes 18/18；
* OdinANN live probes 18/18；
* OdinANN fresh probes 18/18；
* immutable base 前后 manifest。

## 6.2 Update/visibility

分别报告：

```text
ingestion throughput
online-visible throughput
restart-visible throughput
```

DGAI：

```text
online visibility = unsupported
```

OdinANN：

```text
online visibility = live instance probe verified
```

不能把 DGAI restart-visible 与 OdinANN online-visible 直接放入同一排名。

## 6.3 I/O 与空间

* ingest phase read/write bytes；
  -online probe phase；
  -publish phase；
  -fresh probe phase；
  -end-to-end read/write bytes；
  -payload-normalized device writes；
  -persistent index growth；
  -temporary space peak；
  -final apparent/allocated bytes。

## 6.4 Query stability

对每个系统和 L 报告：

* pre/post actual Recall；
  -QPS；
  -P50/P95/P99；
  -mean I/O；
  -NVMe reads；
  -serving memory；
  -三次 raw values；
  -median/min/max；
  -相对 W0 的变化。

这些是 fixed-policy churn stability 数据，不能称为 checkpoint-1 matched-Recall frontier。

---

# 7. 通知

至少发送：

* formal W1 开始；
* CP01 preparation 完成或失败；
  -GT 完成或失败；
  -DGAI 开始/完成/失败；
  -OdinANN 开始/完成/失败；
  -DiskANN stale control 完成/失败；
  -全局完成或停止原因。

通知失败不改变实验结果，但必须记录。

---

# 8. 输出

正式报告：

```text
codex/share/2026-07-15/dynamic_vamana_w1_one_percent_canary_results_0715.md
```

机器可读目录：

```text
results/pilot3_sift10m_w1/
├── execution_manifest.json
├── preflight/
├── preparation/
├── DGAI/cp01-01/
├── OdinANN/cp01-01/
├── DiskANN/stale-cp00-01/
├── summary.tsv
└── raw/
```

---

# 9. 完成后停止

正式 W1-C 完成后停止，不自动运行：

* 5% replacement；
  -10% replacement；
  -20% replacement；
  -DiskANN rebuild；
  -query/update mixed workload；
  -checkpoint-1 matched-Recall refinement；
  -DEEP/GIST；
  -W2；
  -任何系统机制修改。

下一轮根据 1% canary 决定是否进入完整 W1 trajectory。

---

# 10. 最终裁决

formal execution preflight 与 canonical io_uring replay 已通过。

完成第 2 节的小范围修订并通过自动 replay 后，**正式授权执行 SIFT10M checkpoint-1 preparation 与两个串行 80K canary**。

不需要额外的中间人工审批。
