# Claude 当前立场

日期：2026-07-12，最后更新 17:00

## 已确认的 KILL

- **M08 Stable-ID Refresh**：删除占比 5%，stale edge 不自然剪枝。
- **Dir 1 Deferred Topology Writes**：billion-scale coalescing ratio → 1.0。
- **Append-only 邻接表版本化**：topology write 仅 6–10%，prior art 覆盖。
- **Coordinate acquisition/rerank 优化**：DGAI 解耦布局特有 tradeoff，非共性。
- **Application-cold io_submit 双峰**：非平稳，实现诊断。
- **DGAI 单系统 profiling**：search residual 分散，两数据集主项不同，无共同 30% 子阶段。
- **候选二（维护债务观测）**：维护机制跨系统不兼容，统一指标不可行。
- **Write-set constrained relayout**：Oracle 上界 ~1 页/事件，历史信号无预测力，phase shift 无正收益。

## 总体判断

Insert 路径已穷尽。从一级阶段到 oracle 级的系统假设，均未找到跨系统共同的、可被单一设计显著改善的主导瓶颈。继续在 insert 成本上投入不会产出 FAST/VLDB 论文。

建议转向：A（并发 query/update SSD I/O 干扰）、B（查询侧退化曲线）或 C（换赛道）。详见 `claude/share/claude_post_oracle_assessment_0712.md`。

## 下次介入条件

PZ 和 Gpt 选定新方向后，需要 novelty/系统味道判断时。

## 不会介入的事项

- 日常 instrumentation、数据集配置、代码审计
- Insert 路径的任何进一步分解
