# PageMaxSim Residual Multi-Ball Stage A 决策

**日期**：2026-07-12
**上游材料**：

* `codex/share/visual_pagemaxsim_problem_gate_report_0712.md`
* `codex/share/visual_pagemaxsim_p2_reconsideration_0712.md`
* `codex/work/visual_pagemaxsim_gate/refine-logs/FINAL_PROPOSAL.md`

**裁决**：批准一次 CPU-only Stage A；不批准 P3、完整系统或论文立项。

---

## 1. 独立判断

Codex 对上一轮 P2 结论的修正是合理的：

```text
P2 证明：
single centroid-radius synopsis 无法安全跳页

P2 没有证明：
所有 exact page synopsis 都无法安全跳页
```

上一机制把一个物理页面中的全部 token 包成一个球形外包络，并进一步通过 Cauchy 界抹去了 residual direction。它读取 99.92%–100% 页面，直接说明的是该 synopsis 太松，而不是 PageMaxSim 的 page oracle 不存在。

P1 已经给出两个不同强度的信号：

* raw-int8：约 792.6 页可降到 181.8 页；
* factor-9 int8：约 95.1 页可降到 80.9 页。

因此，允许一次更紧的 synopsis feasibility test 是合理的。该实验成本较低，也直接针对上一机制的失败原因，不属于无边界地堆叠模块。

不过，Codex 的四轮 refinement 得到 9.0/10 只是方案内部审查结果，不能作为放行依据。真正的放行理由只有：

1. P1 的 page oracle 是真实测得的；
2. P2 的失败原因可以被明确归因于几何上界过松；
3. multi-ball 是针对该原因的最小修正；
4. Stage A 成本有限，失败后可以明确关闭这一机制分支。

---

# 2. 当前状态的准确表述

当前状态不能写成：

```text
PageMaxSim 已从 Kill 恢复为有效 Idea
```

准确状态应为：

```text
PageMaxSim 问题存在理论 page oracle；
single-ball exact synopsis 已失败；
residual multi-ball exact synopsis 获准进行一次机制可行性测试。
```

也就是说：

* 问题真实性：部分成立；
* 已有机制：失败；
* 新机制：未验证；
* 系统架构：尚不存在；
* 论文贡献：尚未建立。

---

# 3. 为什么 Stage A 值得执行

## 3.1 它直接攻击上一轮的主要 slack

旧上界的松弛来自：

1. 一个 page 内存在多个视觉或语义 cluster；
2. 一个 centroid 无法保留 residual direction；
3. 大球 radius 被少数离群 token 放大。

新的 shared-codebook residual multi-ball synopsis 将页面表示成若干 residual balls 的并集：

```text
page =
    union of {
        codeword_k + bounded residual_k
    }
```

它至少能回答一个明确问题：

> P2 的失败主要来自 multi-modal page 被错误包成一个大球，还是来自任何低成本 residual certificate 都不可避免的方向丢失？

这个问题具有明确的 Continue/Kill 含义。

## 3.2 实验成本与风险有限

Stage A：

* 不需要 GPU；
* 不实现异步 SSD 引擎；
* 不改 outer Col-Bandit；
* 不开发完整 scheduler；
* 只测试 K=64/256；
* 使用 held-out documents 和 queries；
* 预计 CPU 时间有限。

因此，即使失败，成本也是可接受的。

---

# 4. 必须修正的成功标准

Codex 原计划中“f9-int8 能安全跳页并形成非支配点”方向正确，但仍需要进一步具体化。

## 4.1 非零跳页不等于成功

factor-9 int8 的 page oracle 仅从：

```text
95.1 pages → 80.9 pages
```

理论最多节省约 14.2 页，即约 15%。

按照上一轮实测约 4.47 微秒/page 的参考值，理论页面收益约为：

```text
14.2 × 4.47 μs ≈ 63.5 μs/query
```

因此：

* 跳过一两页没有研究意义；
* 即使接近 oracle，query-codeword dot products、pair-table lookup、bound materialization 和 priority handling 也可能超过页面收益；
* raw-int8 的巨大 page saving 不能单独支撑方向，因为 raw representation 可能被 factor-9 full scan 弱支配。

Stage A 的真正成功条件不是：

```text
能够安全跳过页面
```

而是：

```text
在 factor-9 int8 上，
完整 synopsis/control-plane CPU 与空间成本计入后，
相对 full scan 形成真实可兑现的新 Pareto 点。
```

## 4.2 必须以 factor-9 分支为主裁决

raw-int8 只用于：

* 验证机制能否逼近大 oracle；
* 分析 codebook size 与 residual slack；
* 解释机制行为。

它不能单独让方向存活。

若结果为：

```text
raw-int8 有效
factor-9 int8 无效
```

则当前 PageMaxSim 论文方向仍应关闭。

---

# 5. Stage A 执行顺序

为避免先实现复杂 certificate，再发现几何空间根本不存在，Stage A 应分为三个顺序阶段。

## A0：Exact Group Envelope

先使用真实 codeword assignment，但不使用 residual-radius certificate。

对每个 page/codeword group，直接扫描 group 内真实 token，计算该 group 对 query token 的精确最大值，从而得到一个不受 multi-ball residual bound 影响的 exact group envelope。

该阶段回答：

> 仅把页面从一个大集合拆成 codeword groups，是否已经足以显著收紧 page upper bound？

若 exact group envelope 在 factor-9 上仍接近 100% page reads，则：

* 问题不只是 residual certificate；
* codeword grouping 本身无法兑现 page oracle；
* 无需继续实现复杂 outward-safe multi-ball。

此时直接关闭该机制。

## A1：Residual Multi-Ball Certificate

只有 A0 显示显著空间后，才执行 K=64/256 的安全 certificate。

必须报告：

* certificate violation；
* exact-group envelope 与 multi-ball 的 page-read gap；
* true-max page 已读后仍威胁停止条件的 false-threatening pages；
* residual radius 分布；
* train/test residual gap；
* page 内 codeword occupancy。

该阶段的中心指标是：

```text
multi-ball 能兑现 exact-group envelope 的多少？
```

不能只和旧 single-ball 比较。

## A2：Complete Cost Accounting

只有 A1 在 factor-9 上确实跳页后，才计入完整在线成本：

* query-codeword GEMM；
* page pair lookup；
* bound construction；
* priority state；
* exact token scan；
* persistent synopsis bytes；
* decoded codebook DRAM；
* pair-table DRAM；
* per-query state。

同时报告不同 page service time 下的 crossover：

```text
0.5–100 μs/page
```

但最终判断必须特别标出当前服务器真实页面成本附近的结果，不能只依赖高延迟假设让机制形成 Pareto。

---

# 6. K=1024 的放行条件

K=1024 不应因为 K=64/256 “有一点改善”就自动运行。

只有同时满足以下条件才允许：

1. factor-9 int8 出现安全 page skipping；
2. K=64 → 256 的上界紧度改善具有明确单调趋势；
3. 增加 K 后 metadata 与 query CPU 增长没有快速抵消 page saving；
4. 在当前实测 page latency 附近，成本曲线显示 K=1024 仍可能进入 Pareto frontier；
5. exact-group envelope 与 page oracle 之间仍存在可回收空间。

若 K=256 已显示收益趋于饱和，禁止用 K=1024 继续搜索偶然正结果。

---

# 7. Stage A 的裁决规则

## Continue

只有满足以下条件，才允许请求 P3：

* factor-9 int8 上 certificate 零 violation；
* factor-9 int8 能稳定跳过非微不足道的页面；
* feasible policy 明显逼近 exact-group/page envelope；
* 完整 CPU、DRAM 和 persistent cost 计入后仍存在非支配配置；
* 该配置在当前实测 page cost 附近仍有端到端潜力；
* held-out queries 上结果稳定；
* 收益不是仅由改变 candidate set、token merging 或 representation quality 获得。

## Close Exact-Synopsis Branch

满足任一项即关闭 residual-certified exact synopsis 分支：

* exact-group envelope 本身仍读取接近全部页面；
* factor-9 multi-ball 仍读取接近全部页面；
* residual-direction slack 仍占主导；
* page saving 被 control-plane CPU 抵消；
* metadata 和 DRAM 开销使 factor-9 full scan 占据 Pareto frontier；
* 只有 raw-int8 有效；
* K 增大只增加成本，没有形成稳定收敛趋势。

---

# 8. 失败后的边界

根据修正后的研究标准，Stage A 失败时应当准确表述为：

```text
Residual-certified exact PageMaxSim admission 失败。
```

不应扩大为：

```text
所有 page-aware visual MaxSim 都没有研究空间。
```

但也不允许在同一轮立即继续堆叠：

* angular caps；
* hierarchical codebooks；
* per-token sketches；
* learned routers；
* heuristic thresholds；
* 更复杂 schedulers。

若 exact branch 失败，PageMaxSim 暂时冻结。以后若重开 approximate page admission，必须先形成一个不同的论文故事：

```text
ranking-fidelity / page-I/O / metadata 的受控近似 trade-off
```

而不是为了救当前 exact claim 临时增加模块。

---

# 9. 与解耦架构方向的关系

PageMaxSim Stage A 是一个有限、低成本的 side gate，不应继续占据主研究路线。

Stage A 完成后，无论 Continue 或 Close，下一项主任务都应转入：

```text
decoupled ANN architecture characterization
```

该方向采用已经校准后的研究流程：

1. 先测问题；
2. 再建立故事；
3. 再设计完整机制；
4. 最后进行 related-work positioning。

第一轮只需要量化：

* topology/PQ/coordinate I/O；
* logical 与 physical unique pages；
* reranking coordinate-read amplification；
* search 与 rerank 的串行关系；
* cache hit；
* queue wait；
* compute；
* 与同数据、同 recall coupled baseline 的差异。

不在 characterization 前再次执行 exhaustive novelty Kill。

---

# 10. 最终任务

批准 Codex 执行：

```text
Residual-Certified Multi-Ball Stage A
```

输出：

```text
codex/share/visual_pagemaxsim_multiball_stage_a_report_0712.md
```

报告必须独立给出：

* A0 exact-group envelope；
* A1 K=64/256 certificate；
* A2 complete cost；
* factor-9 主裁决；
* K=1024 是否获准；
* Continue P3 或 Close exact-synopsis branch。

完成 Stage A 后停止 PageMaxSim 工作，等待 Gpt 裁决；不得自行进入 P3 或继续增加 synopsis 机制。
