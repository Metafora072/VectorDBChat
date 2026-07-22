# Round 2：Compact Fresh-World Distributional ANN

## Primitive

对象 `i` 存 `P_i=N(μ_i,σ_i²I)` 与 multiplicity `S_i`。每次查询独立产生 fresh world，并返回 `max_{s≤S_i}<q,X_is>` 的 top-k。

## Core

用 inverse CDF 惰性抽取对象分数；用 simultaneous UCB `U_i=<q,μ_i>+||q||σ_iβ_i` 转成 `(d+1)`-MIPS，按 UCB 枚举并在第 k 大 realized score 超过所有 unseen bounds 时停止。

## Claim gate

只有同时满足以下条件才进入论文：world Recall≥0.99；p95 枚举≤`50·k`（`k=10` 时为 500）；相对 matched-candidate mean-overfetch 至少 +0.10 Recall；实际 ANN oracle 不破坏 `1-δ` 语义。
