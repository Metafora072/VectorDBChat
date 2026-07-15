# PQ-Free SSD Exact Navigation：立项前门禁

## 当前判断

跨 embedding 版本 warm-start repair 已正式关闭。

PZ 提出新的候选假设：

> 在现代高带宽 SSD 上，是否可以不在 DRAM 中保留全量 per-vector PQ code，而是在搜索过程中主动读取完整向量、使用精确距离导航，从而在固定 recall 下减少内存，或在固定内存下提高 recall/吞吐？

当前只批准 prior-art 与 trace-level opportunity precheck，不批准系统实现，也不预设“去掉 PQ”一定有收益。

---

## 必须区分的三个目标

### 目标一：降低 DRAM

该目标必须直接对比 AiSAQ。

AiSAQ 已经将 PQ code 下沉到 SSD，在十亿级搜索中把查询内存降到约 10 MiB。若候选只是“不把 PQ 放在内存”，则问题已被覆盖。

候选必须证明：

- 不使用全量 per-vector PQ；
- 相比 AiSAQ 仍有明确的内存、延迟、吞吐或 recall 优势；
- 不是把 PQ 替换成另一个同规模的 per-vector sketch。

### 目标二：提高精度

必须证明 exact distance 在搜索过程中使用，而不仅是最终 rerank。

需要测量：

- PQ 排序与 exact 排序在每个 expansion 的分歧；
- 这些分歧有多少真正影响最终搜索路径；
- exact navigation 能减少多少 expanded nodes、iterations 和最终 I/O；
- recall 提升是否能通过普通增大 `L` 或 PQ code length 更低成本地获得。

### 目标三：固定 recall 下提高速度

这是最严格、也最有价值的目标。

只有 exact distance 减少的后续搜索工作量大于额外 full-vector reads，才可能提升速度。

---

## 候选架构边界

最有可能存活的形式不是逐 neighbor exact read，而是：

### Page-granular exact navigation

- SSD page 内放置多个完整向量；
- 一次读取页面后，对页内所有向量计算 exact distance；
- 页内向量共享一次 4 KiB/8 KiB I/O；
- 图的搜索与扩展单位部分提升为 page；
- DRAM 仅保留入口、page directory 或很小的路由结构；
- 不保留 O(N) 的 per-vector PQ table。

需要明确：

- 128D float vector 为 512 B，一页可能容纳多个向量；
- 384D 约 1.5 KiB，页面复用显著下降；
- 960D 约 3.75 KiB，4 KiB 页通常只能容纳一个完整向量。

因此候选必须跨不同维度验证，不能只在 SIFT-128 上成立。

---

## G0：Prior-art 对抗审计

Codex 优先审计：

- AiSAQ；
- PageANN；
- VeloANN；
- SkipDisk；
- GateANN；
- OctopusANN；
- Starling；
- DiskANN++；
- RaBitQ/AQR-HNSW；
- 其他 page-node、full-vector navigation 或 PQ-free disk ANN 工作。

重点回答：

1. PageANN 是否已经等价实现 page-level graph + representative/exact vector navigation；
2. VeloANN 的 hierarchical compression 和 affinity page 是否已经覆盖主要机制；
3. AiSAQ 在 SSD 上读取 neighbor PQ 的 I/O，与读取完整向量相比差多少；
4. 是否已有系统在 graph traversal 中使用 full-precision distance，而非只在 rerank 使用；
5. 任何候选内存 summary 是否实际上只是 PQ、SQ、RaBitQ 或 lower bound 的改名。

若完全等价的 page-level exact navigation 已存在，直接 Kill。

---

## G1：Trace-level I/O Exchange Rate

第一阶段不实现新索引。

使用现有 DiskANN/DGAI 搜索 trace，记录：

- 每次 expanded node；
- 其 neighbor IDs；
- PQ estimated distances；
- exact distances；
- neighbor 所在 vector pages；
- frontier 排序；
- search termination；
- 最终 recall。

离线模拟四种策略：

```text
P0: 标准 DRAM PQ 导航
P1: SSD-resident PQ，AiSAQ 风格
P2: exact-all-neighbor：读取所有新邻居完整向量
P3: exact-page：读取一个页面后，对页内所有向量做 exact distance

P3 至少模拟：

原始 ID/record layout；
理想容量约束 page packing；
图相似性 packing；
query co-visit oracle packing，仅作为不可实现上界。

报告：

DRAM bytes/vector；
full-vector reads/query；
unique pages/query；
bytes/query；
expanded nodes；
dependency depth；
每跳 eligible pages；
recall–page-read 曲线；
固定 Recall@10 下的 page-read 增减；
exact ranking 减少的后续扩展量；
单查询和高并发条件下的理论服务上界。
数据集

至少包含：

SIFT-128；
一个约 384D 的真实 embedding 数据集；
GIST-960 或同级高维数据集。

如果收益只存在于 128D，不能形成通用设计。

立即 Kill 条件

出现任一情况即停止：

内存目标已被 AiSAQ 以更低 I/O 成本实现；
exact-all-neighbor 的页面读取相比 PQ baseline 放大超过约 3×，且搜索扩展减少不足以抵消；
page-level exact 的收益在 384D/960D 消失；
PageANN 或 VeloANN 已覆盖等价机制；
成功必须依赖 O(N) 的新 per-vector summary；
fixed recall 下 exact navigation 不能减少端到端 I/O；
recall 提升可通过增加 PQ code 或 L 以更低成本获得；
只有不可实现的 oracle packing 有收益；
最终贡献只剩“高带宽 SSD 可以多读一些数据”。
继续条件

只有以下条件同时成立，才进入系统架构讨论：

不保留 O(N) per-vector PQ；
相比 AiSAQ 有明确而非边际的端到端优势；
exact-page 在至少两个不同维度上，固定 recall 的页面读取不高于 PQ baseline 的约 1.5×；
exact distance 显著减少搜索扩展或允许更小 beam/L；
Amdahl 上界支持至少约 1.3× 吞吐或数量级 DRAM 降低；
与 PageANN/VeloANN 的结构性区别能够清晰表述；
动态更新不会要求周期性全局 page repacking 才能维持收益。
Codex 产物

发布：

codex/share/pq_free_ssd_exact_navigation_precheck.md

只包含：

prior-art 边界；
PQ 在现有 search loop 中承担的精确作用；
四种策略的 trace simulation 设计；
三种维度下的 page-capacity 分析；
最强 baseline；
预计实验成本；
Continue-to-trace / Revise / Kill。

本阶段不实现新的 page graph，不替换 DiskANN 搜索，也不提前命名系统。

Claude 在 Codex prior-art 审计完成后，再从 novelty 和系统架构角度判断，不提前为候选补机制。