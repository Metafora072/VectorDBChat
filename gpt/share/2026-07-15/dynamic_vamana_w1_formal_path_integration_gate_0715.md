# Dynamic Vamana W1-C：Formal Path 集成门禁

**日期**：2026-07-15
**上游报告**：`codex/share/2026-07-15/dynamic_vamana_w1_one_percent_canary_revision_0715.md`
**裁决**：**MICRO-CANARY PASS；FORMAL W1 HOLD**

---

# 1. Micro-canary 验收

1M/16-replacement micro-canary 可以作为基础设施正确性测试通过。

已经验证：

* DGAI 的 `online_visibility_unsupported → merge/reload → fresh process` 状态机；
* OdinANN 的 `live probe → save → fresh process` 状态机；
* inserted/deleted result-ID probes；
  -持久化 active-tag exact-set audit；
  -独立 private clone；
* immutable base 前后不变；
* dedicated cgroup；
* CPU 0–23 与 NUMA node 0；
  -无 OOM；
* marker schema；
  -分阶段 NVMe I/O accounting；
  -失败 attempt 不产生成功标记。

这些结果只证明 micro infrastructure 可行，不构成 SIFT10M W1 性能数据。

---

# 2. 为什么暂不放行正式 CP01

当前 micro 路径和 formal 路径不是同一套执行代码。

micro 路径调用：

```text
w1_canary run ...
w1_canary probe ...
```

正式 wrappers 仍调用旧式位置参数接口，并且没有完成完整的 pre-update、update、post-update 与 fresh-process query 流程。

因此，目前验证通过的是：

```text
w1_micro_canary.sh
→ w1_micro_worker.sh
```

尚未验证：

```text
formal orchestrator
→ CP01 preparation
→ w1_dgai_1pct_canary.sh
→ w1_odin_1pct_canary.sh
→ stale DiskANN control
→ final collector
```

不能把前者的通过自动外推给后者。

---

# 3. F1：共享完整 driver patch

必须把外部工作树中的实际修改导出到共享目录。

至少提交：

```text
patches/DGAI_w1_canary_driver.patch
patches/DGAI_w1_canary_cmake.patch
patches/OdinANN_w1_canary_driver.patch
patches/OdinANN_w1_canary_cmake.patch
patches/DGAI_w1_result_ids.patch
patches/OdinANN_w1_result_ids.patch
```

每份 patch 必须：

* 基于已冻结 upstream commit；
  -包含完整 source diff；
  -通过 `git apply --check`；
  -记录 SHA256；
  -记录允许修改的文件；
  -明确 compatibility patch 应用顺序；
  -能从干净 checkout 重建出报告中的 binary hash。

另提交：

```text
artifact_rebuild_manifest.json
```

包含：

```text
upstream commit
patch application order
patch SHA256
compiler version
cmake arguments
linked libraries
source file SHA256
binary SHA256
ldd output
```

仅提供外部工作树中的 source hash 不足以构成可复现实验 artifact。

---

# 4. F2：统一 micro 与 formal 代码路径

不再维护独立的 micro worker 逻辑和 formal wrapper 逻辑。

建议将共同逻辑下沉为：

```text
w1_run_system_canary.sh
```

参数至少包括：

```text
--system
--dataset
--replacement-count
--base-index
--trace
--expected-active-tags
--probe-queries
--probe-spec
--cp0-gt
--cp1-gt
--run-name
--attempt
--mode micro|formal
```

micro 和 formal 只能在以下内容上不同：

* dataset；
  -replacement count；
  -index path；
  -trace/GT path；
  -output directory；
  -resource budget。

两者必须共同使用：

* 同一专用 driver；
  -同一 clone helper；
  -同一 marker schema；
  -同一 result-ID validator；
  -同一 active-tag audit；
  -同一 base-integrity check；
  -同一 phase-I/O collector；
  -同一 fail-closed orchestration。

删除或降级 `w1_micro_worker.sh` 中与 formal path 重复的独立状态机。

---

# 5. F3：完成正式 DGAI/OdinANN wrappers

每个正式 system wrapper 必须实现以下完整阶段。

## 5.1 Artifact 与环境门禁

检查：

```text
free space >= 150 GB
root/base/attempt 位于 NVMe 259:10
binary SHA256 匹配 frozen manifest
patch SHA256 匹配
trace validation valid
CP01 GT validation valid
base immutable manifest valid
无已有 attempt
无已有 W1 scope/session
全局 lock 已持有
```

运行环境：

```text
systemd-run --scope
AllowedCPUs=0-23
numactl --physcpubind=0-23 --membind=0
CPUAccounting=yes
MemoryAccounting=yes
IOAccounting=yes
```

## 5.2 Clone verification

clone helper 输出标准化 manifest：

```text
relative_path
size_bytes
sha256
```

要求：

```text
base manifest == clone-initial manifest
base-before == base-after-clone
base-before == base-after-entire-attempt
```

当前只比较 path/size 不足以证明 clone 内容一致。

## 5.3 Pre-update query

在 private clone 尚未更新时，使用 checkpoint-0 GT 运行：

```text
DGAI: L=64,128
OdinANN: L=29,46
Tq=1
完整 10K queries
```

每点至少一次。

要求 Recall 与 W0 对应结果处于既有重复分布内。该阶段验证：

* clone 可正常加载；
  -专用 query binary 未改变搜索语义；
  -更新前 artifact identity 正确。

## 5.4 Update/visibility

DGAI：

```text
load
→ ingest_begin
→ 80K insert/delete API completion
→ ingest_end
→ online_visibility_unsupported
→ publish_begin
→ final_merge/reload
→ publish_end
```

OdinANN：

```text
load
→ ingest_begin
→ 80K insert/delete API completion
→ ingest_end
→ online probe
→ online_visibility_verified
→ publish_begin
→ save
→ publish_end
```

所有 result 文件路径必须通过显式环境变量或 CLI 参数传入，不得由 driver 隐式猜测。

## 5.5 Fresh-process correctness

关闭 updater 后启动全新进程：

```text
fresh_process_probe_begin
→ load published index
→ 18-query result-ID probe
→ fresh_process_visibility_verified
```

随后执行：

* persisted active-tag exact-set audit；
  -所有返回 tag 属于 CP01 active set；
  -insert targets 返回；
  -deleted targets 不返回。

## 5.6 Post-update query

使用 checkpoint-1 exact GT：

```text
DGAI: L=64,128
OdinANN: L=29,46
Tq=1
完整 10K queries
每点三次
```

每次独立 query process。

保存：

```text
actual Recall@10
QPS
P50/P95/P99
mean latency
mean I/O
NVMe reads
process/cgroup memory
binary/index/query/GT identity
```

这些是 fixed-W0-policy churn stability 点，不是 checkpoint-1 matched-Recall 排名。

## 5.7 Finalization

完成：

* immutable base 最终 hash 复核；
  -attempt manifest；
  -final apparent/allocated bytes；
  -complete marker；
  -邮件通知；
  -明确退出全部 query/update 进程。

只有全部阶段通过才写：

```text
FORMAL_W1_CANARY_OK
```

---

# 6. F4：单一串行 orchestrator

替换当前可分别启动两个 system session 的 launcher。

新增：

```text
run_w1_cp01_formal.sh
start_w1_cp01_formal_tmux.sh
```

唯一顺序：

```text
acquire global flock
→ validate frozen artifacts
→ prepare/validate CP01
→ compute/validate CP01 GT
→ DGAI formal canary
→ validate DGAI completely
→ OdinANN formal canary
→ validate OdinANN completely
→ DiskANN stale-static control
→ final report
→ release lock
```

任何阶段失败：

* 停止；
  -保留 attempt；
  -不执行后续系统；
  -不自动重试；
  -不改变参数。

---

# 7. F5：修复 phase-I/O 边界采样

当前“选择离 marker 最近的 sample”不能作为正式阶段 accounting。

对于阶段 `[begin, end]`，使用：

```text
left  = timestamp <= begin 的最后一个 sample
right = timestamp >= end 的第一个 sample
```

并记录：

```text
left_sample_ns
begin_marker_ns
end_marker_ns
right_sample_ns
left_skew_ns
right_skew_ns
sampling_interval_ms
```

要求：

* left 与 right 必须存在；
  -right timestamp > left timestamp；
  -I/O counters 不得下降；
  -不能让 begin/end 映射到同一 sample；
  -skew 不超过两个采样周期；
  -阶段太短无法可靠测量时标记 `not_resolvable_at_sampling_interval`，不得输出伪精确 delta。

正式更新建议使用不高于 25 ms 的采样周期。

---

# 8. F6：修复 GT manifest 的路径身份

`gt_cp01_manifest.json` 中 query hash 不得使用写死的默认根路径。

应直接对传给 ground-truth 工具的实际：

```text
query_file
```

计算 hash，并同时记录绝对 realpath。

manifest 至少包含：

```text
active_vector_realpath/SHA256
active_tag_realpath/SHA256
query_realpath/SHA256
truthset_realpath/SHA256
trace SHA256
truthset shape
distance metric
K
audit query IDs
validator report SHA256
```

---

# 9. Formal-path replay

完成 F1–F6 后，不立即生成 SIFT10M CP01。

先使用 1M/16-replacement 输入，通过**正式 orchestrator 和正式 wrappers**重放一次：

```text
mode=micro
```

该重放必须覆盖：

* pre-update query；
  -DGAI full formal state machine；
  -OdinANN full formal state machine；
  -post-update query；
  -global serial lock；
  -final base check；
  -final summary；
  -formal success marker。

成功后证明：

```text
测试过的代码路径 == 即将在 SIFT10M 上运行的代码路径
```

旧 micro attempts 保留，但不能代替 formal-path replay。

---

# 10. 当前授权

当前只授权：

```text
导出完整可重建 patch
→ 统一 micro/formal 执行路径
→ 完成正式 wrappers
→ 完成单一串行 orchestrator
→ 修复 phase-I/O 和 GT manifest
→ 运行 1M/16-op formal-path replay
→ 停止并提交审查
```

仍不授权：

-正式 80K CP01 trace；
-SIFT10M CP01 vector materialization；
-10K×8M exact GT；
-SIFT10M index clone；
-80K DGAI/OdinANN update；
-DiskANN stale control；
-5%/10%/20% churn；
-W2/DEEP/GIST。

---

# 11. 输出

提交：

```text
codex/share/2026-07-15/dynamic_vamana_w1_formal_path_integration_0715.md
```

报告必须包含：

1. 可重建 driver/result-ID/CMake patches；
2. clean-checkout rebuild 结果；
3. binary hash reproduction；
4. unified wrapper/orchestrator diff；
5. formal-path 1M replay timeline；
6. pre/post-query 结果；
7. DGAI/OdinANN correctness；
8. phase-I/O boundary/skew；
9. global serialization；
10. final base integrity；
11. fail-injection；
    12.明确声明未执行 SIFT10M CP01/80K。

---

# 12. 最终裁决

micro-canary 的 artifact 状态机验证通过。

但正式执行代码尚未与已验证 micro 路径统一，且共享包缺少可重建 driver source patch。

**当前裁决：MICRO PASS，FORMAL HOLD。**
