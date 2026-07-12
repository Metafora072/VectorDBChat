# Round 3 Review

# Round 3 Re-evaluation

## 总体判断

Round 2 refinement 已经完成了绝大部分方法与实验设计闭合：

- 问题 anchor 保持不变；
- dominant contribution 仅剩 shared-codebook residual certificate；
- raw/f9 使用 disjoint training documents 和独立 codebook；
- DRAM-resident synopsis、persistent bytes、CPU 与 crossover 都进入统一成本模型；
- Stage A/B 早停明确；
- exact-group/page envelope 的语义已澄清；
- scheduler、angular cap、disk metadata engine 和 P3 均未被偷偷加入。

因此，该方案在概念、范围和工程接口上已经足够成熟，距离直接执行 Stage A 只剩数值证书中的几个局部修正。

但是，我不能按当前公式判为 READY。新的 FP64 方案比上一轮严谨得多，但仍有两个真实的安全漏洞：

1. 从浮点求和结果构造 residual norm 上界时，`s * (1 + gamma)` 并不是严格的反向误差上界；
2. `||q_hat||=1` 对 FP32 归一化后的存储值不严格成立，因而 `A + R` 不一定上界 `Σ|q_i x_i|`。

此外，DRAM control-plane 的 codebook bytes 仍混淆了 persistent FP16 payload 与运行时 decoded-FP32 representation。

这些都是执行规范问题，不要求改动核心机制，但在一个以“exact certificate”为唯一合法性基础的 gate 中必须先修正。

## 评分

| 维度 | 分数 | Round 3 评价 |
|---|---:|---|
| Problem Fidelity | 9/10 | 始终聚焦强压缩 visual late interaction 的 exact inner-page maximum，没有向近似检索或 I/O engine 漂移。 |
| Method Specificity | 8/10 | 数据流、codebook、layout、metadata、CPU、gate 和成本元组均已具体；剩余问题集中在严格数值上界的两个公式。 |
| Contribution Quality | 8/10 | 一个清晰的机制贡献，没有模块堆叠；是否具有论文贡献取决于 f9 结果与 PLAID/WARP 核实。 |
| Frontier Leverage | 8/10 | 恰当地复用 late-interaction、merging、quantization 与 centroid vocabulary，没有强行引入 learned component。 |
| Feasibility | 9/10 | Stage A 的计算、数据和时间预算现实，失败也能快速、明确地终止。 |
| Validation Focus | 9/10 | slack decomposition、held-out replay、f9 survival 和两级早停均直接服务核心 claim。 |
| Venue Readiness | 7/10 | 若 gate、P3 和 prior-art audit 均成功，可形成锐利的系统/IR故事；目前仍未获得机制证据。 |

加权 Overall：

```text
0.15×9 + 0.25×8 + 0.25×8 + 0.15×8
+ 0.10×9 + 0.05×9 + 0.05×7
= 8.25
```

**Overall：8.3/10**

**Verdict：REVISE**

这里的 REVISE 是一个非常窄的执行前修正，不是重新设计方法。完成下面的 certificate patch 后，我认为可以直接执行 Stage A，无需增加新方法或重新扩大 proposal。

## Anchor Check

**Problem Anchor：Preserved。**

方案仍然只回答：

> 对 f9-int8 后仍跨多个 4 KiB pages 的 visual late-interaction object，一个小型 exact synopsis 能否安全排除部分页面，并在计入 control plane 和 CPU 后形成新 Pareto？

没有变成：

- approximate top-k routing；
- 新 outer bandit；
- 通用 multi-vector ANN；
- learned page predictor；
- disk-resident metadata subsystem；
- async SSD implementation。

## Dominant Contribution Check

主贡献现在足够集中：

> corpus-shared codebook 加 per-page residual envelope，作为 exact physical-page admission certificate。

以下组件已正确降级为复用或实验工具：

- k-means；
- Col-Bandit；
- int8；
- Light-style f9；
- codeword-sorted layout；
- sequential/best-upper-bound execution；
- FP64 numerical interval；
- DRAM metadata placement。

没有 contribution sprawl。

## Exact Certificate 复核

### 1. Residual norm 的上界公式仍不严格

设真实 FP64 正项和为 `S`，计算结果为：

```text
s = fl(S), |s-S| <= gamma*S
```

当 `s` 低估 `S` 时，严格反推应为：

```text
S <= s / (1-gamma)
```

而当前使用：

```text
s * (1+gamma)
```

只是一阶近似。因为：

```text
1/(1-gamma) > 1+gamma
```

两者相差高阶项。虽然 FP64 下差异极小且一次 `nextafter` 很可能覆盖，但“很可能”不满足 exact certificate 的定义。

应改为：

```text
s_upper = nextafter64(s / (1 - gamma64_127), +inf)
R64_upper = nextafter64(sqrt(s_upper), +inf)
```

或者使用可证明正确的 exact/compensated sum，再对 sqrt outward round。

### 2. `||q_hat||=1` 不能直接假设

`q_hat = normalize_fp32(...)` 后，组成 `q_hat` 的 FP32 值通常只满足范数接近 1，并不严格等于 1。

因此：

```text
Σ |q_i e_i| <= ||q_hat||_2 * ||e||_2
```

正确上界应使用实际 FP64 计算并向上舍入的：

```text
Q_upper = upper_bound_fp64_norm(q_hat)
```

于是：

```text
sum_abs_qx_upper <= A_upper + Q_upper * R32_disk
```

不能直接使用 `A + R32_disk`。

### 3. `A` 本身也需要向上界化

当前 `A=sum abs(q_i*mu_i)` 同样是 FP64 求和结果，理论上可能略低估真实绝对积之和。建议统一写成：

```text
A_upper = nextafter64(A / (1-gamma64_127), +inf)
```

然后使用：

```text
d_upper = outward_add64(d, gamma64_127 * A_upper)

serving_error =
    gamma32_128 * (A_upper + Q_upper * R32_disk)

U = outward_add64(
        d_upper,
        Q_upper * R32_disk,
        serving_error
    )
```

注意实数域 Cauchy bound 本身也应是：

```text
q·x = q·mu + q·e
    <= q·mu + ||q|| * ||e||
```

所以 `Q_upper * R` 不只属于 serving-error 项，也应替换当前主 bound 中裸 `R32_disk`。如果选择在 query preprocessing 中把 q 重新归一到 FP64 单位向量，则会改变 serving semantics，不如直接计入 `Q_upper`。

### 4. stopping inequality 应明确写正

文本中的：

```text
lower_serving_score <= U
```

更像“尚不能停止”的判定。正式规范应写：

```text
stop cell iff
max_observed_serving_score >= max_unread_page_upper
```

其中 lower 是已观察到的真实 serving FP32 score，upper 是上述 FP64 certificate。相等时可以安全停止。

这些修正属于 **CRITICAL before Stage A**。

## DRAM Control-Plane Cost 复核

当前 persistent synopsis 中 codebook 是：

```text
K × 128 × 2 B FP16
```

但运行时语义定义：

```text
mu_hat = decoded FP16 codeword in FP32
```

因此需要明确采用哪一种内存路径：

### 方案 A：启动时解码并常驻 FP32

```text
persistent codebook = K×128×2 B
DRAM codebook       = K×128×4 B
```

这是最简单、CPU 最有利的模型。

### 方案 B：FP16 常驻，query-time 解码

需要计入：

- K×128×2 B DRAM；
- 每 query FP16→FP32 decode CPU；
- 临时 FP32 buffer bytes。

不能把 persistent FP16 bytes 同时当作 decoded-FP32 DRAM footprint。建议 Stage A 固定方案 A，因为它是乐观、简单且容易审计的上限模型。

还应单独报告每 query 的：

```text
Q × K × sizeof(bound-score)
```

query-codeword score table，以及 page-priority/cell-state bytes。它们不必进入 corpus control-plane bytes，但属于原 gate 要求的 query state。

优先级：**IMPORTANT**。

## Stage A Gate 设计复核

除上述数值修正外，Stage A 已足够具体：

- disjoint 256-document/page training pool；
- representation-specific codebooks；
- deterministic sklearn parameters；
- K=64/256；
- raw-int8 和 f9-int8；
- actual codebook/pair-list serialization；
- full CPU breakdown；
- 0.5–100 µs/page crossover；
- single → multi → exact-page → maxima-page 分解；
- f9 不能跳页则立即停止；
- residual direction 主导则不运行 K=1024；
- Stage B 通过也只允许申请 P3。

我建议把 “residual-direction gap 主导” 的报告方式固定为至少两项，不必增加人为通过阈值：

```text
multi-ball slack / single-ball slack
false-threatening pages:
  single → multi → exact-page
```

裁决可以由 f9 实际 safe pages 和 cost Pareto 主导；slack ratio 用于解释 Kill 原因，不应取代最终页数。

## Simplification Opportunities

**NONE。**

当前方案已经是最小 adequate mechanism。不要在本轮加入：

- angular cap；
- learned residual direction；
- multiple-prototype hierarchy；
- scheduler optimization；
- disk synopsis；
- additional dataset；
- P3。

唯一可做的简化是统一用一个 FP64 outward-bound helper，避免 residual、dot、norm 和 addition 分别实现不一致的舍入逻辑。

## Modernization Opportunities

**NONE。**

这里不需要 foundation-model finetuning、learned router、RL 或 neural bound。复用 frozen ColQwen2/Light-style embeddings 并研究 serving control plane，技术选择是适当的。

## Drift Warning

**NONE。**

本轮的 FP64 arithmetic、DRAM placement 和独立 codebook 都是对原问题的正确执行化，没有扩大或改变问题。

## READY 判定

### 当前文本

**REVISE：尚不能按当前公式直接运行并宣称 exact safety。**

### 完成以下 patch 后

1. residual sum 使用 `s/(1-gamma)` 上界；
2. 实际计算 `Q_upper=||q_hat||`，主 bound 与 serving-error 均使用 `Q_upper*R`；
3. `A` 使用 outward upper；
4. 明确 `stop iff L >= max U`；
5. FP32 decoded codebook 的 DRAM bytes 与 query state 单独计费。

完成后：

**READY to execute Stage A CPU-only gate。**

无需再进行概念 refinement，也无需新增实验。修正可以直接落实到最终 proposal 与实现规范中。

## Remaining Actions

1. **CRITICAL**：修正 residual norm 的反向误差公式。
2. **CRITICAL**：用实际 `Q_upper` 替换 `||q||=1` 假设，并同步修正主 Cauchy bound 与 serving dot error。
3. **IMPORTANT**：向上界化 `A`，明确 stopping inequality。
4. **IMPORTANT**：区分 FP16 persistent codebook 与 decoded-FP32 DRAM footprint，报告 query-state bytes。
5. **MINOR**：将 residual-direction dominance 作为解释性分解，不额外设置替代实际 safe-page/Pareto 的主观阈值。

最终结论：**方案的研究问题、贡献边界、实验范围和成本模型已经足够成熟；它只差最后一个严格数值 patch。修正后应立即执行 Stage A，而不是继续扩展 proposal。**
