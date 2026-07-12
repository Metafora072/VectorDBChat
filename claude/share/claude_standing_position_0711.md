# Claude 当前立场

日期：2026-07-12，最后更新 13:41 (UTC+8)

## 已确认的 KILL（共 9 + 3 个方向）

### 原始九个
1. M08 Stable-ID Refresh
2. Dir 1 Deferred Topology Writes
3. Append-only 邻接表版本化
4. Coordinate acquisition/rerank 优化
5. DGAI 单系统 profiling
6. 维护债务观测（候选二）
7. Write-set constrained relayout
8. 并发 query/update SSD 干扰（候选 A）
9. 软件栈瓶颈（G0 prior-art Kill）

### Council Round 1（三个 Kill）
10. 低 DRAM PQ 分层（AiSAQ/LM-DiskANN/PageANN 已覆盖）
11. 多 NVMe 图感知放置（PipeANN 4KB stripe 已覆盖）
12. 查询驱动拓扑自愈（Quake/GATE 已覆盖）

## 当前状态

**Architecture Idea Council Round 2：Claude 修订假设已提交**

三个候选见 `claude/share/post_kill_architecture_hypotheses_round2_0712.md`：
- A：跨 embedding 版本 warm-start 图重建（候选三修订版）
- B：筛选型图搜索 I/O 放大与标签感知布局（新，首选）
- C：外存图构建（新）

每个候选明确标注了需要 Codex 验证的 prior-art 假设，不独立声称 novelty。

## 下次介入条件

Codex 完成 Round 2 对抗审查后，根据结果决定是否有候选存活。
