# Dynamic Vamana Write Attribution M0–M3 Analysis

## 1. The R=96 vs R=32 Discovery

M2 运行时审计揭示了此前所有跨系统写放大分析中最关键的遗漏：OdinANN 的 R（最大邻居数）为 96，DGAI 为 32。这不是算法差异——它是 base index 构建时选定的图参数，直接决定了每次 insert 的 scheduled repair fanout。

这意味着五点轨迹中观察到的 4.26× 端到端写放大比（CP20, 204.6 vs 48.0 KB/replacement）不能被解读为"online visibility 的代价"。其中至少 3× 来自 R 本身：每次 insert，OdinANN 固定调度 96 条邻居记录的潜在修复，DGAI 只调度 32 条。这是一个结构性的基数差异，与 visibility 机制无关。

## 2. M2 乘法分解

M2 用逐计数恒等式把 neighbor-repair-only 物理写入拆成三个无重叠的乘法因子：

$$\text{touches/N} = \frac{\text{scheduled records}}{N} \times \frac{\text{unique pages}}{\text{scheduled records}} \times \frac{\text{touches}}{\text{unique pages}}$$

| N | Fanout ratio | Page-mapping ratio | Temporal-rewrite ratio | Product | Physical ratio |
|---:|---:|---:|---:|---:|---:|
| 50K | 3.000 | 1.596 | 1.199 | 5.741 | 5.741 |
| 400K | 3.000 | 0.668 | 2.512 | 5.036 | 5.036 |

关键观察：
- **Fanout 恒为 3×**：这是 R=96/32 的直接后果，在所有规模下不变
- **Page-mapping 随 N 反转**：50K 时 OdinANN 访问更多 unique pages（1.596×），400K 时由于覆盖饱和反而更少（0.668×）
- **Temporal rewrite 随 N 急剧上升**：从 1.199× 到 2.512×，成为大 N 下的主要额外放大器
- **400K 的高 rewrite 不是热点主导**：92.71% 的 neighbor-only pages 被重复触及，但 top 1% 只占 2.73% touches

## 3. M3：Queue Supersession = 0

M3 是一个干净的否定性结果。22.5M 个 neighbor-only page version 中：
- superseded_before_enqueue = 0
- superseded_while_queued = 0
- superseded_while_inflight = 0

原因是结构性的：两套实现都在完整页 RMW 前获取 page lock，直到后台 write completion 后才释放。OdinANN 虽然有更深的 queue（max 14 tasks / 573 neighbor pages），但这些都是不同 page keys 的并行，not 同一 page 的可合并写入。

这意味着 M2 观察到的 stage-wide temporal rewrite（OdinANN-400K: 5.0×）全部是 completion-后的顺序重写，不是可以通过 queue coalescing 消除的冗余。"利用现有 background queue 做 same-page pre-submit supersession"这个方向可以 Kill。

## 4. 成本结构清单

从 M0/M1 的 scale matrix（50K/100K/200K/400K），成本结构已经清晰：

**固定成本（与 N 无关）**：
- DGAI publish: 精确 6.005 GB
- OdinANN publish: 精确 8.480 GB（含 shadow copy）
- Publish ratio: 恒定 1.412×

**边际成本（随 N 线性但斜率不同）**：
- Target + shared-page: 两系统均精确 4096 bytes/replacement
- Neighbor-repair-only: DGAI 22.4→35.1 KB/repl, OdinANN 128.6→176.7 KB/repl
- 差距全部来自 neighbor-repair-only

**Recurring ratio 随 N 增长**：2.062→2.655→3.279→3.728×，因为固定 publish 成本被摊薄后，边际 neighbor-repair 差距占比越来越大。

## 5. 研究方向评估

五点轨迹后 Gpt 把候选问题定为"online visibility 与写放大的冲突"。M0–M3 的发现需要修正这个 framing：

**可以确认的**：
- 两系统的 neighbor-repair 写入差距是真实且可精确量化的
- 差距的主导层是 scheduled repair fanout（3× from R）
- Queue coalescing 在当前锁结构下无法消除任何写入

**不能确认的**：
- 写放大差距是否是 online visibility 的因果代价——R=96 vs R=32 是构建参数差异，不是 visibility 机制
- Temporal rewrite 是否可通过延迟写回减少——lock 持有到 completion 是当前实现的选择，但改变它需要新的 durability contract
- matched-R 后差距是否仍显著——M3 的可行性审计显示技术可行（两套 CLI 都支持 R32/R96），但尚未构建

**Matched-R 是下一步的必要前提**。如果 R=32 的 OdinANN 和 R=96 的 DGAI 在相同 N 下的 neighbor-repair 差距缩小到 <2×，那么写放大问题可能主要是一个参数选择问题，不是一个系统设计问题。反之，如果 matched-R 后差距仍然显著，那才能开始讨论 I/O engine、search/prune 或 visibility 机制的贡献。
