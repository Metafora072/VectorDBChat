# 战略评估：Architecture Idea Council 后

日期：2026-07-12

## 事实清单

17+ 个方向被 Kill，覆盖：
- insert 路径全部一级/二级阶段和三个跨系统候选
- 软件栈/I/O 引擎（PipeANN/NAVIS/VeloANN/Turbocharging 已覆盖）
- 低 DRAM serving（AiSAQ/LM-DiskANN/PageANN/SkipDisk 已覆盖）
- 外存构建（DiskANN RAM-budget builder/PiPNN 已覆盖）
- Filtered search 布局（GateANN/PipeANN-Filter 已覆盖）
- 查询驱动拓扑适应（Quake/GATE/MARGO 已覆盖）
- 跨 embedding 版本 warm-start repair（A0：旧图不需要修复）
- PQ-free exact navigation（AiSAQ/PageANN 已覆盖）

## 诊断：为什么卡住了

**不是执行问题，是领域成熟度信号。** 2023–2026 年驻盘图 ANN 经历了一轮爆发式增长，产出 18+ 个系统/变体（DiskANN、OdinANN、PipeANN、FreshDiskANN、NAVIS、VeloANN、LIOS、Turbocharging、AiSAQ、LM-DiskANN、PageANN、SkipDisk、GateANN、Quake、GATE、MARGO、Starling、DiskANN++、OctopusANN、PiPNN、HAKES、GORIO、d-HNSW），覆盖了 serving 低内存、动态更新、异步 I/O、filtered search、workload 自适应、多盘并行、page-level search 等几乎所有角度。

在这个密度下，任何"从已知技术缝隙反推问题"的策略大概率命中已有工作。我的方法论错误是：用不完整的文献知识声称 novelty，而不是先验证 novelty 再提出方向。

## A0 Finding 的价值

虽然 A0 杀死了 warm-start repair 方向，但它产出了一个有价值的发现：

> **Vamana 图拓扑对坐标扰动具有出乎意料的鲁棒性。** 即使 exact kNN 邻居变化 44–56%（E5-small v1→v2），旧拓扑的 Recall–I/O 曲线与新建图的差异 < 0.5 个百分点。

这个发现本身不构成系统贡献，但作为一个经验性事实，它可以在未来方向中被利用（例如：在需要多版本 embedding 共存的场景中，一套拓扑可以服务多个 embedding 版本）。

## 两条前进路径

### 路径一：系统化文献 gap 分析（仍在图 ANN 领域内）

当前所有 Kill 来自一个共同原因：我对 2023–2026 文献的覆盖不够。如果 PZ 仍想在驻盘图 ANN 发力，正确做法不是让我继续猜方向，而是：

1. **Codex 执行结构化文献普查**：搜集所有 2023–2026 驻盘/SSD/external-memory ANN 系统论文，建立 (问题, 机制, 系统) 矩阵
2. **识别矩阵中的真正空白**：哪些 (问题, 场景) 组合没有被任何系统覆盖
3. **由空白出发设计假设**：确认空白是真实需求还是不值得做

这比让我盲目提出假设然后被 Kill 效率更高。

### 路径二：战略性转向相邻但未饱和的领域

利用 PZ 在驻盘图 ANN 领域积累的深厚理解和实验基础设施，转向一个密度更低但仍有系统味道的问题。以下是我认为与 PZ 背景（存储/体系结构、FAST/VLDB）最适配的方向，但**每个都需要 Codex 做 prior-art 验证后才能判断是否可行**：

**A. 向量搜索的端到端数据库集成**
- pgvector/DuckDB 等关系数据库中的向量搜索，涉及查询优化器、buffer 管理、事务一致性与 ANN 的交互
- 系统味道：存储引擎级集成，非插件式
- Turbocharging 覆盖了 pgvector HNSW 的 I/O 优化，但 transaction/MVCC + ANN 的交互可能未被覆盖
- 风险：可能进入 SIGMOD/VLDB 数据库领域，需要数据库系统背景

**B. 多索引/多租户向量存储系统**
- 从单索引优化转向多索引共享基础设施的系统设计
- 系统味道：资源隔离、公平调度、SSD 带宽分配
- 与 PZ 存储/调度背景适配
- 风险：Milvus/Qdrant 的工程实践可能已覆盖主要设计点

**C. 向量搜索的存储效率——压缩、去重、分层**
- 十亿级向量的存储成本是真实痛点（1B × 768d × 4B = 3 TB full precision）
- 存储层的向量压缩、delta encoding、分层存储（hot/cold tier）
- 系统味道：存储系统经典问题
- 风险：可能与 RaBitQ、ScaNN 等量化工作重叠

**D. 驻盘向量搜索 benchmark/characterization（测量论文）**
- IISWC 2025 做了 Milvus+DiskANN 的 characterization
- 更广泛的 benchmark：多系统、多硬件（Gen3/4/5 NVMe）、多负载类型
- 系统味道：偏测量，但 FAST 接受 characterization/benchmark 论文
- 风险：需要非常强的实验设计和新颖观察

## 我的角色限制

连续 17 次 Kill 中，多次因为我的 prior-art 判断有事实错误。这反映了一个结构性限制：我的训练数据截止时间和对 2024–2026 预印本的覆盖不足以在这个快速发展的子领域中可靠地判断 novelty。

在后续流程中，我建议调整角色分工：
- **Codex**：先行搜索和验证 prior art（它可以访问 arXiv/论文 PDF）
- **Claude**：在 Codex 确认 prior-art 边界后，评估系统架构的结构性、kill 条件设计、论文形态判断
- **Gpt**：统一裁决和门禁设计

这样可以避免我再次基于不完整文献做 novelty 声称。

## 建议

**优先路径一（系统化 gap 分析）**，因为 PZ 已在驻盘图 ANN 上投入了大量时间和理解。但如果 gap 分析确认"所有系统级角度都已被覆盖"，应毫不犹豫地执行路径二。

不建议继续让我独立提出假设再交 Codex 审查的循环——这个循环已经证明效率太低。下一步应该反转流程：让 Codex 先找到真正的空白，然后我来评估哪些空白值得填。
