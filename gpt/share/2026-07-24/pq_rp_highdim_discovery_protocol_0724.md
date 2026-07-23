# PQ-RP-HIGHDIM-DISCOVERY 执行规范

## 1. 定位

原 `PQ-RP-HIGHDIM-A0` 及其 `STOP-CANARY` 结论保持归档，不修改、不补跑。

本轮是独立的 idea-discovery characterization，只回答：

> GIST960 上，增加普通 PQ 码长能否用更小的搜索列表 `L` 显著改善 Recall–Performance–DRAM frontier，从而形成后续 mixed-precision idea 的研究动机。

本轮结果不得作为论文级性能结论。

## 2. 复用与禁止项

直接复用现有 GIST1M-960D：

- full-precision R64/L100 graph；
- PQ16/PQ32/PQ64 artifacts；
- Exact navigation artifacts；
- 已审计的 queries 和 ground truth。

禁止重新构图或重新训练 PQ。禁止加入：

- 新的 `L/W` 点；
- OPQ、RPQ、RaBitQ、LVQ、LeanVec；
- mixed-precision implementation；
- selective exact；
- residual refinement。

所有大文件与 raw artifacts 继续放在 `/dev/nvme8n1` 对应的数据目录。

## 3. 核心实验矩阵

```text
PQ16 / PQ32 / PQ64 / Exact
× L={50,100,200,400,800}
× full 1K queries
× W=4, K=10, one thread, zero node cache
```

每个 representation 在一次 index load 中批量运行全部 `L`。

## 4. 条件重复规则

### 4.1 默认两次

每个 representation 默认运行两次完整 multi-L 进程。

若所有 `L` 点的 p50 与 QPS 漂移均不超过 25%：

- 不补跑；
- 中心值取两次算术平均；
- 同时报告 min/max；
- Recall、reads、comparisons 按确定性结果报告。

漂移定义：

```text
abs(v1 - v2) / min(v1, v2)
```

### 4.2 条件第三次

若任意 `L` 点的 p50 或 QPS 漂移超过 25%，对该 representation 的完整 multi-L 进程补跑一次。

不得只补异常的单个 `L`，避免不同加载与缓存状态混入同一条曲线。

三次结果：

- 中心值取三次中位数；
- 报告完整 min/max；
- 检查是否至少有两次在 25% 内一致。

### 4.3 持续不稳定

若三次中没有任意两次在 25% 内一致：

- 标记 `PERFORMANCE-UNSTABLE`；
- 保留 Recall、reads、comparisons、hops 和 DRAM 曲线；
- QPS、p50、p95、p99 只作为带范围的辅助信息；
- 不得依赖延迟或 QPS 作 GO/KILL。

本轮不因单个性能点漂移停止完整矩阵。

## 5. 指标与判断优先级

Idea discovery 阶段优先使用：

1. Recall@10；
2. reads/query；
3. comparisons/query；
4. hops/query；
5. PQ resident bytes。

QPS、p50、p95、p99 用于确认端到端收益。

重点比较：

```text
PQ16 ↔ PQ32
PQ32 ↔ PQ64
```

在相同或更高 Recall 下，报告：

- `L` 缩小多少；
- reads/comparisons 减少多少；
- QPS/延迟改善多少；
- 额外 DRAM 成本；
- 对 100M/1B 的内存外推。

Canary 中的 `PQ32 L800 ↔ PQ64 L400` 仅为候选对照。Full 后必须用完整 1K queries 重新计算，不得直接沿用 200-query 数值。

## 6. 探索性裁决

允许的结果：

```text
PASS-DISCOVERY-UNIFORM-PRECISION-TRADEOFF
HOLD-DISCOVERY-STRUCTURAL-SIGNAL
HOLD-DISCOVERY-WEAK-OR-UNSTABLE
KILL-DISCOVERY-NO-PQ64-FRONTIER-SHIFT
```

`PASS` 的最低要求：

> 在 full 1K queries 的某个高 Recall 公共区间，PQ64 相对 matched-recall PQ32 稳定减少至少 30% reads，并且没有明显的 QPS 或尾延迟反向退化。

若计时仍不稳定，但 reads/comparisons 降幅足够大，只能裁决：

```text
HOLD-DISCOVERY-STRUCTURAL-SIGNAL
```

无论结果如何，本轮都不能声称：

- mixed precision 已可行；
- 高维数据普遍存在该现象；
- 额外精度收益具有节点级或查询级选择性；
- 论文级 RP 优势成立。

## 7. 时间预算

复用现有 artifacts：

```text
基础两次 Full：20–35 分钟
条件第三次：每个异常 representation 约 3–8 分钟
聚合与报告：15–20 分钟
总计：约 40–70 分钟
hard wall：90 分钟
```

## 8. 对话回报要求

对话中只回报：

- 完整 RP-memory 曲线的核心点；
- 哪些 representation 触发第三次；
- 最终使用平均值还是中位数；
- matched-recall PQ16↔PQ32、PQ32↔PQ64 结果；
- 探索性裁决；
- 实际总耗时。

完整结果、脚本、raw summaries 和图放入 `codex/share/2026-07-24/` 与对应 work 目录。
