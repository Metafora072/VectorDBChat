# Round 2 Review

# Round 2 Re-evaluation

## 总体判断

本轮 refinement 已经把最重要的 conceptual gap 补齐：方案不再笼统假设“多球一定更紧”，而是明确区分页内多模态损失与 residual-direction 损失，并允许前者被修复、后者仍失败时立即 Kill；同时，scheduler 已从贡献中删除，f9-int8 被设为不可绕过的生存条件，codebook 使用 disjoint document pool，metadata 和 CPU 也进入同一 Pareto 账本。

因此，就本轮真正需要回答的问题而言——“是否已足够具体，值得执行一次 CPU-only synopsis gate”——答案是 **YES**。它已是一个聚焦、低成本、可证伪的机制实验，而不是系统复活申请。

但 exact safety 仍有一个数值实现缺口：`nextafter_fp32` 一次并不能自动覆盖 FP32 residual norm 计算误差、后续多次加法舍入以及 serving FP32 exact-dot 自身可能向上舍入的误差。因此当前文本还不能称为位级安全已经完全闭合。这个问题可以通过一个很小的执行规范修改解决，不要求改变方法。

## 评分

| 维度 | 分数 | Round 2 评价 |
|---|---:|---|
| Problem Fidelity | 9/10 | 完整保留原始 anchor，只研究强压缩后 exact inner-page MaxSim，未漂移到近似 routing 或 SSD engineering。 |
| Method Specificity | 8/10 | serving vector、layout、metadata、两阶段 K、CPU 路径和早停均已具体；剩余缺口是浮点 interval 实现和 synopsis access placement。 |
| Contribution Quality | 8/10 | 已收缩为一个明确机制：shared-codebook residual certificate；不再把 scheduler、k-means 或 outer bandit包装成贡献。 |
| Frontier Leverage | 8/10 | 正确复用 ColQwen2、Light-style merging、int8 和 centroid vocabulary，也明确不强加 learned router；与 PLAID/WARP 的边界已可操作化。 |
| Feasibility | 8/10 | 额外编码、K=64/256 micro-gate 和 16-query replay 均适合 CPU-only 执行；需要固定 k-means 实现参数和 representation-specific codebook。 |
| Validation Focus | 9/10 | slack source decomposition、f9 survival、两级早停和实际成本形成了非常紧凑的 claim-driven gate。 |
| Venue Readiness | 7/10 | 若 f9 上得到强 Pareto且 closest-work 核实无等价机制，可发展成清晰系统/IR贡献；目前仍只是进入实验的候选。 |

加权 Overall：

```text
0.15×9 + 0.25×8 + 0.25×8 + 0.15×8
+ 0.10×8 + 0.05×9 + 0.05×7
= 8.15
```

**Overall：8.2/10**

**Verdict：REVISE**

这里的 REVISE 不表示应暂停整个方向重新设计。它表示：**CPU-only gate 已值得运行，但运行前应先修正两项执行规范；不需要再增加方法组件或开展新一轮概念扩张。**

## Anchor 与 dominant contribution

### Problem Anchor

**Preserved。**

方法仍然回答：

> 在 Light-style f9 + int8 后仍跨多个 4 KiB pages 的 visual late-interaction object 中，是否能用小型、严格安全的 synopsis 跳过部分物理页并精确恢复 Col-Bandit 请求的 MaxSim cells？

没有变成：

- approximate page routing；
- 通用 DiskColBERT；
- learned query predictor；
- async SSD execution；
- 新的 outer bandit。

### Dominant contribution

现在明显更锋利：

> 使用 corpus-shared codewords 和 per-page residual certificates，为强压缩 visual late-interaction 提供 exact physical-page admission control。

这已经是单一机制贡献。codebook、token merging、int8、Col-Bandit 和 page order 都被正确放回 baseline/reuse 范畴。

## 已解决的 Round 1 问题

### 1. single-ball looseness 的归因已经可证伪

四层分解现在能够回答真正的问题：

```text
single-ball
  → multi-ball L2
  → exact group/page envelope
  → maxima-page oracle
```

如果 single→multi 明显改善，但 multi→exact-page 仍有大 gap，失败原因就是 residual direction；此时 Kill 而不是继续堆 scheduler 或更大系统。这是本轮最重要的改进。

需要澄清一个术语：对固定 page/query，若“group oracle”对每组直接使用真实 token maximum，再对组取 max，那么结果在数值上等于该页的真实 page maximum，其 slack 必然为零。它仍可作为 residual-direction loss 的终点，但报告中应称为 `exact-group envelope / exact-page upper`，避免读者误以为它还保留非零 grouping slack。

### 2. f9-int8 已成为真正的强门禁

Stage A 要求 f9-int8 安全跳页，否则 K=1024 不运行；最终成功又要求计入 codebook、pair lists、padding 和 total CPU 后形成非支配点。这避免了 raw-only result 复活系统，也避免用逐 token 级 metadata 赢得形式上的 page reduction。

### 3. held-out codebook protocol 已基本成立

额外 256 个 disjoint ViDoRe pages 用于 codebook training，原 64/16 trace 完全冻结，解决了最严重的 document leakage 和 top-32 candidate degeneration。

仍需明确：

- raw-int8 和 f9-int8 是否分别训练各自 codebook；
- 若分别训练，成本表只计部署该 representation 所需的一张 codebook，而不是把两张表混入同一点；
- 固定 k-means 实现、seed、初始化、batch size、iteration cap、距离定义和空簇处理。

我建议分别训练，因为 f9 cluster-average vectors 与 raw token geometry 不同；这也给每种强 baseline 最公平的上限。

### 4. scheduler contribution 已正确删除

`sequential` 和 `best-upper-bound-first` 现在只是归因 baseline。无需再减少这一部分；比较二者有助于判断收益来自 synopsis tightness 还是 order。

## 尚未完全闭合的问题

### 1. FP32 exact safety 仍需一个小但关键的修正

当前公式处理了 `q·μ` 的 dot error，但：

1. FP32 计算的 `||x̂-μ̂||₂` 可能低估真实 residual norm，多一次 `nextafter` 不保证覆盖多步减法、平方、求和和开方的累计误差；
2. `dot + radius + epsilon` 的两次 FP32 加法也可能向下舍入，最终一次 `nextafter` 未必覆盖所有舍入；
3. serving exact scan 的 FP32 `q·x̂` 本身可能高于数学实数内积，因此 certificate 需要上界 serving score，而不只是上界实数域 `qᵀx̂`。

最简单、可审计的实现不是继续推复杂 FP32 局部误差，而是：

```text
- x_hat、q_hat、mu_hat 的值仍按 serving 解码为 FP32；
- certificate construction 和 bound evaluation 转成 FP64；
- FP64 中计算 residual norm、q·mu 和完整 U；
- 加入 serving FP32 q·x 的 gamma_128 上舍入项；
- 最后如需存 FP32 radius，再用 outward cast / nextafter 到 +∞；
- stopping comparison 使用 FP64 bound。
```

由于两个 FP32 数的乘积可以被 FP64 精确表示，128 维求和的 FP64 error 很小且容易保守覆盖。这比假设一次 `nextafter_fp32` 足够更可信。

该修改是 **CRITICAL before execution**，但不改变方法。

### 2. synopsis 的访问位置仍稍含糊

文本说：

> pair lists 可以按候选 metadata 访问模型计费，不默认免费驻 DRAM。

但 exact page admission 必须在读数据页之前访问 synopsis，因此最终 gate 应冻结至少一种明确模型：

- **DRAM-resident control plane**：计入完整 DRAM bytes、decode CPU，不产生数据页 I/O；
- 或 **separate packed synopsis I/O**：计入实际 synopsis pages/read bytes，再决定数据页。

不能只报文件大小、同时又在 page trace 中把 pair lists 当作免费可见。对本 CPU gate，最简单和最有利但诚实的选择是 DRAM-resident，并将 codebook、offset table 和全部 pair lists 都计入 DRAM/storage footprint；若在这个上限模型下仍失败，直接 Kill。

优先级：**IMPORTANT**。

### 3. success condition 中“非支配”的计算应固定

建议明确每个 representation 点的 cost tuple：

```text
(
  data pages read/query,
  persistent data bytes + synopsis bytes,
  DRAM control-plane bytes,
  total online CPU/query,
  ranking fidelity
)
```

crossover curve用于把 pages 与 latency联系起来，但不要让“存在某个无限大 page-touch cost”成为通过理由。应至少报告旧 P0 的约 4.47 µs/page break-even 附近，以及一个宽的 page-touch cost range；是否合理由 Pareto 曲线展示，而不是选择最有利单点。

优先级：**IMPORTANT**。

## Simplification Opportunities

方案已经足够紧，**无需再删除核心组件**。仅建议：

1. 把 `group oracle` 重命名为 `exact-group/page envelope`，避免引入一个看似独立的新 oracle。
2. synopsis access 首轮只采用 DRAM-resident 上限模型；不要在同一次 gate 中再扩展 disk-resident metadata engine。
3. outward FP16 radius 仅在 FP32-radius gate 出现正信号后测试，保持当前 staged design。

## Modernization Opportunities

**NONE。**

这里不需要 learned bound、VLM finetuning、RL scheduler 或神经 router。零新增训练组件、复用现有 codebook primitive，是更合适的系统研究选择。angular cap 也不应在本轮与 L2 certificate 并列；若 residual direction 导致 Stage A Kill，应关闭当前候选，再单独决定是否提出新的 synopsis idea。

## Drift Warning

**NONE。**

Refinement 没有改变原问题，反而通过删除 scheduler claim 和 approximate reserve route 进一步收紧了问题边界。

## 是否批准 CPU-only gate

**批准，但需先完成以下 pre-run patch：**

1. 用 FP64/interval-style certificate construction 覆盖 residual norm、bound addition和 serving FP32 exact-dot error；
2. 冻结 synopsis 为 DRAM-resident control plane，并在 cost tuple 中显式计入其 bytes；
3. 固定 raw/f9 分别训练 codebook以及 k-means 可复现参数。

完成这三项后，可以直接执行 Stage A，不需要再做一轮方法设计。

Stage A 的裁决应保持：

- safety violation 非零：实现失败，修实现后重跑；
- f9-int8 读 100%：机制 Kill；
- multi-ball 到 exact-page envelope 的 residual-direction gap 主导：机制 Kill；
- metadata/CPU 在合理 page-cost curve 上明显被 f9 full scan 支配：机制 Kill；
- 只有上述条件都未触发，才允许 K=1024。

即使 Stage A/B 通过，结论也只能是“值得请求 P3”，不能宣称系统、论文或 architecture 已获批准。

## Remaining Actions

1. **CRITICAL**：修正 certificate arithmetic，使其严格上界 serving FP32 MaxSim，而不只是真实数内积。
2. **IMPORTANT**：冻结 DRAM-resident synopsis access model并计入全部 control-plane bytes。
3. **IMPORTANT**：明确 raw/f9 独立 codebook及固定 k-means参数。
4. **MINOR**：将 group oracle 改名为 exact-group/page envelope。
5. **MINOR**：在正结果解释前完成 PLAID/WARP exact residual/page skipping 核实；这不是 Stage A 开跑的 blocker。

最终结论：**方法已经具体到值得一次 CPU-only gate；当前 Verdict 仍为 REVISE，仅因为 exact numerical certificate 和 access-cost model 还需两项小型执行规范修正，而不是因为核心方向仍不清楚。**
