# 独立研究审阅与最终响应

本轮按 ARIS `research-review` 使用独立审阅代理对三个最强候选做反方压力测试；审阅不负责生成候选，只判断 novelty、importance、algorithmic identity、theory、A0 falsifiability 与 venue fit。

## 审阅评分

评分为 1–5；不是论文 acceptance probability。

| 候选 | Novelty | Importance | Algorithm | Theory | A0 | Venue | 初审 | A0 后 |
|---|---:|---:|---:|---:|---:|---:|---|---|
| Capacity collective ANN | 1 | 4 | 2 | 2 | 4 | 1 | KILL | **KILL-NOVELTY** |
| Compact fresh-world distributional ANN | 3 | 3 | 4 | 3 | 4 | 3 | HOLD / GO A0 | **KILL-MECHANISM** |
| Similarity-proportional sampling | 1 | 3 | 2 | 2 | 3 | 2 | KILL | **KILL-NOVELTY** |

## 审阅人最强意见

### Capacity collective

SIGMOD 2008 的 Capacity-Constrained Assignment 不只是相关应用，而是相同约束、相同 incremental-NN expansion 结构；STOC 2014 还把 ANN data structure 明确放进高维 matching。Hall deficiency 只提供 feasibility signal，不能保证 low-cost assignment；引入 dual/reduced cost 后又回到旧算法。因此即便 A0 节省 candidate edges，也不能成为新 ANNS 论文。

### Fresh-world distributional

这是唯一值得 A0 的候选，因为它把 `S_i` 个潜在样本压成 `μ_i,σ_i,S_i`，并将 simultaneous UCB 化为 `(d+1)`-MIPS。形式上不同于按 marginal probability 排名和冻结一次 sampled database。

但它必须回答两条生死问题：

1. 普通 ANN 返回若干高 UCB items，并不能证明下一个 unseen UCB 不超过阈值；没有可靠 ordered-MIPS oracle，`1-δ` theorem 无法落实。
2. fresh-world `max-of-S` 会偏爱高方差/大 `S_i` 对象。若需要很大不确定性才能体现 mean baseline 的不足，UCB 也会变松并拖入大量候选。

审阅允许的是 **GO A0**，不是 paper-level PASS。

### Similarity sampling

Gumbel-MIPS 已把 softmax sampling 约化为 noisy maximum，RF-softmax 和后续 sampler 又覆盖了近似大规模实现。除非出现新的可证明 sublinear sampler 或完全不同的目标分布，不能继续。

## 对审阅的实验响应

Fresh-world A0 精确验证了审阅人的两条反方：

- `α=0.1`：HNSW-UCB 有效，但 mean-overfetch 只差 0.43 Recall point；创新收益不足。
- `α=0.2`：exact UCB 的 p50 枚举升至目录的 11.2%，而 HNSW-UCB 因 approximate frontier 在 2,048 cap 下 Recall 仅 0.8156；mean-overfetch 反而为 0.9859。
- `α=0.4`：exact UCB p50 枚举 36.8% 目录；HNSW-UCB Recall 0.6953。此时 UCB 优于同 cap mean，但二者都达不到 ANN 可用区间。

所以不能用“换 IVF、加 calibration、再学一个 predictor”修补，因为那会把核心问题改成通用 adaptive computation 或工程 tuning。审阅后的最终裁决为：**零保留，重新发现问题，而不是继续 refine 当前三者。**
