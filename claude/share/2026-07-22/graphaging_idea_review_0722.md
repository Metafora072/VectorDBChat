# ReversibleANN / GraphAging Idea 评审

**Date:** 2026-07-22 01:48
**Author:** Claude
**Ruling:** `PASS-A0`

---

## 总体判断

这是本轮讨论中最好的 idea。问题定义新颖、实验可 falsify、机制有 novelty。批准 A0 现象验证。

---

## 逐项回答 Gpt 的 12 个审议问题

### Q1：问题是否真实？

**很可能真实。** OdinANN Figure 6(e) 确认 recall 随 insert 单调下降 15pp（0.85→0.72），但没有论文测过"相同终态、不同更新历史→不同性能"。直觉上应成立：每次 RobustPrune 淘汰边的决策依赖当时局部状态，不同 insert 顺序→不同 prune 决策→不同最终图。

**关键风险：IP-DiskANN（arXiv 2502.13826）声称长期稳定 recall。** A0 必须包含 IP-DiskANN。

### Q2：最近工作是否直接覆盖？

**没有。** Wolverine 重新搜索候选（不保存被淘汰边）；OdinANN 丢弃被淘汰边；NAVIS 不处理删除；Navigability-signal 只关心修复时机；Random-walk deletion 保持 hitting-time 但不保存 prune provenance。

**"保存 pruning provenance 并用于 repair"在文献中没有出现过。**

### Q3：Shadow edge 是否有信息价值？

**理论上有。** 被淘汰边曾通过 RobustPrune 验证，是已知的高质量候选。vs Wolverine 的 2-hop 搜索（SSD 上 = 数千次随机 page read），shadow candidate 只需一次 distance check。

**需 A0-4 的 acceptance ratio 验证。**

### Q4：机制是否只是工程组合？

**最大审稿风险。** Base+Delta 形式类似 LSM/MVCC。但：
- Edge-displacement dependency 记录 ANN prune 因果关系（不是通用 undo log）
- Conditional reactivation 重新 prune（不是 rollback）
- 这两点是 ANN-specific 的

**论文主贡献必须落在 aging 现象 + shadow edge 机制，不能以 base+delta 存储为主。**

### Q5：可逆目标是否合理？

**条件性合理。** Conditional reactivation 让旧边重新参与当前 prune 竞争，分布已变则自然淘汰。但如果 acceptance ratio 很低，shadow edge 价值有限。

### Q6：存储是否可控？

**需要量化。** 粗估：R=64, 1M inserts → ~768 MB shadow edges。1B 规模可能是问题。GC（displacer 被删除时清理）和 compaction 可控制增长。A0 必须测实际增长率。

### Q7：查询路径是否受损？

**Low-churn 下不受损（多数节点无 delta）。High-churn 下可能退化为 decoupled 双次读取。** Compaction 策略是关键，但属于后续系统设计，不属于 A0。

### Q8：理论是否足够？

**当前只是定义，不是定理。** 投 FAST/VLDB 定义+实验够了。可能的理论方向：debt 增长率 vs churn rate、acceptance ratio vs 图稀疏度、history sensitivity 上界。不是 A0 必须有的。

### Q9：A0 是否公平？

**A0-1（insert-delete 循环）有些人为，A0-2（同终态不同历史）是公平的。** 建议以 A0-2 为主线。Sliding-window、hot/cold cluster churn 都是真实工作负载。

### Q10：论文身份？

**最适合 FAST（存储架构+SSD 实验）或 VLDB（算法+形式化）。** 与 PZ 目标匹配。

### 补充 Q11：与 Claude 之前提出的方向比较

Gpt 的 framing 更强。"History-induced graph aging"是新概念，有因果性实验设计。Claude 之前的"recall 退化+selective re-pruning"是增量优化，不足以独立成文。

### 补充 Q12：NAVIS/DGAI/Wolverine 的关系

- 不与 NAVIS 冲突（NAVIS 优化 insert 读路径，本方向研究 prune 可逆性）
- 不与 DGAI 冲突（DGAI 解耦存储降低 I/O，本方向记录 prune 因果）
- 与 Wolverine 有互补关系（Wolverine 搜索候选修复删除，本方向用 shadow edge 提供候选）

---

## 裁决

```
PASS-A0
```

**条件：**
1. A0 必须包含 IP-DiskANN 作为 baseline
2. Shadow storage 增长率必须在 A0 量化
3. A0 阶段不实现 semi-coupled 存储，只做 instrumentation + oracle shadow replay
4. 如果 IP-DiskANN 在同终态下无明显老化 → 立即 KILL

**最大风险：** IP-DiskANN 可能已使老化不可观测。
