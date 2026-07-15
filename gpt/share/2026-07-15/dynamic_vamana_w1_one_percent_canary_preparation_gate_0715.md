# Dynamic Vamana：W1 1% Replace-New Canary 准备门禁

**日期**：2026-07-15
**上游结果**：`codex/share/2026-07-15/dynamic_vamana_p2b_matched_recall_w0_results_0715.md`
**裁决**：**W0 PASS；仅授权准备和审查 W1 1% canary，暂不运行更新实验**

---

# 1. W0 验收结论

P2-M/P2-B 已满足静态查询基线要求：

* 五个 Recall floor 均有三个系统的严格 matched point；
* 最终参数均为达到 Recall floor 的最小实测整数 L；
* Tq=1 和 Tq=16 均完成有效重复；
* 所有 median Recall 均位于 `[R,R+0.005]`；
* 所有运行均无 I/O error、EBADF、负 CQE、OOM 或零设备读取；
* binary、index、query、GT 和 compatibility patch identity 已冻结；
* 实验已按门禁停止，没有进入 W1。

当前 W0 已足以作为动态实验的 checkpoint-0 query baseline。

本轮不继续进行更多 query-only tuning，也不立即做 query-path 机制归因。机制归因应在观察到更新后的 `Vq–Vm` tradeoff 后再决定，否则可能只解释一个与动态主问题无关的静态差异。

---

# 2. 下一阶段目标

下一阶段称为：

```text
W1-C：1% replace-new correctness and visibility canary
```

其目标不是形成论文性能结论，而是证明以下实验链路成立：

```text
确定性 replace-new trace
→ 动态索引正确应用 80K replacements
→ 查询可见性边界可测
→ published/restart 状态可验证
→ checkpoint-1 exact GT 正确
→ 更新后的 query 能使用统一口径运行
→ 更新时间和设备写入可可靠采集
```

只有 canary 通过，才讨论 5%/10%/20% trajectory。

---

# 3. Canary 范围

## 3.1 数据规模

初始 active set：

```text
8,000,000 vectors
```

1% replacement：

```text
80,000 unique deletes
80,000 unique inserts
```

最终 active cardinality仍为：

```text
8,000,000
```

## 3.2 系统范围

动态更新主体：

* DGAI；
* OdinANN。

DiskANN 本轮不执行 checkpoint-1 rebuild。

可以使用 checkpoint-0 DiskANN index 对 checkpoint-1 GT 做一次明确标记的：

```text
stale-static negative control
```

但该点：

* 不属于动态系统性能比较；
* 不具有 update throughput；
* 允许返回已删除 tag；
* 只用于确认不维护索引时的状态偏差。

完整 W1 中的 DiskANN rebuild 仍按既定计划在 checkpoint 20% 执行。

---

# 4. Trace 生成与审计

## 4.1 Trace 规则

使用既有 seed：

```text
20260713
```

生成确定性 trace：

* delete tag 均来自 checkpoint-0 active set；
* insert tag 均来自预留 insert pool；
* delete tag 内部无重复；
* insert tag 内部无重复；
* delete 与 insert 集合不相交；
* insert tag 在 checkpoint 0 中不存在；
* trace 顺序固定；
  -不复制或重采样已有向量。

保存：

```text
replace_cp01_80k.bin
replace_cp01_80k.tsv
replace_cp01_manifest.json
```

manifest 至少包含：

```text
seed
operation_count
delete_count
insert_count
delete_tag_sha256
insert_tag_sha256
binary_trace_sha256
initial_active_set_sha256
expected_cp01_active_set_sha256
```

## 4.2 Expected state

生成 checkpoint-1 expected active tags：

```text
active_cp01 =
(active_cp00 - delete_tags)
∪ insert_tags
```

严格验证：

```text
|active_cp01| = 8,000,000
```

不得仅依靠 driver 报告的 update count 判断更新成功。

---

# 5. Immutable base 与运行隔离

DGAI 和 OdinANN 分别从经过 W0 验证的 checkpoint-0 immutable index 创建独立 canary clone。

要求：

* clone 前保存完整文件清单、大小和 SHA256；
  -优先使用 reflink，若不支持则普通复制；
* clone、更新结果和临时文件全部位于实验 NVMe；
  -两个系统不得共享可写 index 文件；
  -更新完成后重新校验 checkpoint-0 base 的全部 hash；
  -base 发生任何变化即判定 canary 失败。

不得：

-直接更新 W0/F0 base；
-复用此前 dynamic smoke 的已写 index；
-在失败 attempt 上续写；
-覆盖旧 attempt；
-让 DGAI 与 OdinANN 并行更新同一设备。

---

# 6. 更新阶段的计时语义

每套 artifact 必须输出明确的 monotonic timestamp marker，不得依赖从普通日志文本猜测阶段边界。

统一 marker：

```text
clone_ready
index_loaded
ingest_begin
ingest_end
online_visibility_probe_begin
online_visibility_verified
publish_begin
publish_end
fresh_process_probe_begin
fresh_process_visibility_verified
```

## 6.1 Ingestion throughput

定义：

```text
ingestion throughput =
80,000 / (ingest_end - ingest_begin)
```

`ingest_end` 表示全部 delete/insert API 调用已经完成返回。

该区间不包含：

* base clone；
  -index load；
  -GT 计算；
  -merge；
  -consolidation；
  -reload；
  -fresh-process verification。

## 6.2 Online-visible throughput

定义：

```text
online-visible throughput =
80,000 / (online_visibility_verified - ingest_begin)
```

表示当前活跃 index instance 已能通过 checkpoint-1 query/probe 观察更新。

若某 artifact 不支持 merge 前在线可见：

```text
online_visibility_supported = false
```

不得伪造该指标。

## 6.3 Published/restart-visible throughput

定义：

```text
restart-visible throughput =
80,000 / (fresh_process_visibility_verified - ingest_begin)
```

其终点要求：

-必要的 merge/consolidation/publish 已完成；
-关闭 updater；
-启动全新的查询进程；
-新进程加载 index；
-checkpoint-1 状态验证通过。

## 6.4 系统语义

DGAI：

-记录原生更新完成时间；
-明确 merge、reload 和 publish 的真实边界；
-若只有 publish 后才可查询，则 online-visible 标记为不支持；
-primary visible throughput 包含其必要的 merge/reload/publish。

OdinANN：

-记录 live instance 中 insert/delete 完成后的在线可见时间；
-在 consolidation 前执行在线 probe；
-另行完成 publish/restart 验证；
-不能用在线可见时间冒充 restart-visible 时间。

报告必须并列给出两种 visibility，不能把 DGAI 的 restart-visible 与 OdinANN 的 online-visible 放在同一列后直接排名。

---

# 7. 更新正确性验证

## 7.1 全量 active-tag audit

为两个动态 artifact 增加只读 introspection 工具或使用已有安全接口，导出当前有效 tag 集合。

输出至少包括：

```text
active_tag_count
sorted_active_tag_sha256
minimum_tag
maximum_tag
duplicate_count
```

其结果必须精确等于 expected checkpoint-1 active set：

```text
actual active tags == expected active_cp01
```

这项验证覆盖全部 80,000 replacements，不能只验证 driver 返回的成功计数。

若现有 artifact 无法安全枚举 active tags，Codex 应先报告接口边界，不得为了跑通而读取未经确认的内部内存布局。

## 7.2 Query visibility probes

另外生成确定性的 probe query 集：

-从 trace 的开始、结束及等距位置选择 insert/delete pairs；
-选择规则完全由 trace index 决定，不依据查询结果；
-所有 probe 均必须通过，不使用百分比阈值。

Insert probe：

```text
query = inserted vector
expected inserted tag must be returned
```

Delete probe：

```text
deleted tag must not appear in returned top-k IDs
```

probe driver 必须输出实际 result IDs。

DGAI/OdinANN 现有 aggregate-only query 输出不足以承担该验证；允许新增一个最小、只读的 probe result-output 工具，但：

-不得改变 graph traversal；
-不得改变 candidate selection；
-不得改变 distance/rerank；
-只增加 result-ID serialization；
-补丁和 binary hash 必须单独冻结并审查。

---

# 8. Checkpoint-1 exact GT

根据 expected `active_cp01` 计算：

```text
10,000 queries × exact top-100
```

保存为独立 checkpoint-1 truthset。

验证：

* GT tag 全部属于 active_cp01；
  -不存在已删除 tag；
  -distance finite；
  -每行单调非降；
  -query 0、17、9999 做独立 brute-force audit；
  -ID 与距离均与独立结果一致；
  -GT、active-tag set、query 和 trace SHA256 全部写入 manifest。

不能使用 checkpoint-0 GT 评估更新后的 Recall。

---

# 9. 更新前后查询检查

Canary 只检查两个 Recall floor：

```text
0.95
0.98
```

使用 W0 在 checkpoint 0 选出的固定参数：

| 系统                    | R=0.95 | R=0.98 |
| --------------------- | -----: | -----: |
| DGAI                  |   L=64 |  L=128 |
| OdinANN               |   L=29 |   L=46 |
| DiskANN stale control |   L=29 |   L=53 |

## 9.1 Pre-update

在 clone 尚未更新时，使用 checkpoint-0 GT 复现对应 W0 Recall。

## 9.2 Post-update

达到相应 visibility 状态后，使用 checkpoint-1 GT：

* Tq=1；
  -每个固定 L 三次；
  -完整 10K queries；
  -保存 actual Recall、QPS、P99、mean I/O 和设备读取。

本轮保持 checkpoint-0 的固定 L，用于观察：

```text
same query policy under 1% churn
```

不在 canary 中重新做 matched-Recall refinement。

因此 canary 的 post-update QPS 不能作为最终 matched-Recall W1 结果。

---

# 10. 资源与写放大

每个动态系统至少记录：

```text
logical replacement count
logical inserted-vector payload bytes
ingestion wall time
online-visible wall time
publish/restart-visible wall time
device read bytes
device write bytes
read IOPS
write IOPS
peak RSS
cgroup memory peak
memory.events
index allocated bytes before/after
temporary allocated bytes peak
final persistent bytes
```

报告两个明确的写入比率：

```text
device_write_bytes / inserted_vector_payload_bytes
```

以及：

```text
persistent_index_growth / inserted_vector_payload_bytes
```

它们只是统一的 payload-normalized accounting，不能表述为包含所有数据库语义的理论 write amplification。

删除、日志、拓扑修复和元数据写入仍需单独列出可观测字节。

---

# 11. Source audit

在编写执行脚本前，Codex 必须分别审计 DGAI/OdinANN 的实际 update driver：

* trace 如何被读取；
  -delete 与 insert 的执行顺序；
  -是否逐条、批量或异步执行；
  -`ingest_end` 对应哪个 API 返回点；
  -何时 merge；
  -何时 consolidation；
  -何时持久化；
  -查询能否在更新进程内执行；
  -新进程何时可加载新状态；
  -driver 是否自动执行搜索或合并；
  -失败时是否可能仍返回 0。

不得为了统一语义而重写算法执行顺序。

如 artifact 原生语义无法匹配上述某个阶段，应标记为 unsupported/not observable，而不是添加模拟阶段。

---

# 12. 当前只授权准备

Codex 当前只准备：

```text
w1_prepare_cp01_trace.py
w1_validate_cp01_trace.py
w1_compute_cp01_gt.sh
w1_clone_base.sh
w1_dgai_1pct_canary.sh
w1_odin_1pct_canary.sh
w1_visibility_probe.*
w1_dump_active_tags.*
w1_collect_canary.py
start_w1_canary_tmux.sh
```

以及 source audit 报告：

```text
codex/share/2026-07-15/dynamic_vamana_w1_one_percent_canary_preparation_0715.md
```

报告必须包含：

1. DGAI 更新状态机；
2. OdinANN 更新状态机；
3. 每个 timestamp 的准确代码位置；
4. active-tag introspection 方案；
5. result-ID probe 方案；
6. trace/GT manifest schema；
7. clone 与 base-hash 保护；
8. cgroup/CPU/NUMA/设备采集方式；
9. ingestion、online-visible 和 restart-visible 的计算公式；
10. 预期运行时间与 NVMe 空间；
11. 修改的 artifact 文件及 patch SHA256；
12. 明确声明尚未运行 80K updates。

---

# 13. 当前禁止

在下一轮审查前，不允许：

-执行 80K update canary；
-启动 tmux；
-修改 checkpoint-0 base；
-执行 5%/10%/20% churn；
-执行 DiskANN rebuild；
-并发 query-update workload；
-调整 R、build L、PQ chunks 或其他算法参数；
-根据 W0 结果修改某个系统以追赶性能；
-做机制优劣或论文 Idea 结论。

---

# 14. 后续门禁

准备报告通过后，下一轮只放行：

```text
trace/GT preparation
→ DGAI 1% canary
→ OdinANN 1% canary
→ DiskANN stale control
→ 汇总并停止
```

1% canary 通过后，再决定是否执行：

```text
5% → 10% → 20% trajectory
```

以及是否需要：

* checkpoint-specific matched-Recall refinement；
* DiskANN checkpoint-20 rebuild；
* query/update mixed workload；
* query-path 或 update-path 机制归因。
