# Claude 当前立场

日期：2026-07-12，最后更新 18:40 (UTC+8)

## 已确认的 KILL（共 23 个方向）

### 原始九个（insert/update 路径）
1. M08 Stable-ID Refresh
2. Dir 1 Deferred Topology Writes
3. Append-only 邻接表版本化
4. Coordinate acquisition/rerank 优化
5. DGAI 单系统 profiling
6. 维护债务观测（候选二）
7. Write-set constrained relayout
8. 并发 query/update SSD 干扰（候选 A）
9. 软件栈瓶颈（G0 prior-art Kill）

### Council Round 1
10. 低 DRAM PQ 分层（AiSAQ/LM-DiskANN/PageANN 已覆盖）
11. 多 NVMe 图感知放置（PipeANN 4KB stripe 已覆盖）
12. 查询驱动拓扑自愈（Quake/GATE 已覆盖）

### Council Round 2
13. Filtered search 标签感知布局（GateANN/PipeANN-Filter 已覆盖）
14. 外存图构建（DiskANN RAM-budget builder/PiPNN 已覆盖）

### A0 Finding Gate
15. 跨 embedding 版本 warm-start repair（旧图不需修复，recall 差 <0.5pp）

### PQ-Free Direction
16. PQ-free exact navigation（AiSAQ/PageANN 已覆盖）

### Gap Analysis 结论
17. 共享 topology（G1）——storage claim 太弱（高维 3–7%），A0 覆盖窄，无机制 novelty
18. 自动调优/crash recovery/SSD endurance（G2–G4）——分别被 autotuning baseline / 标准 WAL / 未证明瓶颈攻击

### 路径二方向 B
19. 向量存储效率整体——VStream/DecoupleVS/DistVS/FaTRQ/LEANN/Milvus 2.6/S3 Vectors 覆盖
20. B1 routing-criticality quantization——量化算法贡献非系统贡献
21. B2 跨 embedding lazy migration——继承 G1 Kill 边界
22. B4 query-frontier I/O fusion——继承 coalescing Kill

### DiskColBERT（Idea 1 + Idea 3）
23. DiskColBERT / SSD 驻盘 multi-vector 检索——ESPN (ISMM 2024) 覆盖 GPU+SSD 路径，ColBERT-serve (ECIR 2025) 覆盖 mmap 路径。容量计算、I/O 模式描述均有事实错误。剩余 CPU-only purpose-built I/O 空间太窄，只是 engineering delta。连带 Idea 3 characterization 失去叙事目标。

## 关键发现（非方向）

Vamana 拓扑对坐标扰动具有强鲁棒性：kNN overlap 变化 44–56% 时，old topology recall 与 fresh graph 差异 <0.5pp。

## 路径一结论

Codex 系统化 gap analysis（30+ 系统，2023–2026）确认驻盘图 ANN 传统系统优化空间高度饱和。路径一正式完成。

## 路径二结论

方向 B（向量存储效率）出局。扩展方向 E2（learned components）、E3（LLM inference ANN）出局。E1 只剩极窄的 document-version atomic refresh。DiskColBERT（Idea Discovery Pipeline 产出的最高排名方向）被 ESPN + ColBERT-serve 覆盖后出局。

## 当前状态

**活跃候选：Idea 2——VAQ 物理设计。** Exqutor (Microsoft 2025) 只做了 query optimizer (10000× on TPC-H+vectors)，DiskJoin (SIGMOD 2026) 只覆盖 pairwise join。物理设计（数据布局、分区策略、向量/元组共置、缓冲管理）完全空白。PZ 的存储/布局专长适配，pgvector/DuckDB 可原型化。Novelty 7/10。

**等待 Codex prior-art 审计**：重点检查 Exqutor/DiskJoin/pgvector/PostgreSQL-V 覆盖边界、传统物理设计 advisor 对 vector-specific 问题的适用性。

**已关闭的窄问题**：
- Co-access locality trace（成功概率低，2× 门槛高）
- E1-F document-version atomic refresh（太窄）

## 反思

23 kills 后的结构性教训：ANNS/vector DB 是一个被过度研究的领域。在 2026 年找到完全无人触及的系统设计空间极其困难。成功概率最高的路径是找到被忽视的**问题定义**（如 Exqutor 把 vector similarity 定义为 SQL operator 从而打开 physical design 空间），而不是在已有系统设计空间里找缝隙。

## 角色分工

Claude 独立评估方向可行性 → Codex 做 prior-art 审计和实验执行 → Gpt 统一裁决。Claude 对 Codex 的 Kill 做独立分析而非自动接受，但在分析后仍可能得出相同结论。
