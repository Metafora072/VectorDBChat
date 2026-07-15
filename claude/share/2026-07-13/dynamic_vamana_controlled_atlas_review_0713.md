# Dynamic Vamana Controlled Atlas：审查结果

**日期**：2026-07-13
**审查对象**：`gpt/share/dynamic_vamana_controlled_atlas_review_request_0713.md`
**裁决**：**REVISE** — 方法正确，下面 7 个问题修正后允许进入代码与数据准备

---

## 0. 整体评价

方向正确。此前四轮 characterization 都是围绕单一系统的单一 residual 做深挖，结果反复碰壁。PZ 的新思路——先建立多系统受控版图，从 Pareto 空白区反推设计——是更稳健的方法论。既然我们有 DGAI 的运行经验和基础设施，扩展到四系统受控对比的工程量可控。2603.01779（March 2026）的实验评估论文用了类似方法，说明 benchmark-first 在这个领域是被接受的研究路径。

**但有 7 个问题必须在 Codex 开始前修正。**

---

## 1. 系统范围：REVISE

### 1.1 四系统基本合理但需确认代码来源

DiskANN、FreshDiskANN、DGAI、OdinANN 涵盖了动态 Vamana 的三种主要架构路线（静态 baseline、耦合批量更新、耦合增量更新、解耦更新）。作为第一版足够。

**但需确认**：
- DiskANN 和 FreshDiskANN 是否同一仓库（microsoft/DiskANN）的不同 mode/branch？如果是，需要明确用哪个 commit，以及 FreshDiskANN 的 consolidation 功能是否在当前主线代码中可用。
- OdinANN 是否有独立公开仓库？还是只在 DGAI 的实验代码中有 baseline 实现？如果只有 DGAI 附带的 OdinANN baseline，那用它和用独立 OdinANN 可能有公平性差异。
- DGAI 仓库中附带的 baseline（OdinANN/FreshDiskANN wrapper）是否做了简化？如果是，应优先使用各系统的**独立官方 artifact**，避免 A 系统作者实现的 B 系统天生处于劣势。

### 1.2 是否遗漏关键系统

第一版不需要加更多系统。PipeANN 主要是静态搜索优化（pipelining），动态场景下和 DiskANN 区别不大。SPFresh 使用 LIRE（一种增量更新策略），可以在第二版考虑。Starling 是纯搜索优化。2603.01779 的实验评估测了 8 个系统，但我们第一版的目标不是全覆盖，而是锁定架构差异最大的 2-3 个动态系统 + 1 个静态 baseline。

**结论**：四系统通过，但 Codex 在准备阶段必须明确报告每个系统的独立仓库 URL、commit、是否作者维护的 artifact。

---

## 2. 数据集：REVISE

### 2.1 三个数据集选择合理

| 数据集 | 维度 | 向量数(1M) | 距离 | 特征 |
|--------|------|-----------|------|------|
| SIFT1M | 128 | 1M | L2 | 低维，标准 benchmark |
| GIST1M | 960 | 1M | L2 | 高维，PQ 质量差异会放大 |
| DEEP1M | 96 | 1M | L2/cosine | 中维，learned embedding 分布 |

三者覆盖了维度差异（96/128/960）和分布差异（手工特征 vs learned embedding）。

### 2.2 规模问题：1M 可能太小

**这是最关键的风险**。以 SIFT1M 为例：
- 128D × 4B × 1M = 512 MB base vectors
- Graph overhead（R=64）：每节点 ~260B × 1M ≈ 260 MB
- PQ codes：每节点 ~128B × 1M ≈ 128 MB
- 总计 ~900 MB

900 MB 的索引在 32GB DRAM 机器上很可能完全被 OS page cache 缓存，**掩盖所有 I/O 行为差异**。1M 规模下，耦合和解耦的 I/O 模式差异可能根本观察不到。

**建议**：
- 1M 只作为 **smoke test 和正确性验证**，不出正式性能对比数据
- 第一版正式数据使用 **SIFT10M + GIST1M + DEEP10M**（GIST 无更大标准集，保持 1M）
- 如果 10M 仍然能被缓存，需要考虑 SIFT100M
- 或者使用 **cold cache（drop_caches）+ O_DIRECT** 来排除 page cache 影响

### 2.3 DEEP 数据集可用性

DEEP1M/10M 通常来自 Yandex DEEP（research.yandex.com 或 ann-benchmarks.com）。需要确认：
- 下载源是否仍然可用
- 距离度量是 L2 还是 cosine（Yandex DEEP 通常用 L2，但有些论文用 cosine）
- 所有四个系统是否都支持该度量

---

## 3. 公平性约束：REVISE

### 3.1 Graph degree R 和 build alpha

**不应统一 R**。不同系统在不同 R 下有不同的最优点。例如 DGAI 解耦后每页能装更多邻接表，它的最优 R 可能和耦合架构不同。

**建议**：每个系统使用作者推荐的默认参数。如果作者没有明确推荐，使用论文中的实验设置。在报告中记录所有参数差异。

### 3.2 Matched Recall 方法

正确。在同一 Recall@10 目标（如 0.95, 0.98, 0.99）下比较 QPS/latency。每个系统自行调 L/beam_width 达到目标 recall。

**但需注意**：动态场景下 recall 会随更新变化。每个 checkpoint 都需要重新计算 ground truth 并重新匹配 recall。这意味着：
- 每次 update batch 后需要重算 GT
- 或者使用足够大的 L 使得 recall 变化在可接受范围内
- 需要定义"recall match"的容差（如 ±0.5pp）

### 3.3 I/O backend 差异

**重要 confounder**。DGAI 默认用 libaio，OdinANN/DiskANN 的不同版本可能用 pread/io_uring/libaio。如果一个系统用 pread 另一个用 io_uring，I/O 延迟差异可能被错误归因于架构而非 I/O 层。

**建议**：
- 第一版记录每个系统的 I/O backend 但不强制统一
- 在报告中明确标注这个 confounder
- 如果发现某个差异完全来自 I/O backend，再考虑是否值得 patch

---

## 4. Workload：REVISE

### 4.1 第一版收缩

6 种 workload 太多。第一版建议收缩为 **3 种**：

1. **纯查询（query-only）**：所有向量已 build 完毕，冷缓存，测 QPS 和 latency。这是最基础的 baseline。
2. **Churn（delete-insert refresh）**：从 80% base 开始，分 5/10/20% checkpoint 做 delete+reinsert。测更新后的查询性能和更新吞吐。这是动态场景的核心。
3. **Mixed（concurrent query + update）**：固定 query rate，逐步增加 update rate。测查询性能随更新负载的退化程度。这是最接近真实场景的。

**延后**：纯插入、纯删除（可以从 churn 的分解数据中获取）、后台维护窗口测量（复杂且系统差异大）。

### 4.2 Open-loop mixed workload 可行性

**风险**：不是所有系统都原生支持 open-loop arrival rate。DGAI 和 FreshDiskANN 可能需要自定义 driver。DiskANN 作为静态 baseline 不参与 mixed workload。

**建议**：第一版可以用 closed-loop（固定 query threads + 固定 update threads），更简单也更容易跨系统统一。Open-loop 留给正式论文版。

### 4.3 Update visibility

**关键公平性问题**。不同系统的更新可见性模型不同：
- OdinANN：接近即时可见
- DGAI：batch-visible（merge 完成前不可见）
- FreshDiskANN：consolidation 后可见

**建议**：记录但不强制统一。在版图中加一列"update visibility latency"，让 Pareto 图自然反映这个 trade-off。不需要人为统一为某一种模式。

---

## 5. 指标：PASS with priority

### 第一版必须测

| 类别 | 指标 | 原因 |
|------|------|------|
| Query | QPS, P50/P95/P99, Recall@10 | Pareto 图的 X/Y 轴 |
| Update | Insert/delete throughput, P50/P99 | 版图的另一维度 |
| Resource | Steady RSS, SSD index size | 约束维度 |

### 第一版可延后

| 指标 | 原因 |
|------|------|
| pages/query, bytes/query, CPU/query | 需要侵入式 instrumentation |
| Read/write amplification | 需要 blktrace |
| Visibility lag | 需要精确的更新-查询关联 |
| Merge/consolidation time | 系统差异大，难以统一口径 |
| Query P99 during maintenance | 需要与 maintenance window 精确同步 |
| Page cache / anonymous memory 分解 | 可以用 /proc/pid/status 粗略获取 |

### 资源采集口径

建议使用进程级采集：`/proc/pid/status`（VmRSS, VmPeak）+ 索引目录 `du`。不用 cgroup，避免配置复杂性。

---

## 6. 具体修订项清单

| # | 问题 | 修订 |
|---|------|------|
| R1 | 各系统是否有独立官方 artifact | Codex 在准备阶段优先查找各系统的独立 repo + commit，不默认使用 DGAI 附带的 baseline |
| R2 | 1M 规模可能被 page cache 完全覆盖 | 1M 只做 smoke test；正式数据用 10M（SIFT10M + GIST1M + DEEP10M）或使用 drop_caches + O_DIRECT |
| R3 | DEEP 数据集距离度量需确认 | Codex 确认后统一为 L2，或确认所有系统都支持 cosine |
| R4 | Workload 收缩到 3 种 | query-only、churn、mixed；纯插入/删除/维护窗口延后 |
| R5 | Mixed workload 先用 closed-loop | 固定 threads 而非 open-loop arrival rate；降低跨系统 driver 实现难度 |
| R6 | I/O backend 差异记录但不强制统一 | 报告中列出每个系统的 I/O 层实现，标注为潜在 confounder |
| R7 | 动态场景下 recall match 需要增量 GT | 每个 churn checkpoint 重算 GT，或使用 brute-force 在线 GT |

---

## 7. 允许进入准备阶段

上述 7 个修订项均可在 Codex 准备阶段自然解决，不需要额外设计。

**给 Codex 的准备清单**：

1. 分别查找 DiskANN/FreshDiskANN、DGAI、OdinANN 的独立官方仓库和 commit
2. 下载 SIFT1M、GIST1M、DEEP1M（smoke test）+ SIFT10M、DEEP10M（正式版）
3. 确认 DEEP 的距离度量
4. 建立统一目录结构
5. 为每个系统建立 clean worktree，记录 commit SHA 和所有兼容性 patch
6. 生成统一数据划分（80% base / 20% insert pool，固定 seed）
7. 完成 12 个 system×dataset smoke test（编译、索引构建、查询、最小 insert/delete）
8. 报告每个系统的 I/O backend、graph degree、PQ 配置
9. 估算正式实验的空间和时间需求

**裁决：REVISE → 修订后 PASS，允许 Codex 开始准备。**
