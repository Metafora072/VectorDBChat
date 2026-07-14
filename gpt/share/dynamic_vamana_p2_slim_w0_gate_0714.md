# 三系统 SIFT10M Pilot：P2 Slim W0 执行门禁

**日期**：2026-07-14
**上游结果**：`codex/share/dynamic_vamana_three_system_p1_results_0714.md`
**裁决**：**P1 PASS；修复两个测量问题后进入 calibration-first Slim W0**

---

## 1. P1 验收

P1 已达到 readiness 目标：

* 官方 BIGANN SIFT10M provenance 完整；
* checkpoint-0 包含统一的 8M active vectors；
* 10,000 queries 的 exact top-100 GT 已验证；
* DiskANN、DGAI、OdinANN 均已完成可查询索引；
* 三系统 serving query 均使用 CPU 0–23、NUMA node 0；
* 查询阶段均产生真实 SSD I/O；
* 没有启动 W1、churn、DEEP/GIST 或 Fresh-Ref。

DGAI 的构建情况单独记录为：

```text
single-NUMA build: OOM
build-only interleave 0,1: success
peak build RSS: 132.3 GiB
```

该 exception 不阻塞 W0 serving 比较，但本轮不比较三系统 build cost。

---

# 2. P2 前置修复

## 2.1 修复 `memory.events`

当前 `resource_probe.py` 的键值解析器只接受 `key:value`，而 cgroup v2 的 `memory.events` 使用：

```text
key value
```

Codex 应修改解析器，使其同时接受两种格式。

随后运行数秒级 canary，验证 JSON 中至少存在：

```text
low
high
max
oom
oom_kill
```

canary 必须将：

```text
直接读取的 memory.events
```

与：

```text
resource_probe JSON 中的 memory.events
```

逐字段比较，值应完全一致。

该修复只涉及测量代码，不需要重新运行 P1 或重建索引。

---

## 2.2 拆分查询时间口径

F0 表格中的 process wall time 与 driver-reported QPS 显然不属于同一计时区间。例如 10,000 queries 与报告的 wall time无法直接推导出表中 QPS。

这不一定意味着结果错误，可能是：

* wall time 包含 index loading；
* driver QPS 只覆盖 timed search；
  -存在 warm-up；
* driver 扫描了多个内部配置；
  -部分时间被排除。

P2 必须明确记录：

```text
process_wall_seconds
index_load_seconds
warmup_seconds
timed_search_seconds
query_count
driver_reported_qps
externally_computed_qps
```

其中：

```text
externally_computed_qps =
query_count / timed_search_seconds
```

若 driver-reported QPS 与外部计算值不同，报告必须解释其计时边界，不能把不同区间的 wall time 与 QPS 放在同一单元格中。

---

# 3. 为什么不能直接比较 F0 单点

当前 F0：

```text
DiskANN Recall@10 = 0.9688
DGAI    Recall@10 = 0.9216
OdinANN Recall@10 = 0.9738
```

同时三套索引还存在不同的：

* graph degree；
* build L；
* PQ 组织；
* query beam；
* pipeline width；
* search mode。

因此当前 QPS、latency 和 mean I/O 只能证明三套 artifact 能运行，不能证明任何系统占优。

P2 的第一目标是建立各系统自己的：

```text
Recall–QPS
Recall–latency
Recall–I/O
```

曲线，并找到实际共同可达的 Recall 区间。

---

# 4. P2-A：Recall Calibration

## 4.1 固定条件

使用现有 immutable checkpoint-0 索引，不重新构建。

固定：

```text
dataset = SIFT10M checkpoint 0
queries = 固定的前 2,000 条 official queries
Tq = 1
CPU = 0-23
memory = membind node 0
K = 10
metric = squared L2
```

三系统使用完全相同的 2,000 query IDs。

每个 calibration invocation 使用新进程，并记录 load、warm-up 与 timed search。

---

## 4.2 调整对象

每个系统只调整其主要搜索广度参数，例如：

* DiskANN：search list size `L`；
* DGAI：原生 driver 中控制候选搜索广度的 `L`；
* OdinANN：原生 driver 中控制候选搜索广度的 `L`。

其余参数先保持 F0 值不变：

* beam/pipeline；
* search mode；
* rerank strategy；
* cache configuration；
* index files。

不要同时改变多个参数，否则无法知道 Recall 变化来自哪里。

---

## 4.3 初始扫描

建议初始候选集：

```text
20, 40, 80, 120, 160, 240, 320
```

该数字表示各 driver 的原生 search-list 参数；若某个 driver 的参数语义不同，Codex 必须先在报告中说明，不得机械套用。

保存所有实际点，不只保存最佳点。

---

## 4.4 共同 Recall 目标

候选 matched-Recall 目标预先定义为：

```text
0.93
0.95
0.97
0.98
0.99
```

只保留被三个系统实际曲线共同覆盖的目标。

“覆盖”表示存在实际测得的上下邻近点，不依据单点外推。

对于共同可达目标：

* 可以继续尝试中间 L；
  -目标容差为 ±0.005；
  -不能通过曲线插值伪造测量点；
  -若没有参数落入容差，则报告最近的上下界点。

如果 calibration 后少于两个候选 Recall 目标被三系统共同覆盖，则停止在 P2-A，提交结果并重新审查 build/index 配置，不进入吞吐排名。

特别是，如果 DGAI 即使增大搜索广度仍无法进入共同 Recall 区间，需要先判断：

* 是 search 参数不足；
  -还是 R32 索引的质量上限；
  -还是 query pipeline 的配置问题。

本轮不得直接把它描述成 DGAI 架构缺陷。

---

# 5. P2-B：Slim W0

P2-A 找到至少两个共同 Recall 目标后，进入 P2-B。

## 5.1 Query concurrency

运行：

```text
Tq = 1
Tq = 16
```

暂不运行 Tq=8/32。

Tq=1 用于观察单查询路径效率；Tq=16 用于观察中等并发吞吐。

---

## 5.2 测试点

每个系统运行：

1. 所有共同 matched-Recall 点；
2. 一个低开销端点；
3. 一个该索引可达的高 Recall 端点。

完整保留 Recall curve，不能只输出 matched 点。

---

## 5.3 重复

每个正式点运行三次。

每次：

* 新进程；
  -同一 CPU/NUMA policy；
  -固定 warm-up query 集；
  -相同 timed query 集；
  -单独 dedicated cgroup；
  -保存单次原始值。

不得只报告三次平均值。

报告：

```text
median
minimum
maximum
all three raw runs
```

当前单轮 query 只有数秒，三次重复不会构成主要实验成本。

---

# 6. Cache 与进程生命周期

每个 system/concurrency/repeat：

1. 确认上一进程退出；
2. 清理 OS page cache；
3. 创建新的 dedicated cgroup；
4. 加载索引所需内存结构；
5. 执行固定 warm-up；
6. 开始 timed search；
7. 保存完整日志和资源采样；
8. 正常销毁 scope。

由于系统使用 O_DIRECT，`drop_caches` 不能描述为清空 SSD 或设备内部缓存，只用于控制 metadata、辅助文件和 mmap/page-cache 状态。

L 点可以在同一进程内扫描的前提是：

* driver 原生支持多 L sweep；
  -每个 L 有独立 timed interval；
  -顺序固定并记录；
  -不会复用上一个 L 的结果状态。

否则每个 L 使用独立进程。

---

# 7. P2 指标

每个点至少记录：

```text
system
artifact commit
index identity
validation level
query threads
search parameters
query count
Recall@10
QPS
P50
P95
P99
mean latency
mean I/O
device read bytes
device read IOPS
device bandwidth
CPU utilization
steady RSS
peak RSS
cgroup memory.current
cgroup memory.peak
cgroup memory.events
process wall
load time
warmup time
timed search time
exit status
```

DiskANN 保留逐 ID validation。

DGAI/OdinANN 继续标记：

```text
aggregate-only validation
```

P2 是 checkpoint-0 的纯查询实验，因此暂不要求修改两个 artifact 输出逐 query IDs。

---

# 8. 结果解释边界

P2 允许回答：

* 三个现有索引的 Recall–query-performance 曲线；
* matched Recall 下的 QPS、latency 与 I/O；
  -单线程与 16 线程的伸缩差异；
* serving DRAM 和 SSD 空间；
* DGAI 是否能通过搜索参数达到更高 Recall。

P2 不能回答：

* update throughput；
* visibility cost；
* churn 稳定性；
* DGAI/OdinANN 的机制因果关系；
  -完整动态 Pareto frontier；
  -哪个架构普遍更优；
  -论文 Idea。

DGAI 的 132.3 GiB build peak 应保留为 artifact readiness 发现，但不能混入 W0 serving Pareto 图。

---

# 9. 输出

Codex 输出：

```text
codex/share/dynamic_vamana_p2_slim_w0_results_0714.md
```

机器可读结果：

```text
results/pilot3_sift10m_p2/
├── calibration.tsv
├── matched_recall.tsv
├── raw_runs.tsv
├── timing_scope.tsv
├── resource_summary.tsv
└── raw/
```

报告中至少生成：

1. Recall–QPS；
2. Recall–P99；
3. Recall–mean I/O；
4. matched Recall QPS；
5. matched Recall P99；
6. serving DRAM；
7. timing-scope reconciliation 表。

---

# 10. 执行顺序

当前授权顺序：

```text
修复 memory.events
→ resource canary
→ P2-A calibration
→ 检查共同 Recall 区间
→ 若满足条件，执行 P2-B Slim W0
→ 汇总并停止
```

邮件通知覆盖：

* canary 成功/失败；
  -每个系统 calibration 完成；
  -共同 Recall 区间；
  -每个 concurrency 完成；
  -P2 完成或停止原因；
  -预计剩余时间。

---

# 11. 停止条件

P2 完成后停止，不自动运行：

* 1% churn canary；
* 20% churn；
* DiskANN rebuild；
* W2 mixed；
* DEEP10M；
* GIST1M；
* Fresh-Ref；
  -系统机制修改。

下一轮根据 matched-Recall 曲线决定：

* 是否进入 W1；
  -是否需要重建某个索引；
  -是否先做 query-path 归因；
  -是否扩展到其他数据集。

---

# 12. 最终裁决

P1 通过，Pilot 继续。

但 P2 必须从 Recall calibration 开始，不能把 F0 单点转化为性能排名。

完成 `memory.events` 修复和计时口径拆分后，Codex 可以直接执行 P2-A；共同 Recall 区间满足条件时继续 P2-B，无需再次等待中间授权。
