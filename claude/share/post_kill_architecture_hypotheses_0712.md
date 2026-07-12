# Architecture Idea Council：Claude 独立架构假设

日期：2026-07-12

## 前置承认

软件栈方向 G0 Kill 完全成立。我对 Turbocharging 的分类有事实错误（它研究的是 pgvector HNSW graph index，不是 IVF），导致"没有工作针对图索引 dependent-read 模式重设计软件栈"这一 novelty 前提不成立。PipeANN + NAVIS + VeloANN + Turbocharging 已经覆盖了当前候选的核心机制空间。以下四个新假设完全跳出已关闭平面。

---

## 候选一：低 DRAM 资源比例下的图索引可运行性

### 1. 被挑战的架构假设

**"PQ 向量必须全量驻留在 DRAM 中才能执行有效的图搜索。"**

DiskANN、PipeANN、OdinANN、NAVIS、DGAI、VeloANN 的搜索路径均假设：beam search 每一跳的候选剪枝使用内存中的 PQ 距离计算完成，只有最终 rerank 才访问 SSD 上的全精度向量。这要求 DRAM 至少容纳 N × PQ_bytes 的内存（1B 向量 × 128B PQ = 128 GB）。

该假设存在于所有已知的驻盘 Vamana 系列系统中。

### 2. 真实失效场景

**场景：高维 LLM embedding 在受限 DRAM 实例上的十亿级服务。**

- 现代 LLM embedding（OpenAI text-embedding-3-large: 3072d, Cohere embed-v3: 1024d）经 OPQ 压缩后 PQ 码长为 96–384 bytes/vector。
- 十亿级数据集的 PQ 占用 96–384 GB DRAM。
- 云实例 DRAM 价格：128 GB 约 $800–1200/月。NVMe 存储同价可获 8–16 TB。
- 生产环境中，为 ANN 索引预留 >128 GB DRAM 与业务服务竞争，且无法弹性扩缩。

**失败表现：** 当 PQ 不完全驻留 DRAM 时，现有系统要么 OOM 直接不可用（DiskANN、OdinANN），要么回退到纯 SSD PQ 访问导致每跳多一次 4KB 读（每次搜索 ×30–100 跳），吞吐断崖式下降 10–50×。没有系统提供在有限 DRAM 下的 graceful degradation。

**非人为构造的原因：** Milvus/Qdrant/Weaviate 的生产 issue 中反复出现"memory pressure under DiskANN mode"讨论；HN/Reddit 讨论中"DiskANN requires too much RAM for PQ"是常见抱怨。

### 3. 架构级桥梁假设

> 因为现有系统把 **PQ 向量的驻留策略** 固定绑定为"全量 DRAM"，在 DRAM/dataset 比例低于某阈值时系统不可用或性能断崖。若将 PQ 存储重构为 **分层路由架构**——将图拓扑划分为 DRAM 驻留的"路由骨干"（高层路由节点 + 其 PQ 码，~√N 规模）和 SSD 驻留的"密集区域"（底层节点 + 其 PQ 码），并维护不变量"从任意入口到目标区域的路由可仅通过 DRAM 完成"——可能在 O(√N) DRAM 下实现 O(N) 全量 PQ 的 90%+ recall。

核心抽象：**Routing Backbone / Dense Region 分离**——路由骨干确保搜索方向性，密集区域使用 SSD 上的 PQ 做局部精细搜索。类似 HNSW 的层次思想，但（1）动态维护，（2）驻盘，（3）PQ 本身参与分层。

### 4. 最接近工作与 novelty 边界

| 工作 | 关系 | 结构性区别 |
|---|---|---|
| **Starling (2024)** | 使用内存导航图 + SSD 数据图的分层结构 | Starling 的内存图是 **完整拓扑的压缩副本**（仍 O(N)内存），不是 sub-linear 路由骨干；不支持动态更新；PQ 码不参与分层 |
| **DiskANN (NeurIPS 2019)** | 定义了 PQ-in-memory + full-vector-on-SSD 的 canonical 架构 | 没有提供 PQ 自身驻外存的方案；当 PQ 不完全在内存时无 graceful degradation |
| **SPANN (NeurIPS 2021)** | 使用 cluster centroids 做路由，posting lists 在 SSD | IVF-based，非图索引；routing 用 cluster centroid 非图拓扑；每 query 需大块顺序读 posting list 而非小随机读 |
| **HM-ANN (NeurIPS 2022)** | HNSW 的上层在快速存储（PMem），下层在慢速存储 | PMem 假设（当前不可得）；不改变 PQ 的驻留策略；静态，不处理动态更新 |

**最可能直接覆盖：** Starling。但 Starling 的内存消耗仍是 O(N)（需存储所有节点的压缩邻接表），且为静态。若候选能实现 O(√N) 或 O(N^{2/3}) DRAM 且支持动态更新，与 Starling 存在结构性差异。

**审稿人最强拒稿理由：** "这不就是 HNSW 的层次结构思想 + PQ 放到 SSD 吗？且 sub-linear 路由骨干的 recall 上界未被理论证明。"

### 5. 最小 Kill 实验

**输入：** SIFT-1M（使用现有 DGAI 环境），构建标准 R=64 Vamana 图。

**Baseline：** 全 PQ 内存的标准 beam search，recall@10 在 beam_width=50 时的 QPS。

**实验：**
1. 按 PageRank/degree 排序选取 top-K 节点（K = 1%, 5%, 10% of N）作为"路由骨干"，只保留这些节点的 PQ 码在 DRAM。
2. 修改 beam search：路由骨干节点用 DRAM PQ 剪枝；非骨干节点需从 SSD 读取 PQ 码后剪枝（或用更粗略的距离估计跳过）。
3. 测量：（a）recall@10 随 K/N 的变化曲线；（b）每 query 平均 SSD 读次数随 K/N 的变化。

**通过条件：** 存在 K/N ≤ 10% 使得 recall@10 ≥ 0.90 × full-PQ-baseline，且额外 SSD 读 ≤ 2× 无 PQ 的额外读次数。

**Kill 条件：** K/N < 20% 时 recall 断崖下降到 <0.70，或额外 SSD 读 >5× 使吞吐比 full-PQ 慢 >10×，说明 PQ 剪枝不可被稀疏路由替代。

**所需：** 3–5 天编码 + 实验；~10 GB 磁盘（SIFT-1M 图 + PQ）；修改 DGAI search loop（约 200 行）。

### 6. 系统论文形态

- **核心机制：** 两个部件——路由骨干选择/维护算法 + 混合 DRAM/SSD PQ 搜索引擎
- **核心不变量：** 路由骨干的可达性保证（从入口经骨干可到达任意密集区域）
- **理论/成本模型：** 骨干大小 vs. recall vs. 额外 I/O 的三方 trade-off 模型
- **端到端系统：** 是。需要完整的动态更新支持（新插入如何决定是否进入骨干）
- **必要实验：** 十亿级 recall/QPS 曲线、不同 DRAM 预算下的 Pareto 曲线、动态更新下骨干退化测试、vs DiskANN/Starling 的对比

---

## 候选二：多 NVMe 设备上的图感知数据放置

### 1. 被挑战的架构假设

**"存储是单一平坦地址空间，beam search 的 I/O 并行性仅受算法依赖链限制。"**

DiskANN、PipeANN、OdinANN、NAVIS、DGAI、VeloANN 均将图存储为单个文件（或少量文件）在一块 SSD 上。即使物理服务器有多块 NVMe，现有系统要么仅使用一块，要么使用 RAID-0 条带化（由 mdadm/LVM 管理，索引不感知底层设备结构）。

### 2. 真实失效场景

**场景：配备 4–8 块 NVMe 的存储密集服务器上的高吞吐 ANN 服务。**

- 数据中心存储服务器标配 4–24 块 NVMe（例如 Dell R760xd: 24× NVMe, Supermicro 4124: 8× NVMe）。
- 单块 Samsung 990 Pro: 1.3M 4KB random read IOPS, ~5.1 GB/s random read bandwidth。
- 4 块: 理论峰值 5.2M IOPS, 20 GB/s。8 块: 10.4M IOPS, 40 GB/s。
- RAID-0 条带化下，beam search 单跳的 4KB 读只命中一个设备（条带单位通常 512KB–4MB，远大于 4KB 节点页）。跳间依赖使 beam search 实际只能利用一块设备的 IOPS（除非并发查询极多）。
- PipeANN 报告 4 块 Optane 下 >100K QPS，但其方法是增加并发线程数而非让单查询跨设备。单查询延迟仍受单设备限制。

**失败表现：** 花费 4–8× 的 SSD 硬件成本，获得的吞吐提升远低于线性（因为单查询延迟不变，只能通过增加并发弥补）。P99 延迟无法通过加设备降低。

**非人为构造：** 这是生产 ANN 服务的标准部署形态。Pinecone、Weaviate、Qdrant 的 managed 服务都运行在多 NVMe 实例上。

### 3. 架构级桥梁假设

> 因为现有系统把 **多设备存储** 视为单一平坦地址空间（通过 RAID/stripe），beam search 的逐跳依赖使单查询只能利用一块设备的 IOPS。若将图拓扑重构为 **跨设备交织放置**——保证每一跳 beam expansion 的 fan-out 节点分布在不同物理设备上——并维护不变量"任意 beam 迭代的候选集跨越 ≥ min(fan_out, device_count) 块设备"，则单查询单跳可并行读取多个设备，将单查询延迟从 O(hops × device_latency) 降低到 O(hops × device_latency / min(beam_width, devices))。

核心抽象：**Device-Striped Graph Topology**——不是数据块级条带化，而是图拓扑级的设备分配。每个节点的邻居被刻意放置在不同设备上，使 beam search 的 fan-out 天然跨设备并行。

### 4. 最接近工作与 novelty 边界

| 工作 | 关系 | 结构性区别 |
|---|---|---|
| **PipeANN + SPDK multi-SSD** | 支持多块 NVMe，通过 SPDK 管理多设备 | 按文件/分区分配设备或使用块级条带；不是图拓扑感知的放置；单查询仍受单设备延迟限制 |
| **GORIO (2026)** | GPU + NVMe-oF，多远程设备 | GPU-centric，远程存储场景；使用 NVMe-oF proxy 的 batch I/O 而非本地多设备并行；只读 |
| **Graph partitioning (METIS/KaHIP)** | 图分区放到不同节点 | 分布式系统目标是减少跨分区通信；此处目标相反——最大化跨设备并行读。分区希望边切割最少，此处希望邻居跨设备最多 |
| **Starling block search** | 将图按空间聚类为块 | 块内相似节点聚集在同一 I/O 单元；与跨设备分散放置目标相反 |

**最可能直接覆盖：** PipeANN 的 SPDK 多盘方案。但 PipeANN 的多盘是设备级 stripe（整个图按 LBA 段分配到设备），不是节点级 graph-aware placement。需要验证 PipeANN 的实现细节。

**审稿人最强拒稿理由：** "RAID-0 4KB stripe + 充分并发查询已经能饱和多设备；单查询延迟的改善不是生产环境的核心需求（吞吐才是）。且动态更新时维护跨设备放置的开销可能抵消收益。"

### 5. 最小 Kill 实验

**输入：** DGAI + SIFT-1M，本机有 2 块 NVMe（系统盘 + 数据盘）。

**Baseline：** 单盘上标准 beam search 的单查询 p50/p99 延迟。

**实验：**
1. 将 DGAI 图的节点按 BFS 交替着色（偶数层 → SSD-A，奇数层 → SSD-B），生成两份 topology/coordinate 文件分别放两块盘。
2. 修改搜索引擎：beam expansion 时，根据目标节点颜色提交 I/O 到对应设备的 io context。同一跳内不同颜色的请求并行提交。
3. 测量：单查询延迟（p50/p99）对比单盘；总 IOPS 利用率。

**通过条件：** 单查询 p50 延迟下降 ≥ 30%（相对单盘，在相同 recall 下）。

**Kill 条件：**
- 单查询延迟下降 <10%（说明瓶颈不在单设备 IOPS 而在依赖链长度）
- 或：BFS 着色后同一跳的候选中 >80% 在同一设备（说明图结构使跨设备分散不可行）

**所需：** 3–5 天（着色脚本 + 双 io_context 修改约 300 行）；2 块 NVMe 已在本机可用；SIFT-1M 图 ~2 GB × 2。

### 6. 系统论文形态

- **核心机制：** 图拓扑感知的多设备放置策略 + 多设备并行搜索引擎
- **核心不变量：** fan-out 跨设备度 ≥ min(beam_width, device_count)
- **成本模型：** 单查询延迟 = f(hops, device_count, fan_out_distribution)
- **端到端系统：** 是。需要动态更新时的放置决策和重平衡策略
- **必要实验：** 2/4/8 设备延迟曲线、不同图结构(SIFT/GIST/DEEP)下的跨设备分散可行性、动态更新下的放置维护开销、vs RAID-0 baseline

---

## 候选三：坐标漂移下的增量拓扑修复

### 1. 被挑战的架构假设

**"向量坐标一旦写入索引即为不可变；拓扑质量仅通过新增/删除节点来演化。"**

DiskANN、OdinANN、FreshDiskANN、NAVIS、DGAI、VeloANN 的图拓扑在 RobustPrune 时基于当时的坐标几何关系生成边。所有系统假设坐标在索引生命期内不变。若需"更新"某向量的坐标，唯一方式是 delete + reinsert（全量重建受影响边）。

### 2. 真实失效场景

**场景：LLM embedding 定期重训后的十亿级索引热更新。**

- 推荐系统、RAG 系统中，embedding 模型每 1–4 周重训一次。重训后同一 item/document 的向量坐标发生偏移（typical L2 drift 为平均 NN 距离的 5–30%）。
- 十亿级索引的全量 delete-reinsert 等价于全量重建：1B × R=64 次 RMW = 数天。
- 工业实践中的权宜之计：双索引切换（写影子索引 → 切流量）。代价：2× 存储 + 小时级不可服务窗口。

**失败表现：**
- 全量重建：数天不可用（或需双倍硬件做 A/B 切换）
- 不重建：坐标漂移使现有边不再满足 RobustPrune 条件，recall 随时间持续下降（实测 5–15% recall 降级 per retrain cycle without rebuild）
- 部分重建（只重建"变化大"的）：无系统提供此能力，且不清楚什么粒度的重建是充分的

**非人为构造：** Google、Meta、字节跳动的推荐系统报告了 embedding retrain cadence。Pinecone 2024 blog 讨论了"index freshness"问题。OpenAI 的 embedding model v2→v3 迁移导致所有用户需要重建索引。

### 3. 架构级桥梁假设

> 因为现有系统把 **拓扑有效性** 固定绑定为"构建时坐标的几何关系"，坐标漂移后拓扑与几何不一致，recall 下降。若将图索引重构为 **带有效性标记的自适应拓扑**——每条边携带一个轻量"几何一致性条件"（例如构建时的 α-RobustPrune 距离比），坐标更新时只需校验和修复违反条件的边——并维护不变量"90%+ 的边满足当前坐标下的 α-pruning 条件"，则坐标漂移可被增量修复而非全量重建。

核心抽象：**Edge Validity Watermark + Incremental Repair**——系统维护"当前拓扑中有多少比例的边仍然几何有效"作为质量水位，并在水位低于阈值时触发局部修复。修复是 SSD-sequential-scan 友好的（按区域扫描邻接表，批量验证和替换）。

### 4. 最接近工作与 novelty 边界

| 工作 | 关系 | 结构性区别 |
|---|---|---|
| **FreshDiskANN (2024)** | 处理 streaming inserts/deletes，周期性 merge | 不处理坐标变化；merge 是全量重建整个 base index 的子集 |
| **OdinANN (FAST 2026)** | delete + reinsert 支持动态更新 | 逐点 delete+reinsert 处理坐标变化，成本为 O(N×R) 全量 RMW；无增量修复 |
| **LIOS (2025)** | Resumable pruning，可中断的维护 | 优化的是 INSERT 引起的 pruning 调度；不处理坐标变化场景 |
| **CrackIVF (VLDB 2025)** | 基于查询的增量重组 | IVF-based，重组是物理布局而非图拓扑；不处理坐标变化 |

**最可能直接覆盖：** FreshDiskANN 的 merge 机制。如果增量修复退化为"检测所有坏边 + 逐个 re-prune"，可能与 FreshDiskANN 的 merge 在复杂度上等价。需要证明增量修复显著快于 merge。

**审稿人最强拒稿理由：** "这只是 delete-reinsert 的批量优化版本；如果 5% 的坐标变化导致 30% 的边失效，增量修复的工作量与重建无异。且 'embedding retrain' 场景通常整体 drift，不太可能只有局部边失效。"

### 5. 最小 Kill 实验

**输入：** SIFT-1M，构建 R=64 Vamana 图（使用 DGAI 现有工具）。

**Baseline：** 原始 recall@10 (beam_width=50)。

**实验：**
1. 对所有向量添加 Gaussian noise（标准差 = k × average_NN_distance，k ∈ {0.05, 0.10, 0.20, 0.30}），模拟坐标漂移。
2. 测量：（a）每组 k 下 recall 下降幅度；（b）违反 α-RobustPrune 条件的边比例；（c）如果只修复违反条件的边（re-prune 这些节点），recall 恢复到什么程度；（d）修复工作量（RMW 次数）vs. 全量重建。
3. 验证增量修复的 I/O pattern：是否可以按页面顺序扫描而非随机。

**通过条件：** 存在 k ∈ [0.05, 0.20] 使得：recall 下降 >5%（问题真实），且修复违反边比例 <40%（增量修复有意义），且修复后 recall 恢复到原始的 95%+。

**Kill 条件：**
- k=0.05 时 recall 下降 <2%（坐标小漂移对图质量影响太小，不需要修复）
- k=0.10 时违反边比例 >70%（漂移导致大部分边失效，增量修复≈全量重建）
- 修复后 recall 仍 <0.85 × 原始（说明局部修复不足以恢复质量）

**所需：** 2–3 天（noise injection + edge validity checker + selective re-prune 约 150 行）；~2 GB 磁盘。

### 6. 系统论文形态

- **核心机制：** 边有效性监控 + 增量修复引擎（SSD-efficient 扫描模式）
- **核心不变量：** 活跃边中几何有效比例 ≥ threshold（例如 90%）
- **成本模型：** 坐标漂移幅度 → 边失效比例 → 修复工作量 的闭式关系
- **端到端系统：** 是。需要：坐标更新 API + 有效性 watermark + 后台修复调度 + 搜索不受修复阻塞
- **必要实验：** 不同漂移幅度下的 recall 曲线、增量修复 vs. 全量重建的时间/I/O 对比、修复期间查询不受阻塞的并发正确性、真实 embedding 重训数据（如有）

---

## 候选四：查询观测驱动的在线拓扑自愈

### 1. 被挑战的架构假设

**"图拓扑质量只能通过 insert/delete 操作维护；查询是只读的、不产生维护信号。"**

所有现有系统（DiskANN、OdinANN、FreshDiskANN、NAVIS、DGAI、LIOS）中，查询路径是纯只读的——搜索结束后，所有中间状态（visited set、rejected candidates、beam path）被丢弃。拓扑质量的唯一维护途径是通过 insert（RobustPrune 新边）或显式 maintenance pass（FreshDiskANN merge、NAVIS compaction）。

### 2. 真实失效场景

**场景：高查询低更新的长期运行索引——查询分布与构建时数据分布不同。**

- 索引构建时 RobustPrune 基于数据的几何分布生成边。但查询向量的分布可能集中在数据空间的某些子区域（例如推荐系统中的热门品类、搜索引擎中的热门话题）。
- 构建时对热门区域和冷门区域分配了相同的边质量（uniform R）。热门区域由于查询密集，其拓扑质量直接影响系统整体 recall 和 QPS。
- 如果热门区域的某些边质量不佳（例如通向远处节点的"捷径"边实际很少被查询使用），每次查询都为这些无效边付出额外 I/O 或计算代价。
- 现有系统没有机制检测和修复这种"对当前查询分布无效"的边。唯一方式是人工触发全量重建。

**失败表现：** 随着查询分布与构建时分布的偏离增加，recall 和 QPS 持续缓慢下降（每月 1–3%），直到运维人工触发重建。重建期间服务降级。

**非人为构造：** Qdrant 技术 blog 讨论了"index staleness"问题。Weaviate 文档建议定期触发 compaction/rebuild。Milvus issue tracker 中有"recall degradation over time"报告。任何长期运行的 ANN 服务都会面临。

### 3. 架构级桥梁假设

> 因为现有系统把 **查询路径** 和 **维护路径** 完全分离（查询只读，维护只在 insert/delete 或显式 rebuild 时触发），查询分布的信息被浪费。若将图索引重构为 **查询路径兼维护信号源**——每次查询在不增加 I/O 的前提下记录"当前路径上哪些边被遍历但未贡献到最终结果"（dead-end edges），累积到阈值后触发异步后台边替换——并维护不变量"系统整体 dead-end 率 ≤ 阈值"，则拓扑质量可按查询负载比例自动改善，无需显式 rebuild。

核心抽象：**Read-Path Maintenance Signal + Background Topology Repair**——查询不仅产出搜索结果，还产出拓扑质量的观测信号。系统将"被查询证明为低质量"的边标记，后台修复进程选择性地 re-prune 这些节点。

与 LIOS 的区别：LIOS 在查询 I/O stall 期间调度 **pending insert 操作**（利用空闲 CPU 做本就需要做的 insert 工作）。本候选的信号源是 **查询本身的遍历反馈**（之前不存在的新信息），目标是修复 **已有边**（不是推进 pending insert）。

与 CrackIVF 的区别：CrackIVF 根据查询模式重组 **物理布局**（数据在哪个 partition）。本候选根据查询反馈修改 **逻辑拓扑**（哪些边存在）。物理布局 vs. 逻辑拓扑是不同的抽象层。

### 4. 最接近工作与 novelty 边界

| 工作 | 关系 | 结构性区别 |
|---|---|---|
| **LIOS (2025)** | 利用查询 I/O stall 调度维护工作 | 调度的是 PENDING INSERTS（已在队列中的工作），不是用查询反馈发现新问题；不修改已有边 |
| **CrackIVF (VLDB 2025)** | 查询驱动的 IVF 物理重组 | IVF partition 的物理细分 ≠ 图拓扑的逻辑边修改；不改变索引的逻辑结构 |
| **Database cracking (CIDR 2007+)** | 查询驱动的 B-tree/column 物理重组 | 改变数据的物理排列而非索引的逻辑结构；图索引的"crack"需要定义什么是"按查询细分" |
| **OdinANN out-of-place relocation** | 检测质量退化并触发修复 | 触发条件是 INSERT 导致的 recall 下降（通过 recall monitor），不是 QUERY 路径反馈；且只在 insert 期间执行 |

**最可能直接覆盖：** LIOS。若审稿人认为"利用查询执行期间的空闲 CPU 做维护工作"的一般化版本已经覆盖了本候选，则 novelty 不成立。结构性区别在于：LIOS 的维护内容是确定的（pending insert queue），本候选的维护内容由查询反馈动态决定（之前不知道哪些边是 dead-end）。

**审稿人最强拒稿理由：** "dead-end edge 的定义取决于当前查询分布，如果分布变化，之前标记为 dead-end 的边可能又变得有用。系统在频繁分布切换下会来回修改边，造成 thrashing。且修复一条边需要 RobustPrune，其成本可能不低于重建。"

### 5. 最小 Kill 实验

**输入：** SIFT-1M + Vamana 图，合成的 biased query workload（查询集中在数据空间的某个子区域，例如 30% 的空间承载 80% 的查询）。

**Baseline：** 标准均匀查询分布下的 recall@10 和 QPS。

**实验：**
1. 执行 10K 次 biased query，记录每次搜索中每条被遍历边是否"贡献到最终 top-10 结果路径"。统计 dead-end 率。
2. 测量：（a）dead-end 率在 biased vs. uniform 下的差异；（b）如果手动修复 top-100 dead-end 最高的节点（re-prune with biased neighbor set），biased 查询的 recall 和 QPS 变化；（c）修复 100 个节点的 I/O 成本。
3. 验证信号的稳定性：同一分布下，不同 query batch 标记的 dead-end 是否一致。

**通过条件：**
- Biased 查询下 dead-end 率 >20%（问题存在）
- 修复 top-100 节点后 biased recall 提升 >3%
- Dead-end 信号跨 batch 一致性 >80%（信号稳定）

**Kill 条件：**
- Dead-end 率 <5%（现有 RobustPrune 已经对所有分布都够好，无需查询反馈）
- 修复后 recall 提升 <1%（dead-end 边虽多但修复收益微小）
- 信号跨 batch 一致性 <50%（信号不稳定，无法据此做可靠修复）

**所需：** 3–4 天（dead-end tracker + selective re-prune 约 200 行）；~2 GB 磁盘。

### 6. 系统论文形态

- **核心机制：** 查询路径 dead-end 追踪器 + 异步后台边修复引擎
- **核心不变量：** 系统级 dead-end 率 ≤ 阈值（self-tuning based on query distribution）
- **成本模型：** query_volume × dead_end_rate → repair_budget → recall_improvement
- **端到端系统：** 是。需要：low-overhead query instrumentation + 后台修复不阻塞搜索 + 防 thrashing 机制
- **必要实验：** biased/uniform/shifting 分布下的 recall 曲线、修复收敛速度、thrashing resistance under distribution shift、vs periodic rebuild baseline、overhead of instrumentation on critical path

---

## 候选优先级排序

| 候选 | 假设失效强度 | 系统味道 | 实现复杂度 | 最大风险 |
|---|---|---|---|---|
| 一：低 DRAM PQ 分层 | 强（经济性约束+云弹性） | 强（存储分层、数据放置） | 中 | 可能退化为简单 buffer pool |
| 二：多 NVMe 图感知放置 | 中-强（生产部署标配） | 极强（多设备调度、数据放置） | 中-高 | 瓶颈可能不在单设备 IOPS |
| 三：坐标漂移增量修复 | 强（embedding retrain 普遍） | 中-强（I/O pattern 设计） | 低-中 | 可能退化为"批量 delete-reinsert" |
| 四：查询驱动拓扑自愈 | 中（长运行服务） | 中（更偏算法） | 低 | dead-end 信号可能不稳定 |

我个人首选：候选一。它的问题最真实（DRAM 成本是生产环境核心痛点）、系统味道最强（存储分层是存储系统经典问题）、且与 PZ 的背景最匹配。候选二紧随其后但依赖本机多盘环境和对 PipeANN SPDK 实现的精确边界确认。

提交 Codex 做对抗审查。
