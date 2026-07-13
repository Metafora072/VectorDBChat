# 解耦架构问题的深度挖掘

**日期**：2026-07-13

## 1. 关键发现：领域比我们此前认知的更活跃

搜索后发现 2025–2026 年驻盘图 ANN 出现了一批新工作，超出我们此前的文献覆盖：

| 工作 | 时间 | 架构类型 | 核心机制 | 改善幅度 |
|------|------|---------|---------|---------|
| OctopusANN (PVLDB 2026) | 2602.21514 | 耦合 | I/O-first design space: MemGraph + PageShuffle + PageSearch + DynamicWidth | Starling +4.1–37.9% throughput |
| LAANN | 2606.02784 (June 2026) | 耦合 | Look-ahead search + priority I/O-CPU pipeline + **customized candidate pool with overflow area** + in-memory seed graph | 1.41–4.66× throughput, 29–79% lower latency |
| GoVector (Journal of Software 2026) | 2508.15694 | 耦合 | Static + dynamic cache + disk reordering for spatial locality | 46% fewer I/O ops, 1.73× throughput |
| LIOS | 2605.19335 | 耦合 | Leveraging I/O stalls for scheduling computation during waits | — |
| DecoupleVS | 2604.09173 | 解耦 | Component-aware compression for decoupled vector/index storage | Update +10.05×, query +2.66× |
| Onyx | 2604.20401 | — | Disk-oblivious (TEE/ORAM) ANN, compact intermediate representation | 1.7–9.9× lower cost |
| BAMG | 2509.03226 | 耦合 | Block-aware monotonic graph | — |
| Disk-Resident Graph ANN Experimental Evaluation | 2603.01779 (March 2026) | Both | 系统性实验评估所有驻盘图 ANN 设计维度 | 对比框架 |
| NAVIS | 2605.11523 | 混合 | 低 position-seeking 开销的并发搜索与更新 | — |

## 2. PZ 提到的"pool"是什么

PZ 说"有一篇工作指出了 DGAI 的问题（查询慢 20%+），做了什么 pool 解决了这个问题"。根据搜索结果，有几个可能：

### 可能性一：DGAI 自身的机制

DGAI 论文自身指出：raw decoupled storage 导致查询延迟增加 **23%+**。DGAI 自身的解决方案包括：
1. **Three-stage query**：用 multi-PQ 候选过滤，避免无效坐标 I/O
2. **Topology-only buffer**：只缓存拓扑不缓存向量，最大化驻留图节点数——这是一种特殊的 buffer pool
3. **SADL（Similarity-Aware Dynamic Layout）**：增量重排让相似向量在物理上相邻

三者合起来，DGAI 声称 query 比传统耦合架构快 2.57×。

### 可能性二：LAANN 的 candidate pool

LAANN (June 2026) 引入了 **"customized candidate pool with overflow area"**——一个专门为 look-ahead search 设计的候选池。不过 LAANN 是基于耦合架构，不是专门解决 DGAI 的问题。

### 可能性三：GoVector 的 dynamic cache

GoVector 引入了 **static + dynamic cache** 组合策略：static cache 存入口点和高频邻居，dynamic cache 自适应捕获搜索第二阶段的高空间局部性节点。这也是一种 "pool" 概念。

### 可能性四：DecoupleVS

DecoupleVS (2604.09173) 专门处理解耦向量数据和索引存储的空间效率问题。基于 PipeANN 代码库，使用 io_uring。声称 update +10.05×, query +2.66×。

**建议**：PZ 最清楚自己想的是哪篇。我倾向认为是 **DGAI 自身的三阶段查询 + topology-only buffer** 或者 **DecoupleVS**。PZ 可以确认。

## 3. 现有解决方案引入了什么新问题

### 3.1 DGAI 三阶段查询的问题

1. **PQ 质量依赖**：三阶段查询的过滤效果完全取决于 PQ 编码质量。PQ 在高维、分布不均匀数据上可能质量差 → 过度保守（不过滤，没收益）或过度激进（误滤，质量损失）。
2. **多 PQ 内存开销**：三阶段使用 multi-PQ，每套 PQ 都需要 codebook 在内存中。数据规模增大时内存压力增加。
3. **流水线延迟**：三个阶段串行执行，单查询延迟增加。吞吐量可能提升但 p99 可能恶化。

### 3.2 Topology-only buffer 的问题

1. **完全放弃向量缓存**：热向量无法被缓存复用。如果某些文档被高频查询（热点文档），每次都要从 SSD 重新读坐标。
2. **缓存策略固定**：static + dynamic 分区的比例是固定的，不能根据 workload 动态调整。
3. **与 SADL 的冲突**：SADL 重排向量位置，但重排后的新位置可能破坏 buffer 的局部性假设。

### 3.3 SADL 的问题

1. **写放大**：增量重排需要移动数据页，产生写放大。在 write-sensitive 场景（如 SSD 寿命关注）下不利。
2. **重排收敛性**：如果 query workload 频繁变化（distribution shift），SADL 的布局可能永远不收敛。
3. **重排与并发的冲突**：后台重排期间，并发查询和更新需要协调。DGAI 用 page-level locking，但锁竞争在高并发下可能成为瓶颈。

### 3.4 跨系统的共同问题

1. **耦合架构的 I/O 优化不能直接迁移到解耦架构**。OctopusANN/LAANN/GoVector 的优化（MemGraph、look-ahead、page shuffle）全部基于耦合架构。解耦架构的 I/O 模式不同（两轮 I/O vs 一轮），这些技术需要重新设计才能适用。
2. **没有系统同时优化 update 效率和 query 效率**。耦合架构 query 好但 update 差（79%+ redundant I/O during updates）；解耦架构 update 好但 query 需要额外机制。
3. **现代高带宽 SSD 下的重新评估缺失**。大部分优化基于"减少 I/O 次数"，但在 7GB/s SSD 上，"增大单次 I/O 以换取更少次数"的 trade-off 可能更优。

## 4. 可能的论文故事方向

### 方向 A：解耦架构的 I/O 优化迁移

**核心问题**：OctopusANN/LAANN 的 I/O 优化在耦合架构上取得巨大成功（最高 4.66× throughput），但解耦架构需要不同的 I/O 优化策略，因为它的 I/O 模式（topology read → PQ filter → coordinate read）是两阶段的。

**贡献**：将先进 I/O 技术（MemGraph、look-ahead、page shuffle）适配到解耦架构，同时保持其 update 优势。

**风险**：可能发现简单适配就够了，没有新机制需求。

### 方向 B：痛批现有方案的场景性问题

**核心思路（PZ 的建议）**：系统性地找出 DGAI 的三阶段查询 + SADL + topology-only buffer 在什么场景下仍然有问题：
- 高维数据（PQ 质量差）
- 热点查询（topology-only buffer 不缓存向量）
- 分布漂移（SADL 不收敛）
- 高并发混合负载（锁竞争）
- 大规模数据（内存放不下 multi-PQ）

然后针对最显著的问题设计解决方案。

**优势**：完全问题驱动，故事自然。

### 方向 C：统一视角——解耦架构 + 现代 SSD 的重新设计

**核心问题**：解耦架构在 7GB/s NVMe 时代需要重新设计。DGAI 的优化是在旧 SSD 假设下做的（减少 I/O 次数），但现代 SSD 的特性（高带宽、低延迟、io_uring）改变了最优设计点。

**贡献**：characterization（解耦在新硬件上的 I/O 行为）+ 系统设计（利用新硬件特性的解耦架构优化）。

## 5. 建议下一步

PZ 先确认：
1. 你提到的"pool"是 DGAI 自身的 topology-only buffer，还是另一篇工作（DecoupleVS? LAANN? GoVector?）？
2. 你更倾向方向 A（迁移耦合优化到解耦）、B（场景性问题痛批）、还是 C（现代 SSD 重新设计）？

无论选哪个方向，第一步都是在 DGAI 上做 characterization pilot——量化现有三阶段查询 + SADL 在不同场景下的实际表现和问题。
