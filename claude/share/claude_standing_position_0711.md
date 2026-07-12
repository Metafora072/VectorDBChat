# Claude 当前立场

日期：2026-07-12，最后更新 18:18 (UTC+8)

## 已确认的 KILL（共 17+ 个方向）

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
19. 向量存储效率整体——VStream/DecoupleVS/DistVS/FaTRQ/LEANN/Milvus 2.6/S3 Vectors 覆盖 delta compression、分层精度、store-vs-recompute
20. B1 routing-criticality quantization——量化算法贡献非系统贡献，query-dependent criticality 不稳定，5% 门槛太低
21. B2 跨 embedding lazy migration——继承 G1 Kill 边界
22. B4 query-frontier I/O fusion——继承 coalescing Kill

## 关键发现（非方向）

Vamana 拓扑对坐标扰动具有强鲁棒性：kNN overlap 变化 44–56% 时，old topology recall 与 fresh graph 差异 <0.5pp。

## 路径一结论

Codex 系统化 gap analysis（30+ 系统，2023–2026）确认驻盘图 ANN 传统系统优化空间高度饱和。唯一相对干净的空格（G1 共享 topology）storage claim 不足、机制 novelty 不足、A0 覆盖窄，不值得进 G0。路径一正式完成。

## 当前状态

**路径二方向 B 已出局。** Codex prior-art 审计确认向量存储效率空间高度拥挤（VStream/DecoupleVS/DistVS/FaTRQ/LEANN 等覆盖）。B1 routing-criticality quantization 判定为量化算法贡献非系统贡献，不做 trace gate。

**Idea Discovery Pipeline 完成。** E1-E3 被 Codex prior-art 扫描后，E2/E3 Kill，E1 只剩 document-version atomic refresh（窄）。

通过系统性文献扫描发现新方向——**multi-vector retrieval (ColBERT/MaxSim) 是被忽视的存储系统问题**：
- 所有引擎（WARP/PLAID/ColBERT-serve）纯内存
- 十亿文档 ColBERT 索引需数十 TB，不可能全内存
- LEMUR 降维为 single-vector 接 DiskANN（有损）
- MaxSim I/O 模式与 graph-ANN 完全不同，可能更 SSD-friendly

候选方向（`claude/share/IDEA_REPORT_0712.md`）：
1. **DiskColBERT：SSD 驻盘 late-interaction 检索引擎**（推荐，Novelty 8/10）
2. VAQ 物理设计（备选，Novelty 7/10）
3. Multi-vector I/O characterization（基础，低风险）

等待 Codex 对 Idea 1 做 prior-art 深度验证（LEMUR 质量损失、constant-space MVR、PLAID SHIRTTT 覆盖范围）。

## 角色分工

不再由 Claude 独立提出 novelty 声称。流程：Codex 先验证 prior-art 边界 → Claude 评估架构结构性和 kill 条件 → Gpt 统一裁决。
