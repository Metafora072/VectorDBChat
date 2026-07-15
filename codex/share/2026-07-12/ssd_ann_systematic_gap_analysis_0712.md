# 2023–2026 驻盘图 ANN 系统化 Gap Analysis

日期：2026-07-12（检索截止）

## 1. 范围、方法与证据等级

本报告执行 Claude 所建议的路径一：先建立 `(问题, 机制, 系统)` 覆盖矩阵，再从矩阵空格反查 prior art，不从预设机制出发找题。

核心纳入标准为：2023–2026 年公开论文；ANN 主路径使用 proximity graph，且 raw vector、graph、compressed routing data 中至少一项位于 SSD、远端内存或外存层。DiskANN 与 FreshDiskANN 虽早于时间窗，作为所有系统的基础 baseline 保留。纯 IVF/cluster、纯内存 HNSW、GPU-only、PIM-only 工作不进入核心矩阵，但在其已经覆盖某个问题时作为边界反例。

证据按以下优先级使用：正式会议/期刊论文 > 作者公开 preprint > 官方代码/文档 > 2026 年统一实验研究。产品文档只用于判断工程边界，不用于论文 novelty。检索覆盖本地 10 篇全文、2026 年 [Disk-Resident Graph ANN Search 统一实验研究](https://arxiv.org/abs/2603.01779)的 reference graph，以及 arXiv、PVLDB、SIGMOD、USENIX 站点的补充搜索。该清单追求高覆盖，但不声称对尚未公开或未被索引的论文数学完备。

状态缩写：`P` 表示同行评审正式论文，`A` 表示公开 preprint；`核心` 表示直接纳入驻盘图 ANN，`边界` 表示解决相同系统问题但索引或存储形态不同。

## 2. 系统目录

### 基础 baseline

| 系统 | 年份/状态 | 问题 | 核心机制 |
|---|---|---|---|
| [DiskANN](https://proceedings.neurips.cc/paper/2019/hash/09853c7fb1d3f8ee67a61b6bf4a7f8e6-Abstract.html) | 2019/P | billion-scale 单机搜索 | Vamana + DRAM PQ + SSD coupled node records |
| [FreshDiskANN](https://arxiv.org/abs/2105.09613) | 2021/A | streaming insert/delete | memory delta graph + periodic merge，实时更新静态 SSD graph |

### 2023–2024

| 系统 | 年份/状态 | 问题 | 核心机制 | 范围 |
|---|---|---|---|---|
| [LM-DiskANN](https://par.nsf.gov/biblio/10539353) | 2023/P, IEEE BigData | low-memory dynamic disk graph | neighbor routing/PQ data 下沉 node record，支持 insert/delete | 核心 |
| [DiskANN++](https://arxiv.org/abs/2310.00402) | 2023/A | 长入口路径与冗余页读 | query-sensitive entry、isomorphic mapping、PageSearch | 核心 |
| [Starling](https://arxiv.org/abs/2401.02116) | 2024/P, SIGMOD | segment 内 I/O 路径与页利用 | sampled navigation graph、graph-aware reorder、block search | 核心 |
| [AiSAQ](https://arxiv.org/abs/2404.06004) | 2024/A | `O(N)` PQ DRAM | 每个 node chunk 携带 neighbor PQ，查询约 10 MiB 内存 | 核心 |
| [SmartANNS](https://www.usenix.org/conference/atc24/presentation/tian) | 2024/P, ATC | multi-SmartSSD 扩展 | host + SmartSSD hierarchical index、near-data processing | 边界 |
| [Second-Tier Memory ANNS](https://arxiv.org/abs/2405.03267) | 2024/A | SSD 粗粒度 I/O 与索引放大 | RDMA/CXL second-tier memory 专用 graph/cluster layout | 边界 |
| [Curator](https://arxiv.org/abs/2401.07119) | 2024/A | multi-tenant index sharing | tenant-specific trees 压入共享 clustering tree | 边界 |

### 2025

| 系统 | 年份/状态 | 问题 | 核心机制 | 范围 |
|---|---|---|---|---|
| [PipeANN](https://www.usenix.org/conference/osdi25/presentation/guo) | 2025/P, OSDI | best-first 依赖与 SSD 不匹配 | I/O-driven pipeline、dynamic width、SPDK multi-SSD | 核心 |
| [FusionANNS](https://www.usenix.org/conference/fast25/presentation/tian-bing) | 2025/P, FAST | CPU/GPU/SSD 协同 | multi-tier filtering、heuristic rerank、I/O dedup | 边界 |
| [Turbocharging Vector Databases](https://www.vldb.org/pvldb/vol18/p4710-do.pdf) | 2025/P, PVLDB | pgvector HNSW 页读与构建 | io_uring、insertion reorder、locality colocation | 核心 |
| [HAKES](https://www.vldb.org/pvldb/vol18/p3049-ooi.pdf) | 2025/P, PVLDB | build、并发读写与分布式扩展 | compressed filter/refine、learned tuning、disaggregated service | 边界 |
| [Quake](https://www.usenix.org/conference/osdi25/presentation/mohoney) | 2025/P, OSDI | dynamic/skewed workload | query-aware split/merge、recall estimation、NUMA execution | 边界 |
| [PageANN](https://arxiv.org/abs/2509.25487) | 2025/A | page granularity 与低内存 | page-node graph、页内 exact、compressed inter-page routing | 核心 |
| [BAMG](https://arxiv.org/abs/2509.03226) | 2025/A | graph 与 block layout 脱节 | block-aware monotonic graph、decoupled layout、block-first search | 核心 |
| [Gorgeous](https://arxiv.org/abs/2508.15290) | 2025/A | cache/layout 未区分 graph 与 vector | adjacency-prioritized cache、复制邻居 adjacency 的 disk block | 核心 |
| [MARGO](https://www.vldb.org/pvldb/vol18/p4337-zheng.pdf) | 2025/P, PVLDB | disk layout 与真实导航路径脱节 | monotonic-path edge importance + graph layout optimization | 核心 |
| [XN-Graph](https://doi.org/10.1145/3726302.3729996) | 2025/P, SIGIR | disk graph 访问路径 | extended-neighborhood graph 与相应 disk search | 核心 |
| [GoVector](https://arxiv.org/abs/2508.15694) | 2025/A | 高维 cache 低命中 | I/O-efficient cache strategy | 核心 |
| [DGAI](https://arxiv.org/abs/2510.25401) | 2025/A | coupled layout 更新放大 | topology/vector decoupling、SADL、hybrid cache | 核心 |
| [LSM-VEC](https://arxiv.org/abs/2505.17152) | 2025/A | billion-scale dynamic updates | proximity graph 分布于 LSM levels、OOP update、adaptive search | 核心 |
| [LEANN](https://arxiv.org/abs/2506.08276) | 2025/A | 索引存储放大 | graph selective recomputation/low-storage vector index | 边界 |
| [VStream](https://www.vldb.org/pvldb/vol18/p1593-gao.pdf) | 2025/P, PVLDB | streaming vector search 与冷热分层 | memory/local disk/remote object storage、WAL、versioned segments | 边界 |
| [GATE](https://arxiv.org/abs/2506.15986) | 2025/A | base/query distribution mismatch | query-aware entry routing | 边界 |
| [Drift-Adapter](https://arxiv.org/abs/2509.23471) | 2025/A | embedding model migration | 学习 new-query → legacy-space adapter，延后重嵌入 | 边界 |

### 2026（截至 7 月 12 日）

| 系统 | 年份/状态 | 问题 | 核心机制 | 范围 |
|---|---|---|---|---|
| [OdinANN](https://www.usenix.org/conference/fast26/presentation/guo) | 2026/P, FAST | direct insert 与长期稳定性 | in-place direct insert、location indirection、空槽复用/merge | 核心 |
| [OctopusANN](https://arxiv.org/abs/2602.21514) | 2026/A | I/O 优化组合缺乏统一理解 | PQ + MemGraph + PageShuffle/PageSearch + DynamicWidth | 核心 |
| [VeloANN](https://arxiv.org/abs/2602.22805) | 2026/A | CPU stall、fragmentation、cache pollution | ExtRaBitQ records、affinity placement、record cache、coroutine | 核心 |
| [SkipDisk](https://arxiv.org/abs/2605.05787) | 2026/A | 低内存与低延迟过滤 | per-point PCA/BF16 lower bound、three-level pruning、async I/O | 核心 |
| [GateANN](https://arxiv.org/abs/2603.21466) | 2026/A | filtered SSD graph 无效 vector I/O | predicate-before-I/O、in-memory graph tunneling | 核心 |
| [PipeANN-Filter](https://arxiv.org/abs/2605.17992) | 2026/A | arbitrary filtered SSD search | speculative filtering 与概率 attribute structure | 核心 |
| [NAVIS](https://arxiv.org/abs/2605.11523) | 2026/A | high-D concurrent search/update position seeking | selective vector read、dynamic entry graph、edge cache | 核心 |
| [LIOS](https://arxiv.org/abs/2605.19335) | 2026/A | search/update QoS 与 CPU idle | 把可恢复 update subtasks 填入 search I/O stalls，控制 overrun | 核心 |
| [PiPNN](https://arxiv.org/abs/2602.21247) | 2026/A | bounded-memory billion-scale build | overlapping partitions、bulk comparisons、HashPrune | 边界/构建 |
| [DistVS](https://www.usenix.org/conference/nsdi26/presentation/yin) | 2026/P, NSDI | compute-memory-storage disaggregation | local low-PQ、remote high-PQ/graph、SSD exact vector 的三层 PRESS | 边界 |
| [d-HNSW](https://arxiv.org/abs/2505.11783) | 2026 版本/A | RDMA disaggregated memory graph | sampled representative cache、RDMA-friendly layout、batched loading | 边界 |
| [GORIO](https://arxiv.org/abs/2607.04415) | 2026/A | GPU graph traversal over NVMe-oF | GPU page-miss/control path + remote split-phase I/O | 边界 |
| [Cloud-Native Vector Search Study](https://arxiv.org/abs/2511.14748) | 2026/A | remote object storage index choice | graph/cluster、fetch granularity、cache 的系统 characterization | 边界/测量 |
| [Disk-Resident Graph ANN Evaluation](https://arxiv.org/abs/2603.01779) | 2026/A | 缺少统一比较 | storage/layout/cache/execution/update 五维 taxonomy 与 testbed | 边界/测量 |

## 3. Problem–Mechanism–System 覆盖矩阵

| 问题轴 | 已覆盖机制 | 代表系统 | 饱和判断 |
|---|---|---|---|
| `O(N)` PQ/route DRAM | neighbor PQ 随 record 下沉；all-in-disk summary；budget placement | LM-DiskANN、AiSAQ、PageANN、SkipDisk | **高**：问题与主要机制均有直接工作 |
| SSD 页局部性/I/O utilization | ID reorder、graph-aware shuffle、path-aware layout、page-node、block-aware graph、affinity placement | DiskANN++、Starling、MARGO、PageANN、BAMG、Gorgeous、VeloANN、OctopusANN | **极高**：仍有性能空间，但不是文献空白 |
| I/O–compute overlap/软件路径 | compute-driven prefetch、I/O-driven pipeline、coroutine、io_uring、SPDK | Starling、PipeANN、Turbocharging、VeloANN、OctopusANN | **极高** |
| Cache/buffer management | static hot graph、dynamic page cache、hybrid cache、adjacency-first、record-level cache | Starling、Gorgeous、GoVector、DGAI、VeloANN | **高** |
| Insert/delete/长期动态更新 | delta+merge、direct in-place、LSM/OOP、decoupled record、dynamic entry | FreshDiskANN、LM-DiskANN、OdinANN、LSM-VEC、DGAI、NAVIS | **高**；恢复语义另见后文 |
| Search/update concurrency/QoS | pipeline、layout decoupling、stall stealing、target latency degradation | HAKES、DGAI、NAVIS、LIOS、OdinANN | **高**；tenant-level isolation 未完全相同 |
| Filtered SSD search | filter-aware graph、graph tunneling、speculative attribute filter、partition | Filtered-DiskANN、GateANN、PipeANN-Filter、[UNIFY](https://www.vldb.org/pvldb/vol18/p1118-yao.pdf) | **高** |
| Workload/query distribution adaptation | query-aware split/merge、entry routing、path-weighted layout | Quake、GATE、MARGO | **高** |
| 有限 DRAM/快速构建 | RAM-budget partition/merge、parallel partitions/HashPrune、GPU build | DiskANN builder、PiPNN、HAKES | **高** |
| Multi-device/near-data execution | 4 KiB SPDK stripe、SmartSSD、CPU/GPU collaborative I/O | PipeANN、SmartANNS、FusionANNS | **高** |
| Disaggregated/tiered storage | RDMA remote memory、three-tier precision、NVMe-oF GPU control、object-storage segments | d-HNSW、DistVS、GORIO、VStream | **高且快速增长** |
| Multi-tenant index organization | shared/per-tenant tree、partition-key isolation、cold-index no-floor-cost | Curator、[Cosmos DB DiskANN integration](https://www.vldb.org/pvldb/vol18/p5166-upreti.pdf) | **中高**；不是驻盘图论文中的空格 |
| Transaction/MVCC/durability | DBMS MVCC/WAL、Bw-tree durable terms、versioned segment/WAL | [SingleStore-V](https://vldb.org/pvldb/vol17/p3772-chen.pdf)、[Manu](https://arxiv.org/abs/2206.13843)、Cosmos DB、VStream、[PostgreSQL-V](https://www.vldb.org/cidrdb/papers/2026/p2-liu.pdf) | **中高**；standalone graph 内较薄，但标准 DB baseline 很强 |
| 自动参数/设计选择 | query-level learned tuning、recall model、heuristic dimension guide | HAKES、Quake、2026 unified study | **中**：存在公开 open problem，但不是无人触及 |
| 多 embedding 模型/版本 | adapter、federated heterogeneous retrieval、每空间独立 named index | Drift-Adapter、FedBridge、现有 DB 产品 | **低**：未发现共享 graph topology 的系统 |
| SSD endurance/ZNS/FDP | 通用 DB OOP/ZNS/FDP，ANN update 系统未做 device-level endurance 闭环 | 通用 SSD/DB 工作；ANN 核心矩阵为空 | **低覆盖、低问题证据** |

## 4. 被矩阵明确关闭的“伪空白”

1. **“低 DRAM serving”不是空白。** AiSAQ 已做到 billion-scale 约 10 MiB；PageANN、SkipDisk、LM-DiskANN 提供不同 trade-off。
2. **“更好的页布局”不是空白。** 至少八个系统直接优化 layout；2026 统一研究发现 I/O utilization 仍低于 15%，这说明 frontier 未饱和，不等于 problem cell 为空。新工作必须提出不同约束或证书，不能只换 packing score。
3. **“多租户向量搜索”不是空白。** Curator 已研究 shared/per-tenant index trade-off；Cosmos DB 已展示 partition、resource governance、durability 与 DiskANN 集成。若只做 tenant filter 或 cache partition，直接撞已有系统和通用 DB 调度。
4. **“transaction/MVCC + ANN”不是空白。** SingleStore-V、Manu、Cosmos DB、PostgreSQL-V 已覆盖一致性、WAL、snapshot 或 relational integration。standalone SSD graph 缺少细粒度 crash protocol，但只补 WAL/redo 很可能是工程集成，不是论文级机制。
5. **“云端多层存储”不是空白。** VStream、DistVS、d-HNSW、GORIO 与 cloud-native characterization 已覆盖 local/remote memory、SSD、NVMe-oF、object storage 的多个组合。
6. **“并发 query/update 调度”不是空白。** LIOS 已把 update subtasks 放入 search I/O stalls，并按用户目标控制 search degradation；NAVIS/OdinANN/HAKES 也有各自 concurrency 设计。
7. **“高维度自适应”本身不是题。** VeloANN、BAMG、DGAI 和统一研究均已明确 dimension-dependent layout/execution；除非有新的可预测 phase transition 与自动切换机制，否则只是配置经验。

## 5. 真空格与对抗排序

### G1：多个 embedding 模型/版本共享一套 graph topology

**矩阵状态：唯一相对干净的空格；建议进入问题真实性 G0，不视为 Idea 已成立。**

现有系统对同一 corpus 的多个 embedding spaces 通常建立独立 ANN indexes；named vectors 也为每个 space 配独立 index。Drift-Adapter 将新 query 映射回 legacy space，目标是延后新坐标/新索引；FedBridge 在多个异构数据库间做联邦结果融合；两者都没有让多个原生 embedding coordinate/PQ payload 共享一套 disk graph topology。检索未发现“one topology, multiple coordinate spaces, per-space exact/PQ distance”的驻盘图系统。

本项目 A0 提供了窄但真实的机会信号：MiniLM-L6 v1→v2 与 E5-small v1→v2 中，exact kNN 变化显著，但 old Vamana topology 在新坐标下与 fresh topology 的 Recall–I/O 差异小于 0.5pp。此前它杀死“repair old graph”，却反过来支持一个不同问题：若多个 model versions 必须并存，是否可只存一份 topology，给每个 version 保留 coordinate/PQ payload，从而减少 graph storage、build、cache 和切换成本。

最强反例与风险：

- A0 只有两个同家族、同维度 transition；不能外推到跨架构、跨维度或 image/text spaces。
- graph adjacency 相对 full vectors 的存储比例可能不够大。以 `R=64`、4-byte ID 估算，纯 adjacency 约 260 B/vector，只占 128/384/960D float32 单版本 payload 的约 33.7%/14.5%/6.3%；两个版本并存时去掉一份 adjacency，对总 payload 只节省约 16.8%/7.2%/3.2%，尚未考虑 coupled 4 KiB record 对齐会使“逻辑去重”不能自动变成物理省盘。高维下 storage claim 很弱，价值必须主要来自避免 graph rebuild 或共享 hot-topology cache。
- 不同版本的最优 entry、PQ、metric 与 filters 仍需独立；cache sharing 可能因访问路径不同而很低。
- Drift-Adapter 已提供“不存新坐标/不建新索引”的更激进 baseline；若其质量足够，共享 topology 没有部署优势。
- Oracle shared topology 可能只适用于短期 blue-green migration，持续时间不足以回收工程复杂度。

因此下一步只能是 G0 characterization：搜集至少五组真实 model/version pairs，包含同家族、跨家族和至少一种多模态；比较 independent graphs、shared-old topology、shared-selected topology 与 Drift-Adapter。必须先计算 topology 在完整 index/storage/build/cache cost 中的真实占比、fresh graph build 的端到端成本以及双版本并存窗口长度。只有至少三组在 fixed recall 下 shared topology 的 I/O 不高于 independent graph 约 1.1×，并且避免 build 的收益足以覆盖重编码与验证、或低维场景的总 index footprint 有至少约 15% 可实现下降，才值得交 Claude 设计架构。跨维度 pair 天然不能共享同一 coordinate payload，但 topology ID graph 仍可理论共享；若质量普遍失败则立即 Kill。

### G2：自动选择 storage/layout/cache/execution 组合

**矩阵状态：部分空格；论文真实性中等，novelty 风险高，暂不优先。**

2026 统一研究明确把 dimension、page size、beam、memory budget 与 read/write ratio 的配置选择列为 open problem。HAKES 会学习 filter/refine 参数，Quake 会按 query workload 调 search/index 参数，但未发现跨 AiSAQ/PageANN/PipeANN/VeloANN 类设计组合的在线 controller。

最强攻击是：这可能只是普通 Bayesian optimization/learned cost model；不同系统的 layout 不能在线低成本切换，controller 最终只能选 deployment template。没有真实生产 workload shift 和转换成本闭环，不具备系统贡献。因此只保留为 survey finding，不启动实验。

### G3：dynamic on-SSD graph 的 crash consistency 与恢复成本

**矩阵状态：standalone graph cell 较空，但数据库边界不空；暂缓。**

OdinANN、NAVIS、DGAI、LSM-VEC 重点报告 update/search 性能，公开材料很少给出 power-failure 原子点、mapping/record 双写顺序、crash injection 与 bounded recovery time。P-HNSW 已在 persistent memory 上研究 crash consistency；SingleStore-V、Manu、Cosmos DB、VStream 已有 WAL/MVCC/durable terms。

若只为 OdinANN 增加 WAL、copy-on-write 和 recovery scan，最强审稿意见会是“标准数据库技术移植”。只有先证明 ANN graph 的 approximate invariants 允许一种比通用 WAL 更轻、仍能给 recall/connectivity 下界的恢复语义，才有独立问题。当前没有这个机制或生产 failure trace，故不立项。

### G4：SSD endurance / ZNS/FDP-aware dynamic graph

**矩阵状态：字面空格，问题真实性最低。**

现有动态 ANN 论文统计 host write bytes、merge 和空间放大，但几乎不报告 device write amplification、TBW 或 wear distribution。通用数据库研究已表明 OOP、ZNS/FDP 可显著降低 NAND writes；然而 ANN update rate 可能远低于 SSD endurance 门槛，且本项目既有实验未证明 device writes 是瓶颈。除非真实 trace 显示寿命或 GC tail latency成为部署约束，否则这是“有空白但没人需要”的典型假方向。

## 6. 统一结论与建议

路径一没有得出“驻盘图 ANN 已无任何空白”，但确认了传统系统优化空间高度拥挤。核心五维中的空格大多是性能 frontier，不是未被研究的问题。继续从 layout、PQ、async I/O、filter、update、multi-SSD 或 cache 里挑一个机制，命中 prior art 的概率仍然很高。

唯一值得交给 Gpt/Claude 做下一层问题审查的是 **G1：多 embedding 模型/版本共享 topology**，但它仍未达到 `PROVISIONAL`。它不是此前已 Kill 的 warm-start repair：后者试图修复一张旧图，G1 的目标是多版本并存时消除重复 topology/build/cache 成本；A0 的“旧图无需修复”恰好是共享可能性的证据。另一方面，高维下可省 topology bytes 很少，且“直接复用旧 topology”本身没有机制 novelty。当前只请求高层判断 G0 是否值得，未批准实验、更未设计机制。

G2–G4 只作为 gap registry 保留。若 G1 被高层认为业务窗口太短、节省比例太低或 Drift-Adapter baseline 已足够，应停止在驻盘图 ANN 内继续找缝隙，执行 Claude 的路径二，而不是从 G2–G4 中自动补位。
