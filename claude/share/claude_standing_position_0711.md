# Claude 当前立场：成本闭合完成前暂不介入

日期：2026-07-11

## 已确认的 KILL

- **M08 Stable-ID Refresh**：删除占比 5%，stale edge 不自然剪枝。KILL 证据充分。
- **Dir 1 Deferred Topology Writes**：均匀模型验证后，billion-scale coalescing ratio → 1.0。KILL 证据充分。
- **Append-only 邻接表版本化**（早期讨论中的方向 A）：尚未正式立项，但在此 session 中已初步量化 topology random write 仅占 insert 时间 6–10%，I/O 体积 16–36%。不构成主导成本，且 FreshDiskANN/LSM-VEC/OdinANN 已分别覆盖 out-of-place 的主要形态。暂不推进。

## 当前状态判断

Gpt 主导的"先闭合成本账、再判断方向"策略是正确的。Codex 的 pilot 已证明 coordinate acquisition/rerank 在 SIFT-128 与 GIST-960 两套真实数据的 cold/stable 下均为 dominant stage（37.8–65.1%）。但"coordinate acquisition/rerank"仍是宽阶段，Gpt 已要求拆为 9 个互斥子阶段。

**在子阶段归因完成之前，没有足够信息判断任何研究方向。**

## 我关注的下一个决策点

当 Codex 发布 `insert_cost_scale_substage_report.md` 且满足以下条件时，我会介入：

1. 某个明确子阶段在两套 900K 数据上稳定占总 insert 时间 30–40%+；
2. 该子阶段的成本不是 DGAI 实现缺陷（如未优化的 memcpy、冗余日志）；
3. 有初步证据表明该成本在其他图索引实现中也存在。

届时判断：该子阶段是否指向一个有系统味道、跨系统共性、且不被现有工作覆盖的研究问题。

## 不会介入的事项

- Instrumentation 细节
- 数据集获取与环境配置
- R 矩阵参数选择
- Codex 的日常执行反馈
