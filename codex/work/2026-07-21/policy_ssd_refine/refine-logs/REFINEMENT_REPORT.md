# Refinement Report

**Problem**: bounded-DRAM SSD graph ANN 的动态权限维护  
**Initial Approach**: page-addressed grant delta  
**Date**: 2026-07-21 (UTC+8)  
**Rounds**: 1 / 5  
**Final Score**: 6.275 / 10  
**Final Verdict**: RETHINK

## Score Evolution

| Round | Fidelity | Specificity | Contribution | Frontier | Feasibility | Validation | Venue | Overall | Verdict |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 8.5 | 6.0 | 4.0 | 8.5 | 6.5 | 7.0 | 4.5 | 6.275 | RETHINK |

## Method Evolution

1. 纠正 GateANN 内存事实：63 GiB 对应 1B/R16 neighbor store，而非 100M；当前机器 251 GiB，因此“机器内存放不下”不能作为动机。
2. 保留 ACL-on-SSD 场景，删除“首个整合系统即可构成贡献”的推理。
3. 将 page-addressed delta 降为 hypothesis，并将最强基线升级为相同 page-prefix、cache、WAL、batching 与 compaction 的 RocksDB 组合。
4. 将 scope 收紧为 object-side policy atom updates；MVCC、lazy revoke 与 exact verification 均为复用 plumbing。
5. 停止完整实现，先做源码 stale-negative witness 与自然组合等价性审计。

## Remaining Weaknesses

- 尚无目标 ANN 代码中的真实剪枝 witness。
- 尚无普通 page-prefix RocksDB 无法提供的唯一性质。
- locator、grant publish、merge/GC 与 top-k refill 仍需在任何未来设计中形式化。
- 缺少真实权限 churn trace；synthetic 结果最多支持 HOLD。

## Raw Reviewer Response

完整原文见 `round-1-review.md`。

## Next Step

把等价性门禁提交 Gpt 审阅。只有 Gpt 同意，才准备 G0/G1 的源码审计清单、时间/空间预算；当前不运行实验。
