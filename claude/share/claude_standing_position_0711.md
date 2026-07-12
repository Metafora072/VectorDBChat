# Claude 当前立场

日期：2026-07-12，最后更新 16:46 (UTC+8)

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

## 关键发现（非方向）

Vamana 拓扑对坐标扰动具有强鲁棒性：kNN overlap 变化 44–56% 时，old topology recall 与 fresh graph 差异 <0.5pp。

## 路径一结论

Codex 系统化 gap analysis（30+ 系统，2023–2026）确认驻盘图 ANN 传统系统优化空间高度饱和。唯一相对干净的空格（G1 共享 topology）storage claim 不足、机制 novelty 不足、A0 覆盖窄，不值得进 G0。路径一正式完成。

## 当前状态

**进入路径二：战略转向相邻未饱和领域。** 四个候选方向已整理至 `claude/share/path2_adjacent_directions_0712.md`：
- A. DB-native ANN 存储引擎集成（优先级最高）
- B. 向量数据存储效率与分层管理
- C. 驻盘向量搜索系统性 characterization
- D. 多索引共享基础设施

等待 PZ 选择感兴趣的方向后，由 Codex 做针对性 prior-art 验证。

## 角色分工

不再由 Claude 独立提出 novelty 声称。流程：Codex 先验证 prior-art 边界 → Claude 评估架构结构性和 kill 条件 → Gpt 统一裁决。
