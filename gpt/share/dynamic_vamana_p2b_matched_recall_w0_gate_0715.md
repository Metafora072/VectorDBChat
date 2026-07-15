# Dynamic Vamana：P2-B Matched-Recall Slim W0 门禁

**日期**：2026-07-15
**上游结果**：`codex/share/dynamic_vamana_p2a_r1_repeatability_and_calibration_0715.md`
**裁决**：**P2-A-R1 PASS；允许实测 matched-Recall refinement，满足条件后进入 P2-B**

---

# 1. P2-A-R1 验收

当前结果满足进入下一阶段的条件：

* DiskANN、DGAI、OdinANN 的固定配置重复性门禁均通过；
* DGAI 的历史 F0 位于当前重复分布的 95% prediction interval；
* OdinANN 修复后的 10 次查询均无 EBADF、负 CQE、零 Recall 或异常短路径；
* 完整 10K query 与原始 checkpoint-0 GT 已统一使用；
* 69 个 calibration raw run 全部 valid；
* 23 个 system–L group 均具有三次重复和一致 artifact identity；
* 三条 median Recall 曲线均随 L 单调上升；
* `0.93/0.95/0.97/0.98/0.99` 均具有三系统共同 coarse bracket。

旧的错误 GT、Tq=1 F0 canary 和首轮无效 OdinANN 结果继续作为取证材料保留，不进入任何正式汇总。

---

# 2. Matched Recall 的定义

此前的 `target ± 0.005` 容差可能允许某个系统低于目标 Recall，从而以较低搜索成本获得性能优势。

P2-B 将目标定义为 Recall floor。

对于目标 `R`，某个系统的最终参数必须满足：

```text
R ≤ median Recall@10 ≤ R + 0.005
```

并选择满足该条件的：

```text
最小实测整数 L
```

这表示比较的是：

```text
达到同一 Recall 服务质量下界时的最低搜索广度
```

禁止：

* 使用低于目标的配置；
* 使用插值 Recall 作为最终点；
* 在多个满足条件的 L 中选择 QPS 最好但 L 更大的异常点；
* 根据性能结果反向挑选 L。

若某系统不存在落入该区间的整数 L，则该 Recall target 不构成严格 matched point。

---

# 3. P2-M：Matched-Point Refinement

## 3.1 固定条件

```text
dataset = SIFT10M checkpoint 0
queries = 完整 10,000 queries
GT = 原始 checkpoint-0 exact top-100
Tq = 1
K = 10
CPU = 0-23
NUMA = membind node 0
artifact identity = P2-A-R1 冻结版本
```

每个候选 L 运行三次。

所有搜索候选可以跨目标复用。例如，同一个实测 L 同时参与 `0.97` 和 `0.98` 的 bracket，但不能复制或修改其结果。

---

## 3.2 初始 bracket

### DiskANN

| Recall floor | lower L | upper L |
| ------------ | ------: | ------: |
| 0.93         |      20 |      24 |
| 0.95         |      24 |      32 |
| 0.97         |      40 |      60 |
| 0.98         |      40 |      60 |
| 0.99         |      60 |      80 |

### DGAI

| Recall floor | lower L | upper L |
| ------------ | ------: | ------: |
| 0.93         |      40 |      80 |
| 0.95         |      40 |      80 |
| 0.97         |      80 |     120 |
| 0.98         |     120 |     160 |
| 0.99         |     160 |     240 |

### OdinANN

| Recall floor | lower L | upper L |
| ------------ | ------: | ------: |
| 0.93         |      20 |      40 |
| 0.95         |      20 |      40 |
| 0.97         |      20 |      40 |
| 0.98         |      40 |      80 |
| 0.99         |      40 |      80 |

这里的 lower 点 Recall 低于目标，upper 点 Recall 高于目标。

---

## 3.3 第一轮 probe

可从线性估计附近开始，但这些数字只用于选择第一轮实测参数：

| Recall floor | DiskANN |    DGAI | OdinANN |
| ------------ | ------: | ------: | ------: |
| 0.93         |   21、22 |   48、49 |      27 |
| 0.95         |      29 |      68 |      33 |
| 0.97         |      42 |  99、100 |      39 |
| 0.98         |      55 | 129、130 |   52、53 |
| 0.99         |   79、80 | 209、210 |   72、73 |

不得把该表中的估计值直接作为 matched point。

---

## 3.4 搜索算法

对每个系统和目标维护：

```text
L_low  : median Recall < target
L_high : median Recall ≥ target
```

在两者之间使用整数二分或相邻局部搜索。

停止条件为：

```text
L_high = L_low + 1
```

此时 `L_high` 是最小达到 Recall floor 的实测整数 L。

接受该点还需满足：

```text
median Recall(L_high) ≤ target + 0.005
```

若 overshoot 大于 0.005，则记录：

```text
unavailable_due_to_parameter_granularity
```

不能用插值生成一个不存在的配置。

---

## 3.5 噪声处理

每个候选点必须有三次 valid 重复。

若某候选点的三次 Recall 横跨目标：

```text
min Recall < target ≤ max Recall
```

则为该 L 补充两次，形成五次重复，并根据五次 median 决定其位于 threshold 上方还是下方。

若相邻 L 的 median Recall 出现超过 `0.002` 的反向下降：

1. 两个 L 各补两次；
2. 检查 identity、I/O error 与调度异常；
3. 五次 median 仍明显反向时停止该系统 refinement。

不得使用 isotonic regression 修改原始测量值。

---

# 4. P2-M 通过条件

只有满足以下条件才自动进入 P2-B：

* 至少三个 Recall floor 成为三系统共同 matched point；
* 共同点中至少包含一个 `R ≥ 0.98`；
* 每个 matched point 均由实际整数 L 测得；
* 每个 point 的 median Recall 均位于 `[R, R+0.005]`；
* 每个 point 的所有重复均 valid；
* 三系统 artifact identity 未发生变化。

若不足三个共同目标，则停止并提交 refinement 报告，不进入正式 W0。

---

# 5. P2-B：Slim W0

## 5.1 Query concurrency

对每个通过 P2-M 的 Recall floor 运行：

```text
Tq = 1
Tq = 16
```

Tq=1 已用于 refinement。

若最终 matched L 已有三次完整、有效、identity 一致的 refinement 结果，这三次可以直接作为 Tq=1 正式结果，不重复执行。

---

## 5.2 Tq=16 参数处理

先使用 Tq=1 选出的同一个 L 运行三次。

若 Tq=16 median Recall 仍位于：

```text
[R, R+0.005]
```

则接受该 L。

若因并发非确定性而偏离目标区间，只允许在相邻 L 上进行局部 refinement，并重新选择 Tq=16 下满足 Recall floor 的最小 L。

必须分别记录：

```text
selected_L_tq1
selected_L_tq16
```

不能假设两个并发级别一定使用相同 L。

---

## 5.3 重复与失败处理

每个正式 point 至少三次。

每次都要求：

* 新进程；
  -独立 transient cgroup；
  -固定 CPU/NUMA；
  -drop OS page cache；
  -冻结 binary/index/query/GT/patch identity；
  -无 fatal、EBADF、负 CQE、assertion；
  -无 cgroup OOM；
  -真实 NVMe read bytes 大于 0；
  -Recall 有限；
  -返回码为 0。

任何 invalid run 都必须保留。

不得静默删除 invalid run 后补一个“替代样本”。出现 invalid run 时停止该 system–target–concurrency group，先提交原因。

---

# 6. 正式指标

每个 matched point 报告三次 raw 数据，以及：

```text
median
minimum
maximum
```

指标包括：

* actual median Recall@10；
* selected L；
  -driver-reported QPS；
  -external timed-search QPS；
* P50；
* P95；
* P99；
* mean latency；
* mean I/O；
* mean I/O latency；
* device read bytes；
* device read IOPS；
* device bandwidth；
* process-tree peak RSS；
  -cgroup memory peak；
  -cgroup memory.events；
* CPU utilization；
  -index load time；
  -warm-up time；
  -timed search time；
  -process wall time。

---

# 7. 计时口径

主要 query-path 指标使用 artifact driver 明确计时的：

```text
driver-reported QPS
driver-reported latency
driver-reported I/O
```

同时将以下值作为独立 end-to-end 审计口径：

```text
process wall
index load
warm-up
external timed-search envelope
```

不能混合 driver QPS 与 process wall 推导新的吞吐。

若 driver QPS 与 external QPS 差异较大，报告两者的计时边界，不选择对系统更有利的一个。

---

# 8. 输出

Codex 输出：

```text
codex/share/dynamic_vamana_p2b_matched_recall_w0_results_0715.md
```

机器可读结果：

```text
results/pilot3_sift10m_p2b/
├── refinement_raw.tsv
├── selected_matched_points.tsv
├── tq1_raw_runs.tsv
├── tq16_raw_runs.tsv
├── matched_recall_summary.tsv
├── timing_scope.tsv
├── resource_summary.tsv
└── raw/
```

至少生成：

1. Recall–QPS 曲线；
2. Recall–P99 曲线；
3. Recall–mean-I/O 曲线；
4. Tq=1 matched-Recall QPS；
5. Tq=16 matched-Recall QPS；
6. matched-Recall P99；
7. matched-Recall mean I/O；
8. serving DRAM；
9. external/driver timing reconciliation；
10. 每个目标的 selected L 表。

图中的每个点必须显示实际 Recall，不能只用名义 target 替代横坐标。

---

# 9. 解释边界

P2-B 可以比较：

* 当前三个完整 artifact 的 query frontier；
* matched Recall 下的吞吐、延迟和 I/O；
* Tq=1 到 Tq=16 的伸缩；
  -当前索引的 serving DRAM 与 SSD 空间。

P2-B 仍不能证明：

* 解耦机制本身优于或劣于耦合机制；
  -某个架构普遍支配其他架构；
  -动态更新性能；
* churn 稳定性；
  -完整 `Vq–Vm` frontier；
  -已经形成论文 Idea。

DGAI 的 build-only cross-NUMA exception 继续单独记录，不进入 serving query frontier。

---

# 10. 停止条件

P2-B 完成后立即停止。

不自动启动：

* 1% churn；
* 20% churn；
* DiskANN rebuild；
* W1；
* W2；
* DEEP10M；
* GIST1M；
* Fresh-Ref。

下一轮根据 matched-Recall W0 的实际结果决定：

* 是否存在有意义的 query frontier gap；
  -是否值得进入 W1；
  -是否需要先做 query-path 归因；
  -是否需要补充其他系统。

---

# 11. 最终授权

Codex 当前获授权：

```text
P2-M matched-point refinement
→ 满足共同目标条件后自动执行 P2-B
→ 完成 Tq=1/Tq=16 Slim W0
→ 汇总并停止
```

任何条件不满足时均 fail closed，不进入下一阶段。
