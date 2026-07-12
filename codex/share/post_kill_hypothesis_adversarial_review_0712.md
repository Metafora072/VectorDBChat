# Architecture Idea Council：Codex 独立对抗审查

日期：2026-07-12

## 总裁决

| 候选 | 裁决 | 核心原因 |
|---|---|---|
| 1. 低 DRAM PQ 分层 | **KILL** | AiSAQ、LM-DiskANN、Starling/PageANN 已直接覆盖问题与主要结构；Claude 对现有系统的描述有事实错误 |
| 2. 多 NVMe 图感知放置 | **KILL** | PipeANN 已做 4 KiB SPDK 多盘条带；候选的单查询延迟模型与实验资源假设均不成立 |
| 3. 坐标漂移增量修复 | **REVISE** | 问题真实，但把跨 embedding 空间迁移误建模为 Gaussian noise，edge watermark 不能闭合 RobustPrune 的集合语义 |
| 4. 查询驱动拓扑自愈 | **KILL** | 静态索引不会随查询时间自行退化；dead-end 不是因果信号，Quake/GATE 等简单强 baseline 已覆盖真实 workload-skew 问题 |

本轮 **零个候选达到 `PROVISIONAL`**。候选三可以彻底改题后重新提交 Council，但当前版本不应进入 Problem Gate。审查覆盖 2024–2026 一手论文、正式 artifact、本机代码与硬件；第二个独立审查者得到相同的四项裁决。

---

## 候选一：低 DRAM 资源比例下的图索引可运行性

### 裁决：KILL

### Prior-art 攻击

该候选最核心的两项主张——“全量 PQ 必须驻留 DRAM”以及“PQ 下沉后每跳需要额外随机 I/O”——已经被直接解决。

- [AiSAQ](https://arxiv.org/abs/2404.06004)（2024 预印本）把邻居 PQ 码与当前节点记录共同放入 SSD node chunk，使一次原有图页读取同时取得下一跳所需 PQ，不增加独立 PQ read。论文报告十亿规模查询内存约 10 MiB，而非 `O(N)` PQ DRAM。
- [LM-DiskANN](https://par.nsf.gov/biblio/10539353)（IEEE BigData 2023）同样把完整邻居路由信息/PQ 放入磁盘节点记录，并明确支持动态 insertion/deletion。它已覆盖“低 DRAM + 动态图”的组合边界。
- [Starling](https://arxiv.org/abs/2401.02116)不是 Claude 所称的“完整拓扑压缩副本”。原文从全量数据采样一个低于 10% 的子集建立内存 navigation graph，并按 segment memory limit 调节样本比例和度，结构上已经是 routing backbone + disk graph。
- [PageANN](https://arxiv.org/abs/2509.25487)（2025 预印本）明确以 lightweight routing index、page-node graph 和 memory–disk coordination 处理受限内存；[SkipDisk](https://arxiv.org/abs/2605.05787)（2026 预印本）又给出约 10%/20% memory footprint 的多层 pruning 方案。

因此候选的结构实际是 Starling 的 sampled routing graph 与 AiSAQ/LM-DiskANN 的 PQ-on-SSD 组合，不能形成新的系统抽象。`O(√N)` 也不是自动成立的不变量：若要让骨干从任意入口路由到所有 dense regions，仍需 region membership、entry mapping 或跨区连边元数据；这会退化成已有 partition/page-node 架构。

### 问题真实性与 baseline 攻击

- DiskANN 的典型 PQ 长度并非固定 128–384 bytes；SIFT1B 常用 32-byte PQ，对应约 32 GiB。Claude 把高码长当作普遍配置，夸大了最低 DRAM 需求。
- “没有 graceful degradation”和“PQ 下沉必然慢 10–50×”均被 AiSAQ 的一手结果否定。
- 最强 baseline 不是 full-PQ DiskANN，而是相同 DRAM budget 下的 AiSAQ、LM-DiskANN、PageANN，再叠加普通 hot-record/PQ cache。候选没有说明能在 recall、IOPS、SSD space 或 update cost 的哪一项同时胜过它们。
- SIFT-1M 的 PQ 只占几十至百余 MiB，强行限内存不能验证十亿规模经济问题。

### 可实现性攻击

DGAI 可以原型化 PQ miss，但这只是复现已知 trade-off。动态维护 routing backbone 还需处理新节点归区、骨干连通性、删除和 metadata scaling，Claude 的 200 行估计明显不足。

### 最终边界

当前候选及其 gate 均关闭。不应转成“动态 AiSAQ”或“Starling + 更新”，因为 LM-DiskANN 已占据该邻域。

---

## 候选二：多 NVMe 图感知数据放置

### 裁决：KILL

### Prior-art 与事实攻击

[PipeANN 官方主线](https://github.com/thustorage/PipeANN)已经提供 SPDK multi-SSD backend。本机审计的官方提交 `9e7a193dc3f38ad12063bfe50aa5885efb4e8d3b` 中：

- 每块 SSD 有独立 poller 和 NVMe queue pair；每个 search thread 可向所有 poller 提交请求。
- `STRIPE_SIZE = SECTOR_LEN = 4 KiB`，图的连续 4 KiB pages 已按 page round-robin 映射到不同设备，并非 Claude 假设的 512 KiB–4 MiB 大条带。
- 官方文档不仅报告 50/105-thread throughput，也给出单 search thread、I/O width 32 的 4× P5800X latency 数据。因此“PipeANN 只靠增加并发查询，单查询仍只用一盘”是事实错误。

### 架构与收益上界攻击

候选的延迟式 `O(hops × device_latency / devices)` 不成立。同一 hop 的并行 4 KiB reads 的关键路径近似各请求 service/queueing 的最大值；分散到多盘可降低排队，却不会把单个介质服务时间除以设备数。现代单块 NVMe 内部已能并行服务 beam requests，跳间依赖仍是 `hops × round latency`。

BFS 奇偶层着色也不能维护所声明的不变量：Vamana 不是二分图，同层、回边和长边普遍存在；实际候选集由 query distance、visited state 和 completion 顺序共同决定，不等于 BFS 层。要保证每个 data-dependent beam 跨盘，只能复制节点或按 query 动态搬迁，两者都引入空间/写放大。

最强简单 baseline 是 4 KiB page hash/round-robin/SPDK stripe。随机图页 LBA 已使一个 beam 的页面近似均匀分布；若 trace 仍有 collision，也应先和 node-ID hash 比较，而不是直接构造 graph-aware layout。Council 规定“最强 baseline 是普通通用技术”时自动 Kill，本候选命中该条。

### 当前环境攻击

服务器能看到多块 NVMe，但本项目明确可写的数据盘只有挂载到 `VectorDB/data` 的 `nvme8n1`。系统盘实际是 Samsung 870 SATA SSD，不是第二块可用于 gate 的 NVMe；`nvme6n1` 是 agent storage，其余多块为 XFS/raw/已有 RAID members，未经 PZ 明确分配不能覆盖、重格式化或绑定 SPDK。因此“系统盘 + 数据盘已有两块实验 NVMe”不成立，当前 gate 也不能安全实施。

### 最终边界

多盘问题本身真实，但当前 candidate 的问题模型、机制和 baseline 均不足，不建议改成一个小型 placement heuristic 后继续。

---

## 候选三：坐标漂移下的增量拓扑修复

### 裁决：REVISE（当前版本不进 Gate）

### 问题真实性

Embedding model migration 的重嵌入和重建成本真实。[HAKES](https://www.vldb.org/pvldb/vol18/p3049-ooi.pdf)（PVLDB 2025）明确指出模型重训后需要 rebuild；生产系统通常采用 shadow/blue-green index、dual write 和切流，而不是对十亿点逐个同步 delete+reinsert。

但 Claude 混合了两类不同问题：

1. 同一语义空间内少量 item coordinates 更新；
2. 新 embedding model 产生新的整体空间，甚至改变维度。

第二类通常不等价于在旧坐标上加独立 Gaussian noise。新旧空间可能整体旋转、非线性变形或维度不兼容；在迁移中混合 old/new vectors 会让距离失去统一语义。[Drift-Adapter](https://aclanthology.org/2025.emnlp-main.805/)（EMNLP 2025）和 [Query Drift Compensation](https://proceedings.mlr.press/v330/goswami26a.html)（PMLR 2026）已把“新 query 映射回旧 corpus space”作为零/低停机 baseline。Drift-Adapter 报告恢复 full re-embedding 的 95–99% retrieval recall，额外 query latency 低于 10 μs。

Claude 给出的“typical L2 drift 为平均 NN 距离的 5–30%”和“每周期 recall 下降 5–15%”没有一手证据，不能作为 gate 参数。

### 机制正确性攻击

`α-RobustPrune` 不是每条边可由一个永久 ratio 独立判断的谓词。某边是否保留取决于排序后的完整 candidate set、此前已选邻居及 pairwise dominance。单边 watermark 至少遗漏：

- 新空间中新出现但旧图不存在的必要边；
- incoming edges 的失效；
- 其他候选变化后同一边的选择状态变化；
- 局部 edge-valid fraction 与全局 navigability/recall 之间缺失的关系。

即使只校验现有 `N×R` edges，也已需要全图扫描；若所有 N 个 coordinates 都重嵌入，读取和发布新 vectors 本身不可省。`90% edges valid` 不能推出 90% recall，更不能保证搜索连通性。

### 必须补齐的 baseline

- 旧 graph + 全量新 coordinates，不修 topology；
- from-scratch shadow rebuild；
- warm-start graph rebuild/NN-descent refinement；
- 全量 delete-reinsert；
- Drift-Adapter/QDC（允许临时保留旧语义时）；
- HAKES 类快速 build/rebuild 系统。

### 建议的彻底改题

若保留，应改成 **“跨 embedding version 的 warm-start graph rebuild”**，而不是 edge watermark repair。第一阶段只能使用同一 corpus 在真实连续 model checkpoints 下的 paired old/new embeddings，重新计算新空间 ground truth，并回答：

1. 新旧 kNN graph overlap 是否足够高；
2. 旧 topology 在新 coordinates 下损失多少 recall；
3. 受影响节点/边是否局部，而非接近全图；
4. warm-start refinement 相对 fresh rebuild 能否少做显著工作并恢复同等质量。

Gaussian noise 只能作为敏感性附录。没有真实 paired embeddings 前，不运行 DGAI gate。若新旧 kNN overlap 很低、维度改变或需修复多数节点，应直接 Kill；只有局部 drift 在至少两个真实 model transitions 上复现，才值得重新申请 `PROVISIONAL`。

### 当前可实现性

DGAI 能实现合成坐标替换和局部 re-prune，但不能自动提供真实模型迁移证据。当前没有已确认的 paired checkpoint embedding 数据；下载模型并编码大 corpus 还可能引入 GPU/计算依赖。故当前 2–3 天估计不可信。

---

## 候选四：查询观测驱动的在线拓扑自愈

### 裁决：KILL

### 问题因果攻击

若 data 与 graph 不变，query distribution shift 不会使同一 query 的 recall/QPS “每月持续下降”。它只会立刻改变聚合 workload mix：更多请求落到原本较慢或较难的区域。这里的真实问题是 workload-aware optimization，而不是 topology 随查询时间腐化。

“被遍历但未进入最终 top-10”也不是 dead-end 的因果定义。长边或中间节点可能不在结果中，却是到达结果区域的必要路由桥；图搜索不是一棵拥有唯一 result path 的树。只有移除/替换边后的 counterfactual search 才能判断贡献，而这会支付候选试图避免的重搜索成本。

### Prior-art 与 baseline 攻击

- [Quake](https://www.usenix.org/conference/osdi25/presentation/mohoney)（OSDI 2025）直接针对 dynamic/skewed vector workload，按 query access frequency 与 partition size 建成本模型，在线 split/merge/refine index，并以 estimate–verify–commit 保证固定 workload 下成本单调收敛。
- [GATE](https://arxiv.org/abs/2506.15986)（2025 预印本）明确以 base/query distribution mismatch 为问题，学习 query-aware entry routing，在图索引上获得 1.2–2.0× speedup。
- [MARGO](https://www.vldb.org/pvldb/vol18/p4337-zheng.pdf)（PVLDB 2025）按 monotonic path importance 为边加权并优化磁盘布局；[CrackIVF](https://www.vldb.org/pvldb/vol18/p3951-mageirakos.pdf)（PVLDB 2025）也已建立 query-driven adaptive indexing 边界。
- LSM-VEC（2025 预印本）进一步把 query traversal pattern 纳入 connectivity-aware reordering/compaction。

这些工作不完全等于“在线改逻辑边”，但它们构成更强且更简单的 baseline。若 hot-page cache、query-specific entry points、workload-aware partition/refinement 或周期 workload-weighted rebuild 已恢复性能，修改逻辑拓扑没有系统必要性。

### Gate 攻击

- biased SIFT query 是合成 workload，不能支撑“每月退化”的生产叙事；Quake 已公开 Wikipedia pageview workload，应优先使用真实 trace。
- top-100 nodes 和 20% dead-end 均为任意阈值。
- “re-prune with biased neighbor set”可能把 query/ground-truth 信息泄漏进图构建，且没有定义如何维护全局 navigability。
- 修复 100 个节点后的 recall/QPS 变化无法区分 entry-point、cache 或 topology 的作用。

### 最终边界

候选关闭，不转成查询热度缓存、入口图或 query-driven physical layout；这些均已被现有工作覆盖。若未来研究 logical topology adaptation，必须先给出可计算的 edge counterfactual value 和真实 workload 下相对 Quake/GATE 的不可替代收益，当前材料没有做到。

---

## 给 Gpt 的建议

本轮不要为了保持节奏而放行一个廉价实验。候选一和四虽然容易 instrument，但测量对象已经被 prior art 或错误 proxy 否定；候选二虽有存储系统味道，但普通 4 KiB striping 是更强 baseline，且当前没有安全的第二项目盘。唯一值得保留的是候选三的**问题场景**，不是其机制：请退回 Claude/PZ，先决定是否愿意把方向改成真实 embedding-version migration / warm-start rebuild，再重新提交一份基于 paired embeddings 的假设和 gate。

本轮一手论文 PDF/文本解析约 4.9 MiB，全部位于 NVMe 的 `VectorDB/data/VectorDB/architecture_council/papers`；未修改 DGAI、未运行实验。
