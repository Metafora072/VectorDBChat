# PQ-Free SSD Exact Navigation 立项前预检

## Prior-art 边界

候选要同时主张两件事：不在 DRAM 保留 `O(N)` per-vector PQ，以及在图遍历期间用从 SSD 读取的 full-precision vector 做 exact navigation。审计后，这两部分分别已被现有工作逼近，二者之间只剩一个尚未证明的 I/O 交换假设，而不是一个已经定义的新机制。

- **AiSAQ 是内存目标的最强直接反例。** AiSAQ 把当前节点所有出邻居的 PQ code 与 full vector、neighbor IDs 一起写入 node chunk；搜索只需保留入口点和当前 hop 的至多 `R + n_ep` 个 PQ code。它在 SIFT1B 上把 DiskANN 的约 31,303 MB 查询内存降到 11 MB，并保持同图、同参数下相同 recall。其关键点不是额外随机读取 neighbor PQ，而是从当前 node chunk 一次取得邻居 ID 与 PQ code；当扩大的 chunk 仍落在相同 4 KiB 块数内时，请求数不增加。[AiSAQ](https://arxiv.org/abs/2404.06004)
- **PageANN 已覆盖 page-node、相似向量聚页、页内 full-vector exact distance 和 page-to-page traversal。** PageANN 将相似向量聚为 page node，每个逻辑 page node 对齐一个物理 SSD page；读取页面后，对页内所有 full vectors 计算 exact distance。但它用压缩的邻页代表向量估计距离来决定跨页候选，exact distance 进入 result set，而不是完全取代跨页 compressed control plane。因此它不是候选的逐字等价实现，却覆盖了候选最可陈述的结构；候选唯一剩余 delta 是删除 PageANN 的跨页压缩估计并先读取候选 full-vector pages。[PageANN](https://arxiv.org/abs/2509.25487)
- **VeloANN 覆盖层次压缩、相似记录 co-placement 和 page reuse。** 它用 1-bit 基码做初筛、扩展码做精化，以 affinity 而非仅图邻接把可能共同遍历的 records 放入同页，并采用 record buffer、prefetch 和 cache-aware beam search。它明确保留压缩导航层；高维下甚至观察到一条 record 占满一页，说明 co-location 收益随维度下降。[VeloANN](https://arxiv.org/abs/2602.22805)
- **SkipDisk 不是 PQ-free 目标的替代答案。** 它把邻接留在内存，并为每个点保留 PCA/BF16 剪枝后的表示、专属 pivot/lower bound 等 `O(N)` summary，再以 full-vector SSD read 验证未过滤候选。它证明“低内存过滤”仍依赖 per-point control plane，而不是证明无 summary 的 exact navigation 可行。[SkipDisk](https://arxiv.org/abs/2605.05787)
- **OctopusANN、Starling、DiskANN++ 的共同方向是先减少路径或提高页局部性，再保留廉价候选分数。** OctopusANN 的最佳组合仍是 `PQ + MemGraph + PageShuffle + PageSearch + DynamicWidth`；Starling 用内存导航图、重排磁盘图和 block search；DiskANN++ 用 query-sensitive entry、isomorphic mapping 和 page search。这些工作没有提供“先读所有候选 full vectors”优于压缩控制面的证据。[OctopusANN](https://arxiv.org/abs/2602.21514)、[Starling](https://arxiv.org/abs/2401.02116)、[DiskANN++](https://arxiv.org/abs/2310.00402)
- **GateANN 给出相反的系统分解。** 它明确把 traversal 所需信息压缩为 neighbor list 与 approximate distance，使不匹配节点无需读取 full-precision vector；这与本候选用 full-vector read 取代 control plane 的方向相反。[GateANN](https://arxiv.org/abs/2603.21466)
- RaBitQ/AQR-HNSW 仍是 `O(N)` 量化表示；把 PQ 改名为 binary code、lower bound、representative 或 adaptive quantization 不满足候选边界。[RaBitQ](https://arxiv.org/abs/2405.12497)、[AQR-HNSW](https://arxiv.org/abs/2602.21600)

由此，最接近 prior art 不是一篇完全等价论文，而是 **AiSAQ 的 `O(N)` PQ 消除 + PageANN 的 page-node/页内 exact**。唯一未覆盖部分是“完全删除跨页 compressed routing，先读 full-vector page 再决定 frontier”。当前没有新的 page topology、eligibility rule、packing guarantee 或 I/O scheduling 机制支撑这一差异；它只能被视为待证伪的 finding hypothesis，不能作为方法 novelty。独立审稿复核也得出相同判断。

## PQ 在现有 search loop 中承担的精确作用

本地 DiskANN `PQFlashIndex::cached_beam_search()` 的真实控制流如下：

1. 查询先生成每个 PQ chunk 的查表距离；`compute_dists(ids)` 从 DRAM 的 `N × M` PQ table 聚合目标 ID 的 codes，并计算 approximate distances。
2. 入口点以 PQ distance 插入 `retset`。每轮从 `retset.closest_unexpanded()` 弹出最小 PQ-distance 节点，beam 中这些节点才触发 SSD node-record read。
3. 读回 expanded node 后，系统对该节点 full vector 计算 exact distance并放入 `full_retset`；但 `retset` 中用于 frontier order、beam selection 和 termination 的键仍是原 PQ distance，exact distance 不回写导航队列。
4. 当前节点的所有新邻居继续由 `compute_dists()` 用 PQ 排序并插入 `retset`。搜索结束后，`full_retset` 才按 exact distance 返回 top-k；必要时还会对候选做独立 full-vector rerank read。

因此 PQ 是 **I/O admission/control plane**，不只是结果压缩：它以 `M` bytes/neighbor 的顺序内存访问，决定哪些 node records 值得形成随机 SSD reads。删除它后，若没有另一种候选界，系统必须在排序前先取得 full vectors。

AiSAQ 将这项控制面从 DRAM 移入当前 node chunk。设 full vector 为 `b_full` bytes、PQ code 为 `M` bytes、degree 为 `R`，DiskANN record 约为 `b_full + 4(R+1)`，AiSAQ record 约为 `b_full + 4 + R(4+M)`。以 `R=64, M=32` 为例，AiSAQ 的邻居控制面仅增加 2,048 bytes；128D/384D float32 的整个 record 理论上仍分别约 2,820/3,844 bytes，可落在一个 4 KiB read 中。相比之下，读取 64 个邻居 full vectors 的净 payload 已是 32/96/240 KiB，尚未计对齐、页头和重复页面。

## 四种策略的 trace simulation 设计

现有查询日志只含每个 `L` 的 mean I/O、latency、recall；现有 DGAI formal trace 虽含 `expanded_nodes`、`PQ evaluations`、iterations 和 aggregate I/O，却没有逐 expansion 的 neighbor IDs、PQ/exact distances、frontier snapshots 与 vector-page mapping。故它们不能直接重放 P0–P3。本阶段不伪造结果；若只为留存负向边界，所需 measurement-only trace 如下。

每条 query 记录 query ID、`L/beam/M`、每轮 frontier、弹出的 expanded IDs、邻接 IDs、新访问信号、每个候选 PQ 与 exact distance、入队/淘汰/终止原因、node/vector physical page、cache state、最终 top-k 与 ground truth。所有策略使用相同 graph、entry、visited 规则和 I/O cache 容量；在固定 Recall@10 上分别调 `L`，并加入增加 PQ code length 和普通增大 `L` 的对照，不能固定参数后宣称 exact 更准。

- **P0：DRAM PQ。** 完全重放 DiskANN；DRAM 为 `M bytes/vector`，neighbor PQ lookup 不计 SSD read，expanded record read 和最终 rerank 分开计数。
- **P1：AiSAQ-style SSD PQ。** 路径和 P0 应在相同数值精度下完全一致；DRAM per-vector 为 0，当前 expanded record 同时带回 neighbor PQ。按实际 record length 向 4/8 KiB 对齐，不能把 SSD PQ 当成额外随机 neighbor read。
- **P2：exact-all-neighbor。** expanded node 暴露一批首次发现邻居后，只有其 full vector page 完成读取并算出 exact distance，邻居才可进入 frontier。维护 query-local page cache，报告 requested vectors、unique pages 和重复命中；不得用事后 PQ 顺序预筛 exact reads。
- **P3：exact-page。** 仅当某个已发现邻居指向页面时，该页才 eligible；读页后计算所有 resident vectors 的 exact distance。保守主口径只允许图上已发现的 resident IDs 入 frontier，其余 exact scores 仅形成 cache benefit；“页内任意 resident 可直接入 frontier”会改变图语义，只能作为 page-node oracle 单列。

P3 使用四种 layout：原始 ID/record mapping；每个 expansion 独立取 `ceil(new_neighbors/capacity)` 的理想容量下界；基于 Vamana graph proximity 的静态、容量约束 packing；使用未来 query co-visit hyperedges 的容量约束 oracle packing。后两者必须固定 mapping 后重放；query oracle 不得进入可实现结论。更新审计额外报告插入后 page occupancy、split/repacking bytes 和 locality decay，任何依赖周期性全局 repacking 的收益都判无效。

统一输出：DRAM bytes/vector、full-vector reads/query、unique 4/8 KiB pages、bytes/query、expanded nodes、iterations/dependency depth、每跳 eligible pages、PQ/exact rank inversion、真正改变后续 expansion 的 inversion、Recall@10–page 曲线，以及 fixed Recall@10 下相对 P0/P1 的 page ratio。高并发上界同时受 `min(device_IOPS/pages_per_query, bandwidth/bytes_per_query, CPU/exact_ops_per_query)` 限制；单查询 latency 则按 dependency depth 上的串行 page rounds 估算，不能用 SSD 峰值带宽掩盖依赖链。

## 三种维度的 page-capacity 分析

以下采用 gate 指定的 float32，并先给完全不含元数据的最乐观上界：

| 维度 | full vector | 4 KiB raw capacity | 8 KiB raw capacity | R=64 首跳 exact-page 最少 4 KiB pages |
|---:|---:|---:|---:|---:|
| 128D | 512 B | 8 | 16 | 8 |
| 384D | 1,536 B | 2 | 5 | 32 |
| 960D | 3,840 B | 1 | 2 | 64 |

最后一列是假设 64 个邻居被完美连续 packing、没有任何 page metadata 的 optimistic lower bound；原始随机 layout 可接近 64 页。若 page node 还需一个 8-byte header 与 64 个 4-byte neighbor/page IDs，4 KiB 可用 3,832 bytes，容量下降为 7/2/0：960D 的一个 vector 加最小 topology 已超过 4 KiB，必须把 topology 分页或改用至少 8 KiB。8 KiB 下同口径也只有 15/5/2。

这直接给出 exchange-rate 门槛。P0/P1 在一个 expanded record 内即可给 64 个邻居排序；P3 首跳即需最乐观 8/32/64 个 4 KiB candidate pages，随后才能决定下一次 expansion。即使这些页日后部分转化为 expanded-page 命中，384D/960D 也必须把后续 expansions 减少一个数量级才可能打平；960D 没有实质 page amortization。128D 尚有 8-way 上界，但“相似向量聚页 + 页内 exact”正是 PageANN 的核心结构，且 AiSAQ 在 `M=32` 时可用单个约 2.8 KiB record 完成同一批邻居的导航评分。

## 最强 baseline

内存目标的最强 baseline 是 **P1/AiSAQ**，不是原始 DiskANN：它已经把 per-vector DRAM 从 `M` bytes 降为 0，并把 neighbor PQ 顺带放进当前 record。page-structure 的最强 baseline 是 **PageANN**；吞吐/布局还应包含 VeloANN 与 OctopusANN。精度目标必须对比 P0/P1 的 PQ code length 与 `L` sweep。候选只有同时胜过 AiSAQ 的内存/I/O、PageANN 的 page-node 路径以及 tuned-PQ 的 fixed-recall 曲线，才存在继续理由。

## 预计实验成本

若只保留一次负向 trace audit，预计需约 150–250 行 measurement-only instrumentation 和一个离线 replay/packing 工具；每个维度先取 200–500 queries。按约 160 expansions、64 neighbors 估计，三组会产生约 6–15 million edge events，压缩 trace 约数百 MiB 到 1 GiB，离线四策略 sweep 为小时级。SIFT/GIST 与现有索引可复用；384D 数据已有 100K embedding，但若要求与 900K/1M 同规模一致还需另建索引。本轮没有运行这些实验。未来若经上层特批，所有 trace/index 必须写入 NVMe 的 `VectorDB/data/VectorDB/`，不得写系统盘。

## 结论：Kill

该候选在立项前即命中 Kill 条件：

1. “去掉 DRAM 全量 PQ”的内存目标已被 AiSAQ 以约 11 MB、通常无需额外 neighbor request 的方式实现；读取完整邻居向量的 I/O 更高。
2. PageANN 已覆盖 page-node、相似向量聚页、page traversal 与页内 exact distance；候选剩余差异只是删掉跨页 compressed estimate，并没有新的可陈述机制。
3. 最乐观容量上界已从 128D 的 8 vectors/page 降到 384D 的 2 和 960D 的 1；计 topology 后 960D 甚至无法形成单页 page node。多维度通用收益不成立。
4. 独立模型审稿认为剩余 delta 只是待验证 finding，而非方法 novelty；VeloANN、GateANN、OctopusANN 等也共同保留廉价 compressed control plane。

因此不进入正式 trace、不实现 page graph、不交 Claude 补架构。若未来出现一个与 PageANN 明确不同、能在不引入 `O(N)` summary 的前提下保证跨页 candidate amortization 的新机制，应作为新 idea 重新过 G0，而不是恢复本候选。
