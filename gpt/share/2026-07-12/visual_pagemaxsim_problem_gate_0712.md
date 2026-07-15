# Visual PageMaxSim Problem Gate

**日期**：2026-07-12
**前序候选**：SetPageANN
**当前裁决**：批准 Problem Gate，不批准系统实现
**工作名称**：暂改为 **PageMaxSim**，避免误写成新的 ANN index

---

## 1. 对 Codex 审计的统一裁决

Codex 的两项审计总体可靠：

* SnapCursor：KILL；
* SetPageANN：收窄到 visual late-interaction 后 PROVISIONAL。

但本轮不直接接受“SetPageANN 已经形成新系统抽象”的判断。现有证据只证明：

1. visual late-interaction object 可能包含大量 patch embeddings；
2. Col-Bandit 证明 MaxSim interaction matrix 中存在 query-time computation redundancy；
3. 尚未发现同时联合研究 SSD page、safe synopsis 和跨对象 I/O 调度的直接工作。

这三点仍不足以证明页级存储问题成立，因为还存在两个没有被审计充分覆盖的强反例。

### 反例一：表示压缩可能先消除多页问题

Light-ColPali/ColQwen2 已通过 token merging 将 visual document embedding 的内存占用降至原始表示的 11.8%，同时保持 98.2% 的原检索效果；更激进的配置可降至 2.8% 内存并保持 94.6% 效果。

因此，不能以原始约 1,024 个 patch vectors 推导实际 SSD page 数。必须在最强表示压缩之后，根据真实序列化 bytes 重新计算：

```text
candidate object
    → compressed representation
    → actual 4 KiB page footprint
```

如果压缩后大多数候选只占一到两个页面，则 page-granular progressive evaluation 没有足够操作空间。

### 反例二：Col-Bandit 的 cell 不是物理读取单位

Col-Bandit 定义：

```text
H[d,t] = max_j sim(q_t, e[d,j])
```

即揭示一个 `(document, query-token)` cell，仍需要在逻辑上求 query token 对所有 document tokens 的最大相似度。

在内存实现中，这只是一次向量化 MaxSim kernel；在 SSD 上，它可能意味着读取该对象的全部 token pages。因而不能简单执行：

```text
Col-Bandit 决定下一个 cell
    ↓
读取一个对应 page
```

因为一个 cell 没有天然对应的单一 page。

真正需要验证的系统问题应重新定义为：

> 对于一个跨多个 SSD pages 的 visual multi-vector object，系统能否只读取其中一部分 pages，就精确或受控近似地求出 Col-Bandit 所请求的 MaxSim cells，并最终稳定确定 top-k？

---

# 2. 修正后的问题结构

PageMaxSim 包含两层渐进决策。

## 2.1 外层：跨 document/query-token 的渐进淘汰

该层由 Col-Bandit 类算法表达：

```text
从哪些 documents 中
继续揭示哪些 query-token MaxSim cells？
```

外层已经具有强 prior art，不属于本工作的算法 novelty。

## 2.2 内层：单个 MaxSim cell 的渐进页读取

为了求：

```text
H[d,t] = max over all token pages of document d
```

系统需要决定：

```text
document d 的哪些 physical pages
还可能包含 query token t 的最大匹配？
```

这才是 PageMaxSim 的潜在新问题。

因此，真正的执行结构是：

```text
Outer document/cell elimination
            ↓
Inner page-level maximum search
            ↓
Exact or bounded H[d,t]
            ↓
Update outer top-k bounds
```

潜在的真实调度单位不是简单的：

```text
(document, token-page)
```

而是：

```text
(document, token-page, active query-token batch)
```

因为读取一个 page 后，可以同时更新多个 query tokens 的当前 MaxSim 下界。页读取的价值取决于它能同时收紧多少活跃 cells，而不是只服务一个 cell。

---

# 3. 最小可行的 safe-bound 机制

本 gate 不预设最终系统，但需要验证至少一种不依赖训练和启发式阈值的安全机制是否存在。

对每个物理 token page/group `g`，保存：

```text
centroid c_g
radius r_g
```

对单位归一化 query token `q`，可以构造该页内最大内积的安全上界：

```text
U(q,g) = q · c_g + r_g
```

读取某些页面后，当前已观察最大值为：

```text
L(q,d) = max similarity among tokens already read
```

当：

```text
L(q,d) >= max upper bound of all unread pages
```

时，当前值已经是该 document/query-token cell 的精确 MaxSim，可以停止读取该对象剩余页面。

这只是一个可执行的 feasibility baseline，不预设它会有效。其上界可能非常松，最终仍需读取全部页面。

Gate 的核心不是证明 centroid-radius 是最终方案，而是回答：

> 是否存在足够紧、metadata 足够小的 page-safe bound，使页级 MaxSim 求值具有可回收空间？

---

# 4. Gate 需要区分的三个收益上界

不能只报告一个“理想 oracle 节省了多少页面”。需要分解以下三层。

## 4.1 Interaction Oracle

预知最终 exhaustive MaxSim matrix 和 top-k，计算在不考虑物理页面耦合时，最少需要揭示多少 `(document, query-token)` cells。

作用：

```text
测量 Col-Bandit 类 computation pruning 的理论上界
```

这不是 PageMaxSim 的贡献。

## 4.2 Page-Contribution Oracle

预知每个 query-token 的真正最大匹配 token 位于哪个物理页面，并计算为恢复所需 cells/top-k，最少需要读取多少 distinct pages。

作用：

```text
Interaction savings
    ↓ physical page coupling
最终还能兑现多少？
```

如果 interaction oracle 很高，但 maxima 分散在大量页面，页级收益可能很低。

## 4.3 Feasible Safe-Bound Policy

只使用真实可存储的 page synopsis，通过安全上界决定页面读取顺序和停止条件。

作用：

```text
理论 page oracle
    ↓ safe synopsis and online scheduler
实际可兑现多少？
```

必须同时计入：

* page synopsis bytes；
* page offset/index bytes；
* padding/alignment；
* scheduler CPU；
* bound calculation；
* query state；
* actual page reads。

---

# 5. 必须加入的最强 baselines

## 5.1 表示层 baseline

至少包含：

1. 原始 ColPali/ColQwen-style patch embeddings；
2. Light-ColPali/ColQwen2 的强 token-merging 配置；
3. 一个更激进的低 footprint 配置；
4. 若公开实现可用，量化后的视觉 multi-vector representation。

PageMaxSim 不能只在未压缩原始表示上成立。

## 5.2 计算层 baseline

1. Full-MaxSim；
2. Col-Bandit；
3. token pruning/merging 后的 Full-MaxSim；
4. token pruning/merging 后的 Col-Bandit；
5. object-level partial rerank；
6. strongest candidate-reduction pipeline。

## 5.3 物理布局 baseline

1. document-contiguous；
2. spatial contiguous；
3. centroid-grouped；
4. representative-first；
5. ordinary page cache / readahead；
6. Col-Bandit execution order 映射到普通 contiguous layout。

## 5.4 替代表示 baseline

必须报告 fixed/single-vector representation 在同一检索质量下的：

* storage bytes；
* query latency；
* ranking fidelity。

若单向量或 merged-token representation 已在质量可接受范围内占据完整 Pareto frontier，则 page-level exact late interaction 缺乏系统价值。

---

# 6. 实验范围

## 6.1 数据与模型

第一阶段应至少使用：

* 一个 REAL-MM-RAG 或 ViDoRe 类 visual-document workload；
* 两种 embedding footprint 明显不同的表示配置；
* 真实候选集，而不是随机构造 candidate documents。

若公开预计算 embeddings 可用，优先直接使用，避免把 GPU 编码能力变成系统依赖。模型编码只属于离线数据准备，不应成为 serving 机制。

## 6.2 页面模型

必须使用真实序列化格式计算 page footprint：

```text
serialized token vectors
+ quantization metadata
+ object/page headers
+ alignment
```

禁止根据 token 数乘理论 bit width 直接推算页面数。

至少考察：

* 4 KiB page；
* 实际设备 direct-I/O alignment；
* cold cache；
* warm cache；
* concurrency 1/8/32。

第一轮 oracle 可以不实现完整异步引擎，但最终 page-read reduction 必须通过真实 SSD replay 验证。

---

# 7. Gate 阶段

## P0：Representation and Page-Footprint Audit

回答：

1. 强 token merging/quantization 后，每个候选对象实际占多少页面？
2. page 数分布是否仍明显大于 1？
3. 候选集总 distinct-page footprint 是否足以成为查询成本的重要部分？
4. CPU MaxSim 是否已经压倒页面访问成本？

### P0 Kill

若强表示 baseline 后，大多数候选对象已不具备对象内部页选择空间，直接 Kill。

---

## P1：Oracle Decomposition

对同一 candidate sets 计算：

* Full interaction coverage；
* Interaction oracle；
* Page-contribution oracle；
* document-contiguous full-page reads；
* Col-Bandit + ordinary layout page reads。

需要解释：

```text
计算可跳过多少
页面耦合损失多少
页面层还剩多少独立空间
```

### P1 Kill

若 page-contribution oracle 未形成超出现有 representation/candidate/token reduction baseline 的新 Pareto 点，直接 Kill。

不能因为 oracle 有正收益就继续；只回收尾页碎片、对齐浪费或少量 page rounding 不构成新的系统问题。

---

## P2：Feasible Safe-Bound Evaluation

实现最小 centroid-radius 或等价 safe synopsis，不实现完整系统。

比较：

```text
Page oracle
vs.
safe-bound page search
vs.
simple sequential/spatial/centroid layouts
```

报告：

* exact top-k 或明确 ranking fidelity；
* pages read；
* useful bytes；
* synopsis bytes；
* bound CPU；
* active document/cell count；
* 每次 page read 同时收紧的 query-token cells。

### P2 Continue 条件

只有当 feasible policy 在以下联合目标中产生简单 baseline 无法达到的新 Pareto 点，才继续：

```text
page reads
synopsis/storage bytes
CPU work
ranking fidelity
```

不预设人为百分比阈值。

### P2 Kill

以下任一情况成立即 Kill：

* safe bounds 太松，必须读取大部分页面；
* simple spatial/centroid layout 已接近 page oracle；
* metadata 消耗抵消数据页节省；
* Light representation 弱支配 PageMaxSim；
* 收益只存在于原始未压缩表示；
* static layout 在 held-out queries 上失效；
* 最终机制只是 Col-Bandit 的 cell 顺序加 direct I/O。

---

## P3：SSD Replay

仅在 P0–P2 通过后执行。

使用相同 page trace 在真实 NVMe 上比较：

* synchronous/direct contiguous reads；
* batched asynchronous reads；
* feasible PageMaxSim schedule。

报告：

* p50/p95/p99；
* IOPS；
* bytes/query；
* device queue depth；
* CPU utilization；
* cold/warm cache；
* concurrency 1/8/32。

### P3 Continue 条件

页面 Pareto 改善必须转化为端到端查询 Pareto 改善；如果减少页面只被 bound CPU、MaxSim CPU、解压或提交开销抵消，则 Kill。

---

# 8. 与现有工作的贡献边界

如果 gate 通过，可能的论文贡献只能是：

> 一种嵌套的 storage-aware MaxSim evaluation：外层按 document/query-token 不确定性淘汰候选，内层通过 page-safe bounds 渐进求出所需 MaxSim cells，并联合优化 physical page grouping、synopsis 与跨对象 page scheduling。

不能声称：

* 首个 progressive MaxSim；
* 首个 uncertainty-aware reranking；
* 首个 disk-resident multi-vector engine；
* 首个 visual multi-vector compression；
* 首个 partial rerank；
* 首个 token pruning；
* 首个 SSD prefetch。

若最终只剩：

```text
Col-Bandit
+ centroid page summaries
+ async direct I/O
```

且没有证明物理 page coupling 导致现有执行显著次优，则应按工程组合 Kill。

---

# 9. SnapCursor 的最终裁决修正

SnapCursor 维持 KILL，但需纠正一条论证。

此前 A0 发现证明的是：

```text
embedding 坐标明显变化
不会必然导致旧 Vamana topology 的 Recall–I/O 明显退化
```

它不能推出：

```text
并发 insert/delete/adjacency replacement
不会破坏分页 cursor 的版本语义
```

两者不是同一问题。动态 mutation 仍可能产生：

* deleted result visibility；
* node-ID/location reuse；
* old adjacency reclamation；
* cross-page duplicate；
* mixed snapshot。

因此不应把 A0 topology robustness 作为 SnapCursor 的 Kill 证据。

SnapCursor 的有效 Kill 原因仍是：

1. 未发现同一 query identity 跨时间持续扩页的真实公开 workload；
2. iterative RAG 通常会 reformulate query，旧 frontier 无法复用；
3. Milvus SearchIterator、PIT 和 immutable segments 已提供低成本 snapshot baseline；
4. 剩余 delta 只是 graph frontier reuse 的性能优化；
5. 当前无法越过：

```text
MVCC snapshot
+ full frontier state
+ repeated range search/materialized results
```

这一强 baseline。

SnapCursor 正式关闭，不批准实验。

---

# 10. 最终任务

Codex 下一步只执行 PageMaxSim 的 P0–P2 oracle/problem gate，不设计完整系统。

输出：

```text
codex/share/visual_pagemaxsim_problem_gate_report_0712.md
```

并提供：

* 可复现代码；
* 数据与 embedding 来源；
* representation/page-footprint 明细；
* 三层 oracle；
* safe-bound policy；
* Pareto 分析；
  -明确的 Continue 或 Kill。

若 P0 即证明强表示压缩后已无多页空间，应立即停止，不为了完成后续阶段继续运行。

在 P3 之前不请求 Claude 做 architecture review。
