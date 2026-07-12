# Claude 当前立场

日期：2026-07-12，最后更新 16:30 (UTC+8)

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

## 关键发现（非方向）

Vamana 拓扑对坐标扰动具有强鲁棒性：kNN overlap 变化 44–56% 时，old topology recall 与 fresh graph 差异 <0.5pp。

## 当前状态

**战略分叉点。** 已提交 `claude/share/claude_strategic_assessment_post_council_0712.md`。两条路径：
1. 反转流程——Codex 先做系统化文献 gap 分析，再从空白出发
2. 战略转向——利用已有领域理解转到相邻未饱和问题

等待 PZ 战略决策。

## 角色调整建议

不再由 Claude 独立提出 novelty 声称。改为：Codex 先验证 prior-art 边界 → Claude 评估架构结构性和 kill 条件。
