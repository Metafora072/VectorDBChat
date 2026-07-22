# R4 A−1 Necessary-Phenomenon Results

日期：2026-07-22

六个探针均只问“是否存在进入 A0 的必要条件”，不把小规模正现象当作论文证据。

| 候选 | 数据与测试 | 关键结果 | A−1 裁决 |
|---|---|---|---|
| P04 ranking-risk precision | 100K MiniLM，150 train + 150 test，平均 4 bits | uniform 4-bit Recall@10 `0.9473`；train-risk mixed `0.8240`，MSE mixed `0.8133`，random mixed `0.8100`；test-risk oracle-leak `0.9833` | **A−1 ORACLE PASS / HOLD**：oracle headroom 明确存在；被否定的只是当前 static train-risk estimator。没有可部署且区别于 progressive rerank 的机制，故不进入本轮 A0。 |
| P05 query-in-flight | 120 个真实 Quora query 的 25/50/75/100% 前缀，对 100K corpus | 75% 前缀与最终向量 cosine `0.8156`；最终 top-10 在 prefix top-100 的 coverage 均值 `0.7642`、p10 `0.29`，top-500 均值 `0.8842`、p10 `0.59`；完整 query 前 sound gap certificate 为 `0%` | **KILL-MECHANISM**：尾部 query 无法安全复用；剩余方案只是不可验证的 speculative retrieval。 |
| P02/P09 stable top-k | 60K MiniLM，4 个 HNSW build，240 queries | ef=80 时 recall `0.9887`，pairwise Jaccard `0.9811`，平均仅 `0.118/10` replacements，any-swap query `6.67%`；`71.5%` churn item 在 exact kth 的 `0.01` 内 | **HOLD，低优先级**：均值 churn 小，但本实验同时改变 seed 与 insertion order，未真正执行 fixed-seed/fixed-order 对照；near-tie 占比反而支持 epsilon-indifference 现象。 |
| P03 motion-bounded | 60K×128 benchmark；10/20% moved；位移半径为 median kth 的 0.05/0.1/0.2 | 20% moved、0.1 radius 时 stale recall `0.9288`，最小 sound candidates p50 `292.5=29.25k`，而 old top-50 coverage `1.0`；0.2 radius 时 p50 `4524.5=452k` | **GO A0**：小/中位移存在选择性区间，但必须击败 old-order overfetch。 |
| P10 payload speculation | 100K graph walker，300/3000 expansions | 3000 expansions 的 ANN recall 仍仅 `0.57`；完整覆盖最终候选需 `47%–92%` wasted payload reads | **INVALID A−1 / KILL current form as generic prefetch**：低 recall walker 不能裁决高 recall search；若无 ANN-specific survival mechanism，该提案仍只是通用 prefetch。 |
| P01 structural fidelity | 2,504 MovieLens semantic vectors，k=15，三种相同 edge-recall 扰动 | directed edge recall 同为 `0.8` 时，低阶 eigenvalue L2 error 从 `0.0171` 到 `0.1154`，相差 `6.76×` | **A−1 PASS / HOLD-high-risk**：错误位置确实重要；NeurIPS'23/ICML'25 优化 fully-connected kernel graph，与 kNNG critical-edge discovery 极近但不能直接写成同构。缺少主动发现漏边的算法，故不进入本轮 A0。 |

## A−1 结论

- 修正门禁确实发挥了作用：P01、P03 出现可复现正现象，P04 也通过 oracle-headroom gate。
- 正现象不自动等于可发表机制。P01/P04 没有找到可与最近机制分开的可执行算法，因此只进入 backlog；P03 进入 A0。
- A−1 只杀当前必要条件或当前机制；这里不把 P01/P04 的 HOLD 写成候选级永久 KILL。

原始结果均位于 `results/`；脚本位于 `a_minus_1/`。
