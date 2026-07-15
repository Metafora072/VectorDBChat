# 路径二：相邻未饱和方向初步评估

日期：2026-07-12

## 前提

驻盘图 ANN（Vamana/DiskANN 家族）在 2023–2026 经历了 30+ 系统的集中攻击，传统系统优化维度高度饱和。路径一 gap analysis 确认了这一诊断。以下方向利用 PZ 在存储系统/体系结构领域的积累，转向密度更低的相邻问题。

每个方向标注：**核心问题**、**PZ 背景适配度**、**最强已知 prior art**、**需要 Codex 验证的关键问题**、**论文形态**。

---

## 方向 A：向量搜索的存储引擎集成（DB-native ANN）

**核心问题：** 关系型/分析型数据库（pgvector、DuckDB、SQLite-VSS）将 ANN 作为 extension 接入，但 extension 无法感知 buffer pool、WAL、MVCC、query optimizer 的状态。当 ANN 索引与事务引擎深度耦合时，存储引擎层面出现哪些新的系统设计问题？

**PZ 适配度：高。** 这是存储引擎级别的系统工作，涉及 page 管理、WAL 协议、并发控制——与 PZ 的 FAST/VLDB 定位和存储系统背景高度一致。

**最强已知 prior art：**
- Turbocharging (2025)：pgvector HNSW 的 I/O path 优化，但未触及 transaction 语义
- SingleStore-V (VLDB 2024)：向量列 + relational 的 MVCC 设计
- PostgreSQL-V (CIDR 2026)：pgvector 在 PG 内部的 characterization 和优化
- Cosmos DB DiskANN (VLDB 2025)：云端 partition/resource governance/durability 集成
- Manu (2022)：Milvus 的 log-based WAL + segment 管理

**需要 Codex 验证：**
1. SingleStore-V / PostgreSQL-V / Cosmos DB 是否已覆盖"ANN 索引在 MVCC 下的 visibility 和 consistency 保证"问题
2. Turbocharging 之后，pgvector/DuckDB 的存储引擎 integration 是否仍有未被触及的系统层问题
3. "ANN 索引的 crash recovery"在 DB-native 场景下是否已被充分解决
4. 是否存在"ANN-aware buffer management"（让 buffer pool 理解 ANN 访问模式）的系统工作

**论文形态：** 系统论文（设计 + 实现 + evaluation）或 characterization + optimization（如 Turbocharging）。适合 VLDB/SIGMOD，可能也适合 FAST（若聚焦存储引擎层）。

---

## 方向 B：向量数据的存储效率与分层管理

**核心问题：** 十亿级向量的存储成本是真实痛点（1B × 768D × 4B ≈ 3 TB full precision）。当前系统主要靠量化（PQ/SQ/RaBitQ）降低搜索内存，但存储层面的压缩、去重、cold/hot 分层、以及存储成本与搜索质量的端到端 trade-off 尚未被系统性研究。

**PZ 适配度：高。** 分层存储、压缩、cold data management 是经典存储系统问题。

**最强已知 prior art：**
- VStream (2025)：三层存储（DRAM/SSD/object storage）的向量流处理
- DistVS (2025)：disaggregated 向量存储的分层设计
- GORIO (2025)：NVMe-oF GPU 控制的 SSD 向量搜索
- LSM-VEC (2024)：LSM-tree 风格的向量存储管理
- RaBitQ/ScaNN/AdSampling：量化/采样技术（算法层，非存储系统层）

**需要 Codex 验证：**
1. VStream/DistVS/GORIO 是否已覆盖 hot/cold 向量分层的核心系统设计
2. 是否存在"向量数据的增量压缩/delta encoding"的系统工作（非 per-vector quantization，而是 cross-vector 存储压缩）
3. "向量数据的 garbage collection 和 space reclamation"在动态场景下是否被系统性研究
4. 向量存储的 cost-performance Pareto 是否有系统性 characterization

**论文形态：** 系统论文或 characterization。适合 FAST/VLDB。

---

## 方向 C：驻盘向量搜索的系统性 Characterization / Benchmark

**核心问题：** 2023–2026 产出了 30+ 个驻盘 ANN 系统，但缺乏跨系统、跨硬件、跨工作负载的统一 characterization。每个系统论文只与 DiskANN baseline 比较，用自己选择的数据集和参数。系统之间的 I/O 效率、CPU 利用率、内存效率、SSD 带宽利用率的横向比较几乎不存在。

**PZ 适配度：中高。** FAST 接受 characterization/benchmark 论文（如 IISWC 的 Milvus+DiskANN characterization），但需要非常强的实验设计和新颖观察，不能只是跑 benchmark。PZ 已有的 DiskANN/OdinANN/DGAI 实验基础设施可以复用。

**最强已知 prior art：**
- IISWC 2025 characterization：Milvus + DiskANN 的 system-level profiling
- 2026 unified study（Codex gap analysis 中提到的）：dimension/page/beam/memory 配置选择
- ANN-Benchmarks/Big-ANN-Benchmarks：in-memory benchmark，非 disk-resident

**需要 Codex 验证：**
1. IISWC 2025 和 2026 unified study 的具体覆盖范围
2. 是否已有跨系统（DiskANN vs PipeANN vs VeloANN vs PageANN 等）的统一 benchmark
3. 不同代 NVMe（Gen3/4/5）对驻盘 ANN 性能特性的影响是否被研究
4. "SSD I/O 效率"（有效数据 vs 实际读取量）的跨系统比较是否存在

**论文形态：** Characterization + insights + guidelines。适合 FAST/ATC/VLDB。

---

## 方向 D：多索引共享基础设施（Vector Store as a Service）

**核心问题：** 生产环境中通常存在数十到数百个独立的向量索引（不同 collection、不同 embedding model、不同 tenant）。当前系统为每个索引独立分配 SSD 空间、内存 buffer 和 I/O 带宽。多索引共享存储基础设施的资源隔离、公平调度、SSD 带宽分配和冷索引成本优化是一个系统级问题。

**PZ 适配度：中。** 资源调度和隔离是系统问题，但更偏向 cloud/service 层面，与 PZ 的存储系统底层背景有一定距离。

**最强已知 prior art：**
- Curator (2025)：multi-tenant 向量搜索的 shared/per-tenant index trade-off
- Cosmos DB DiskANN integration：partition/resource governance
- Milvus/Qdrant/Weaviate 的多 collection 管理（工程实践，非论文）

**需要 Codex 验证：**
1. Curator 的覆盖范围——是否已解决 SSD 层面的多索引资源隔离
2. 是否有"cold index 零成本保持"或"按需加载 SSD 索引"的系统工作
3. 多索引共享 buffer pool / SSD bandwidth 的调度是否被研究

**论文形态：** 系统论文。适合 VLDB/OSDI/ATC。

---

## 我的优先排序

**A > B > C > D**

方向 A 最值得优先验证：DB-native ANN 的存储引擎集成是一个明确的系统问题，与 PZ 背景高度适配，且虽然有 SingleStore-V / Turbocharging 等先行者，但存储引擎层面的深度整合（buffer-aware ANN、ANN-aware WAL、transaction visibility for approximate results）可能仍有未被覆盖的空间。关键是需要 Codex 先验证 SingleStore-V 和 PostgreSQL-V 的精确覆盖边界。

方向 B 次之，但需要先确认 VStream/DistVS 的覆盖范围。

方向 C 是保底选项——characterization 论文的门槛不在于技术 novelty 而在于 insight 深度，PZ 的实验基础设施可以快速启动，但必须能产出非显而易见的发现。

方向 D 更偏 cloud service，与 PZ 当前定位距离最远，优先级最低。

**每个方向都必须先经过 Codex prior-art 验证后才能判断是否可行。** 不重复路径一的错误。
