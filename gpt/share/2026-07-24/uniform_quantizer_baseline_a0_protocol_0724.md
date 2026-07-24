# UNIFORM-QUANTIZER-BASELINE-A0 执行与审计规范

## 1. 当前定位

普通 PQ baseline 已经完成，当前确认：

```text
PASS-DISCOVERY-UNIFORM-PRECISION-TRADEOFF
```

即在 GIST1M-960D、固定全精度图和普通 PQ 下，增加码长能够显著减少达到高 Recall 所需的图扩展和 SSD I/O，但增加 DRAM。

下一步不进入机制设计，先回答：

> 相同或更低码长的强统一量化器，能否消除普通 PQ32→PQ64 的前沿差距？

本轮分为 OPQ 实验和 RPQ 兼容性审计。

---

## 2. OPQ-A0：受控实验

### 2.1 原则

尽量保持以下内容不变：

- GIST1M-960D dataset；
- queries 与 ground truth；
- byte-identical full-precision R64/L100 graph；
- W=4，K=10，单线程，zero node cache；
- 同一 SSD I/O 与 final rerank 路径；
- 相同训练 row IDs；
- 相同 `L={50,100,200,400,800}`。

只改变导航量化表示。

### 2.2 表示矩阵

```text
PQ32
OPQ32
PQ64
OPQ64
× L={50,100,200,400,800}
× full 1K queries
```

普通 PQ32/PQ64 可直接复用现有结果；若执行环境或代码路径发生变化，应做最小 canary 验证，不必重跑全部普通 PQ。

### 2.3 OPQ 实现要求

必须明确记录：

- OPQ 训练实现与版本；
- 旋转矩阵维度；
- 训练样本数量及 row IDs；
- 迭代次数和随机种子；
- query 旋转发生的位置；
- codes、codebooks 与旋转矩阵的实际 resident bytes；
- 是否需要对 base vectors、queries 或 graph 做变换；
- graph 是否仍为原 byte-identical full-precision graph；
- 是否改变 ADC 或搜索器内部逻辑。

若需要旋转原始数据并重新构图，则该路径不再属于严格 frozen-graph 表示实验，必须 hard stop 并先回报。

### 2.4 指标

报告完整：

- Recall@10；
- reads/query；
- comparisons/query；
- hops/query；
- QPS；
- p50/p95/p99；
- PQ/OPQ resident bytes；
- rotation matrix bytes；
- training wall time；
- query rotation CPU cost；
- reconstruction L2²；
- code generation time。

### 2.5 重复规则

沿用 discovery 协议：

- 每种新 representation 默认两次完整 multi-L；
- 任一 L 的 p50 或 QPS 漂移超过 25%，补跑该 representation 的第三次完整 multi-L；
- 两次稳定则取平均；
- 三次则取中位数；
- 持续不稳定时，保留 Recall/reads/comparisons，性能仅报告范围。

### 2.6 结果解释

不预设武断数值门槛，比较完整 Pareto frontier。

允许的裁决：

```text
OPQ32-CLOSES-PQ64-GAP
OPQ32-PARTIALLY-NARROWS-GAP
OPQ32-DOES-NOT-NARROW-GAP
OPQ-A0-INCOMPATIBLE
```

解释：

- `CLOSES`: OPQ32 在高 Recall 区域达到或支配普通 PQ64 的 Recall–reads–QPS–p99 前沿；
- `PARTIALLY`: OPQ32 明显优于 PQ32，但仍与 PQ64 保持清晰差距；
- `DOES-NOT`: OPQ32 与普通 PQ32 基本重合；
- `INCOMPATIBLE`: 无法在 frozen graph 和相同搜索路径下公平接入。

本轮不因 OPQ 失败而自动启动 mixed precision。

---

## 3. RPQ-COMPATIBILITY-AUDIT：只审计，不运行训练

Codex 同步完成 RPQ 代码与实验兼容性审计，但本轮不下载大数据、不训练、不跑完整实验。

### 3.1 必须核对

1. 论文与官方代码仓库；
2. commit/release/version；
3. license；
4. 是否真正包含 DiskANN integration；
5. 支持的数据格式、metric 和最大维度；
6. 是否支持 GIST1M-960D；
7. 是否可复用现有 full-precision graph；
8. 是否需要重新构图或修改 graph topology；
9. RPQ codebook/code 的格式；
10. 能否接入当前 ADC 搜索路径；
11. 32B/vector 的实际含义与额外 metadata；
12. 训练需要的 GPU、显存、CPU RAM、磁盘和时间；
13. 是否需要 training queries、query logs 或 routing samples；
14. 论文训练数据与测试 query 是否严格隔离；
15. native RPQ 中除量化器外是否还有搜索或系统优化；
16. 能否做 controlled frozen-graph comparison；
17. 若只能运行 native fork，如何拆分表示收益与系统收益。

### 3.2 输出

生成：

```text
codex/share/2026-07-24/rpq_compatibility_audit_0724.md
```

至少包含：

- reproducibility verdict；
- frozen-graph compatibility verdict；
- 预计改动文件；
- 最小训练和搜索矩阵；
- 时间/磁盘/GPU预算；
- 风险；
- hard stop 条件；
- 建议先 controlled path 还是 native path。

允许的裁决：

```text
RPQ-CONTROLLED-FEASIBLE
RPQ-NATIVE-ONLY
RPQ-REPRODUCIBILITY-RISK
RPQ-INCOMPATIBLE
```

---

## 4. 本轮执行顺序

```text
M0 OPQ implementation audit
→ M1 OPQ32/64 training and code generation
→ M2 OPQ canary
→ M3 OPQ full matrix
→ M4 OPQ frontier decision

RPQ compatibility audit may proceed in parallel,
but no RPQ training or experiment starts before review.
```

---

## 5. 禁止项

本轮禁止：

- mixed precision implementation；
- per-node selector；
- selective exact；
- residual refinement；
- 新数据集；
- 新 L/W 点；
- 重建 full-precision graph；
- 100M/1B 扩展；
- 将 native system 差异归因于 quantizer。

---

## 6. 对话回报

对话中只汇报：

### OPQ

- frozen-graph 是否保持；
- OPQ32/64 是否成功接入；
- PQ32↔OPQ32 和 PQ64↔OPQ64 的核心 frontier；
- OPQ32 是否达到普通 PQ64；
- 实际训练/搜索耗时；
- 最终 OPQ 裁决。

### RPQ

- 官方代码与版本；
- controlled frozen-graph 是否可行；
- 是否需要 GPU；
- 最小实现工作量；
- RPQ compatibility 裁决。

完整计划、日志和结果放入 share/work 目录。
