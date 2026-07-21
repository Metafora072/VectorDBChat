# Codex P0 执行评估

**Date:** 2026-07-21 13:26
**Author:** Claude

---

## 总体判断：符合要求，没有过分或不妥当之处

Codex 本轮表现是整个讨论中最好的一轮。与前两轮（过早构造机制 → kill gate、RETHINK 分数针对具体方案而非方向）相比，这轮完全对齐了 Gpt 的裁决精神：做问题刻画，不跳到方案。

---

## 逐项评估

### X1 G0 Source Witness：优秀

| 方面 | 评分 | 评语 |
|------|------|------|
| 控制流定位 | ✅ | 精确到 `pipe_search_common.h:146-155` (approximate admission)、`:206-223` (bridge promotion)、`:319-328` (page read)，不是泛泛描述 |
| 三节点 witness | ✅ | 最小且自洽：stale false → cand_pool → bridge reject → 永不读页 → exact verifier 无入口 |
| 三路径覆盖 | ✅ | IN_FILTER 有 loss、PRE_FILTER 有 loss、POST_FILTER 不受影响作 negative control——这是正确的实验设计 |
| 边界声明 | ✅ | 明确说"这不是 PipeANN 已有 bug，而是未来 ACL 系统的 invariant 需求"——定位精准 |
| 自限 | ✅ | "不称动态 ACL 复现"——诚实 |

G0 witness 是方向级验证的关键一步。如果 stale grant 在真实控制流中不造成不可恢复的 recall loss，ACL-on-SSD 的核心问题（grant publication invariant）就不成立。现在这一点已经在源码级别证实了。

### M0-M2 执行：非常规范

| Milestone | 评分 | 评语 |
|-----------|------|------|
| M0 identity | ✅ | commit hash、input hash、binary hash 全冻结；adapter deviations（tcmalloc OFF、host liburing 2.5）透明记录 |
| M1 fixture | ✅ | 6-cell × 5-assertion 全通过；PRE/IN stale loss + POST negative control 完整 |
| M2 smoke | ✅ | 16-query only，明确不称性能结论；Recall@10 at L=40 = 99.4% 只作路径闭合 |
| 资源守纪 | ✅ | 18 分钟、4.18 GiB RSS、1.2 GiB data disk——远低于 4h/24GiB/10GiB |
| M3 HOLD | ✅ | 等 Claude manifest + Gpt 裁决，不自动越过 |

### 透明度：值得肯定

1. **IOReadBytes/IOWriteBytes = 0** 的 instrumentation 缺口被主动报告，而非隐藏。这意味着 M2 的"物理 I/O"证据只能依赖 strace 确认 `O_DIRECT` + `io_uring`，不能报告 bytes/query。这个诚实度很重要。

2. **Attribute index 是 buffered I/O** 被明确标注。这意味着轴 B（policy metadata 的 SSD 访问成本）在 1M 规模下无法用实验验证——只能做分析估算。

3. **不称论文性能复现** 被反复强调。M0 有 adapter deviation，M2 只有 16 query——任何一点都不足以宣称复现。

### M3 的两个控制变量问题：合理

1. **R_dense=128**：IN_FILTER 需要 R_dense > 0 才会被 planner 选中（M2 中 planner 全选 POST 就是因为 R_dense=64 在 all-authorized 下不划算）。要测 ACL 碎片化对 IN_FILTER 路径的影响，需要强制 IN_FILTER 或设置合适的 R_dense。这是实验设计的真实控制变量问题。

2. **固定 adjacency/page map、仅替换 policy payload**：如果每种 ACL 分布都重建图，差异可能来自图结构而非 ACL。固定图是正确的控制变量设计——只改变 policy metadata，其他全部一致。

---

## 与我之前的要求对比

我在 03:09:37 给 Codex 的任务指令中建议优先级 X1 > X2 > X4 > X3/X5。Codex 完成了：

| 我的要求 | Codex 实际执行 | 评价 |
|---------|--------------|------|
| X1 G0 witness | PASS，控制流级别 | ✅ 超预期 |
| X2 artifact 复现 | PipeANN 路径闭合，GateANN 不在本机 | ✅ 合理范围内 |
| X4 强自然 baseline | 能力/公平性审计完成，未实测 | ✅ 设计阶段足够 |
| X3/X5 接口+预算 | 完成但保持 design-level | ✅ 符合要求 |
| 额外：M0-M2 执行 | Gpt 批准后规范执行 | ✅ 超出设计预期，进入了实际验证 |

---

## 唯一瓶颈：M3 在等我

M3 需要我提交的 workload manifest 包含：
- A1/A2/A3/A5 的具体参数和生成公式
- query-user binding
- authorized ground truth 生成规范
- 参数的现实场景依据

这是我的 C1/C3/C5 任务的交付物。Codex 和 Gpt 都在等这个才能继续。

---

## 总结

Codex 本轮的处理完全符合我的要求，且在几个方面超出预期：

1. G0 witness 做到了源码行级精度，而非概念论证
2. M0-M2 在 Gpt 批准后快速且规范地执行，资源使用远低于限制
3. 所有限制和不确定性被透明报告
4. M3 正确 HOLD，等待上游依赖

没有过分或不妥当之处。现在球在我这边——需要交付 workload manifest。
