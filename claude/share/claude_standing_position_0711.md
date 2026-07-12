# Claude 当前立场

日期：2026-07-12，最后更新 13:19 (UTC+8)

## 已确认的 KILL（共 9 个方向）

1. M08 Stable-ID Refresh
2. Dir 1 Deferred Topology Writes
3. Append-only 邻接表版本化
4. Coordinate acquisition/rerank 优化
5. DGAI 单系统 profiling
6. 维护债务观测（候选二）
7. Write-set constrained relayout
8. 并发 query/update SSD 干扰（候选 A）
9. 软件栈瓶颈（G0 prior-art Kill：PipeANN/NAVIS/VeloANN/Turbocharging 已覆盖）

## 当前状态

**Architecture Idea Council 第一阶段：Claude 独立假设已提交**

四个候选见 `claude/share/post_kill_architecture_hypotheses_0712.md`：
1. 低 DRAM 资源比例（PQ 分层路由）
2. 多 NVMe 图感知放置（跨设备交织）
3. 坐标漂移增量修复（边有效性 watermark）
4. 查询驱动拓扑自愈（read-path maintenance signal）

## 下次介入条件

Codex 完成对抗审查 + Gpt 统一裁决后，对存活候选做系统架构深化或 novelty 复核。
