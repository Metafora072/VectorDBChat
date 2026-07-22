# Independent xhigh Review and Convergence

Reviewer agent：`/root/r4_gate_reviewer`
模型/力度：OpenAI Codex secondary agent，xhigh
日期：2026-07-22

## Round 1: critical review

审阅给出的核心批评不是“应多留几个 idea”，而是三类证据口径错误：

1. **A−1 与 candidate-level KILL 混淆**：P04 的 test-oracle `0.9833` 已高于 uniform-4bit `0.9473`，所以 oracle-headroom gate 通过；只能杀 train-risk estimator，不能杀 precision-allocation problem。
2. **保证级不一致**：P03 的 sound exact envelope 不能只因无证书 old-top50 有 `0.9994` empirical recall 而被杀。必须真正实现一个不扫描全库的 sound enumeration。
3. **相邻工作被写成同构**：NeurIPS'23/ICML'25 的 fully-connected kernel similarity graph 与 kNNG critical-missing-edge discovery 极近，但不能仅凭共同的 spectral objective 直接判 P01 同构；Optimistic Routing 与 sound local-ANN missing certificate 也不相同。

其他修正：

- P02 没有单独做 fixed seed/fixed order 对照，故只能 HOLD-low-priority；
- P10 的 walker recall 过低，现有 A−1 无法裁决高 recall search，只能按 current form 缺 ANN-specific mechanism 而 KILL；
- P05 的事后 oracle drift-ball certificate 在 final query 前仍为零，当前机制 KILL 有效；
- P06 的 query-cover/pivot-bound/split 与 dual-tree pruning 同构，KILL 有效；
- P07/P08/P09/P11 均只有 HOLD 级证据，不能把“尚未失败”升级成 finalist。

审阅的 mock score 是 `2/10 Strong Reject, confidence 5/5`，因为当时 ledger 把多项局部机制失败扩大成候选级 KILL。

## Required corrective experiment

审阅只允许复活 P03 的一个最小版本：**Motion-Expanded Certified Top-k Enumeration**。

固定实验，不做 sweep：

- 60K MiniLM、160 queries；
- 20% workload-aligned movement，`r=0.1*d_k`；
- 4,096 个旧空间球形 cells；
- cell bound `||q-c||-R-max(r_i)`；
- 禁止搜索路径访问全量 old distances/exact old order；
- gate：160/160 exact；p95 centroid+point distances `<=6000`；median time `<=0.5×` flat scan。

## Round 2: result and convergence

实测：

| metric | result | gate |
|---|---:|---|
| exact fresh top-10 | 160/160 | PASS |
| p95 centroid + point distances | 64,047 | FAIL |
| p95 cells visited | 4,047 / 4,096 | diagnostic |
| median search / flat time | 4.145× | FAIL |
| cell build | 549.8 s | diagnostic |

Reviewer 最终同意：

- **P03 KILL-MECHANISM**，精确限定为 spherical-cell sound enumeration；高维 cell bounds 实证 vacuous。
- P01/P04/P07 仅是 evidence-level backlog，不是本轮 finalist。
- 本轮最终 `PASS=0, retained=0` 成立，但必须声明只否定当前形式化、当前机制或当前保证—成本路径，不声称问题永久无解。

## Claims matrix

| 结果 | 允许主张 | 禁止主张 |
|---|---|---|
| P03 oracle candidate set 小 | bounded motion 的 affected set 可能很小 | 可以亚线性找到该集合 |
| P03 4096-cell exact | lower bound 是 sound 的 | sound 即高效 |
| P03 访问 4047/4096 cells | 当前球形 cell bound 在该高维数据上 vacuous | 所有可能的 bounded-motion ANN 都不可能 |
| P04 test-oracle 胜 uniform | ranking-risk allocation 存在 oracle headroom | 当前 train estimator 有效或 problem 已被杀 |
| P01 equal recall / unequal spectrum | edge recall 不足以表达 graph quality | 已有可发现 critical missing edges 的新算法 |

## Refinement gate

没有稳定 finalist：P03 corrective A0 已失败，P01/P04/P07 没有可执行的区别性最小机制。按 `research-refine-pipeline` 的 core rule，不在不稳定 thesis 上生成完整实验计划；本轮在这里停止。
