# P03 Temporal Connectivity Gap A0 结果

**日期：** 2026-07-23

**主裁决：** `HOLD-P03-STRUCTURE-ONLY`

**资源：** CPU-only，普通 NVMe，SIFT1M，约 12 GB 可再生成快照
**完整工作区：** `codex/work/2026-07-23/p03_temporal_connectivity_a0/`

## 1. 结论

P03 的结构现象真实且高度稳定，但没有形成查询伤害：

```text
chronological streaming
→ directional cross-cohort connectivity deficit     YES
→ grouped-query Recall / search-cost degradation     NO
→ degree-matched Oracle recovery                     NOT ALLOWED
```

因此按 Gpt 预注册阶段门禁早停为 `HOLD-P03-STRUCTURE-ONLY`。没有实现 cross-cohort repair、temporal pruning 或 Oracle edge replacement。

## 2. 严格控制与实现

比较三组最终 active set 完全相同的图：

- `STATIC`：全局随机顺序，一次性静态构建；
- `STREAM-TIME`：C0→C1→C2→C3，每个 cohort 内随机；
- `STREAM-SHUFFLE`：与 STATIC 相同的全局随机顺序，但分四个等大 batch 插入。

所有组使用 `R=64`、`Lbuild=Lsearch=96`、`alpha=1.2`、12 threads、相同 permutation seed，并对 streaming 图执行 final prune，使最终每图均为 1M active nodes、64M directed edges。seeds 为 11/22/33。

在既有 PipeANN harness 中新增：

1. `p03-structure`：只构建和导出最终图，不提前读取 query 指标；
2. `p03_graph_analyzer`：4×4 矩阵、degree-normalized mass、SCC 和 sampled-target shortest paths；
3. 结构 gate 通过后才加入只读 expansion trace 和 `p03_query_a0`。

## 3. 结构阶段：通过

三 seed 平均的 source-degree-normalized edge mass：

| 图 / source | →C0 | →C1 | →C2 | →C3 |
|---|---:|---:|---:|---:|
| STATIC C0 | 0.28779 | 0.24746 | 0.23976 | 0.22498 |
| TIME C0 | 0.46798 | 0.22141 | 0.17264 | 0.13797 |
| SHUFFLE C0 | 0.28796 | 0.24738 | 0.23974 | 0.22492 |
| STATIC C1 | 0.24973 | 0.29779 | 0.23669 | 0.21578 |
| TIME C1 | 0.34350 | 0.32744 | 0.18690 | 0.14216 |
| SHUFFLE C1 | 0.24989 | 0.29769 | 0.23669 | 0.21572 |
| STATIC C2 | 0.23721 | 0.23313 | 0.28966 | 0.24000 |
| TIME C2 | 0.27073 | 0.25828 | 0.29221 | 0.17877 |
| SHUFFLE C2 | 0.23735 | 0.23306 | 0.28963 | 0.23996 |
| STATIC C3 | 0.22559 | 0.21590 | 0.24328 | 0.31522 |
| TIME C3 | 0.23296 | 0.21818 | 0.25338 | 0.29549 |
| SHUFFLE C3 | 0.22572 | 0.21582 | 0.24328 | 0.31517 |

最稳定的 TIME/SHUFFLE 比值：

| Directed cell | Seed 11 | Seed 22 | Seed 33 | Median |
|---|---:|---:|---:|---:|
| C0→C2 | 0.7196 | 0.7204 | 0.7203 | 0.7203 |
| C0→C3 | 0.6137 | 0.6124 | 0.6142 | 0.6137 |
| C1→C2 | 0.7894 | 0.7896 | 0.7899 | 0.7896 |
| C1→C3 | 0.6589 | 0.6582 | 0.6599 | 0.6589 |
| C2→C3 | 0.7450 | 0.7441 | 0.7459 | 0.7450 |

STATIC 与 SHUFFLE 几乎重合，排除了“普通 streaming 就会产生同样矩阵”的解释。所有 9 张图都是一个 SCC，所有 sampled-target cohort pair 的 reach rate 均为 1.0。TIME 的早到晚平均最短距离略增，例如 C0→C3 从 SHUFFLE 2.033 hops 增至 TIME 2.120，但 p95 都为 3。

结构阶段裁决为 `GO-P03-QUERY-EFFECT`，但这不是论文级 PASS。

## 4. Grouped-query 阶段：无查询伤害

10K query 按 exact GT 1-NN cohort 分组，组大小为 C0=2967、C1=3011、C2=3313、C3=709。预注册 query gate：

- Recall@10：中位损失至少 1pp，且每个 seed 至少损失 0.5pp；或
- comparisons / visited：中位增加至少 5%，且每个 seed 至少增加 2%。

TIME 相对 SHUFFLE 的三 seed 中位变化：

| GT cohort | Recall loss (pp) | Comparisons | Visited nodes | Gate |
|---|---:|---:|---:|---|
| C0 | −0.037 | −0.70% | −0.10% | FAIL |
| C1 | 0.000 | −0.71% | −0.10% | FAIL |
| C2 | −0.006 | −1.15% | −0.12% | FAIL |
| C3 | 0.000 | −1.56% | −0.13% | FAIL |

所有 Recall 差异都小于 0.1pp；TIME 的 comparisons 反而略低，visited 基本不变。target-cohort first-entry expansion 和 path transition 虽有变化，但跨 seed 方向不稳定，而且预注册明确禁止这类描述性指标单独通过 utility gate。

## 5. 为什么不做 Oracle

Gpt 的顺序要求是：

```text
structure signal
→ query harm
→ degree-matched Oracle
```

第二段失败，因此 Oracle 的因变量不存在。此时注入 STATIC cross-cohort edges 即使改变路径，也无法证明“恢复查询性能”，只会在事后制造新指标。故 Oracle、repair 和机制设计全部早停。

## 6. 可复现性与资源

- 构建时间：STATIC 95.6–101.6 s；TIME 更新 815.2–827.9 s；SHUFFLE 更新 812.1–827.1 s。
- raw JSONL：`results/full/{structure,query}_metrics.jsonl`；
- gate summaries：`results/full/structure_summary.json`、`query_summary.json`；
- 日志：`logs/full/`；
- 大型 order、edge 与 index 快照位于 NVMe：`VectorDB/data/VectorDB/p03_temporal_connectivity_a0_0723/full/`，不进入 Git。

## 7. 边界与后续

本实验支持的最强表述是：

> 在 SIFT1M 的四段 cohort 和 PipeANN R64/L96 下，chronological insertion 会形成高度可重复的早到晚 directed-edge asymmetry，但该 asymmetry 不造成 cohort-specific Recall 或搜索成本退化。

它不支持“Temporal Connectivity Gap 是一个有 utility 的新 ANN 问题”，也不支持修复算法。除非后续出现独立、真实时间数据集上的查询伤害证据，否则不得通过降低 L、选择 adversarial query 或追加维护机制续命。

独立 result-to-claim 审阅给出 `claim_supported=partial, confidence=high`，确认本轮只支持结构重分配，认可 `HOLD-P03-STRUCTURE-ONLY`、禁止 Oracle，并建议按既定路线转 P10。
