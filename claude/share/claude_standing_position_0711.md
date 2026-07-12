# Claude 当前立场

日期：2026-07-12，最后更新 17:15 (UTC+8)

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

**PZ 扩展目标范围：** 不限于驻盘图 ANN 和 FAST/VLDB，接受 ANNS/向量数据库相关的任何方向，AI 会议也可接受。

扩展后候选方向（`claude/share/path2_expanded_directions_0712.md`）：
- E1. RAG 系统的向量索引层（优先级最高）
- E2. 向量搜索的学习化组件
- E3. 面向 LLM 推理的近似搜索
- E4. ANN 在数据管理系统中的深度集成
- E5. 向量搜索 characterization

等待 Codex 对 E1–E3 做快速 prior-art 扫描。

## 角色分工

不再由 Claude 独立提出 novelty 声称。流程：Codex 先验证 prior-art 边界 → Claude 评估架构结构性和 kill 条件 → Gpt 统一裁决。
