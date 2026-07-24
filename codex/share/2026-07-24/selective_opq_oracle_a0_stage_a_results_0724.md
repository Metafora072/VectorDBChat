# SELECTIVE-OPQ-ORACLE-A0 Stage A 结果

日期：2026-07-24

## 裁决

```text
STAGE-A-COMPLETE
PASS-ALGORITHMIC-SELECTIVITY-SIGNAL
HOLD-STAGE-B-FOR-REVIEW

result-to-claim: partial
confidence: high

STAGE-B-BLOCKED
```

Stage A 找到严格数值信号，但论文机制证据较弱，不建议自动进入完整 Stage B。
最强稳定点的 reads/comparisons 收益均不足 1%，且热点基线几乎复现同等收益。

## 执行边界

- 数据：GIST1M-960D，冻结 graph、1K queries、GT 和 100K training rows。
- 复用：OPQ32/64。
- 新训练：仅 OPQ40/48/56。
- `L={50,100,200,400,800}`。
- per-L selectors：random、visit-frequency、distance-regret、routing-aware。
- mixed budgets：40、48、56 bytes/vector。
- 在线判定仅使用 Recall@10、reads/query、comparisons/query。
- 未训练 OPQ45/53/61，未实现 compact layout，未运行 system repeats。

## 正确性与资源

| 项目 | 结果 |
|---|---:|
| graph/query/GT/training hashes | 全部通过 |
| mixed all-low/all-high endpoint parity | 逐项通过 |
| OPQ40 rotation orthogonality max error | 1.61e-6 |
| OPQ48 rotation orthogonality max error | 1.71e-6 |
| OPQ56 rotation orthogonality max error | 2.07e-6 |
| OPQ40/48/56 code bytes | 40,000,008 / 48,000,008 / 56,000,008 |
| sampled simultaneous peak RSS | 约 35.1 GiB，低于 48 GiB |
| final new NVMe bytes | 1,184,093,505，约 1.10 GiB |
| GPU | 0 |
| wall time | 约 2 h 26 min，低于 10 h |
| metrics completeness | 63 files / 75,000 rows，全通过 |

## 五个严格信号

“严格信号”仅表示相对相同 budget、相同 L 的 uniform baseline，同时满足
no-lower Recall、lower reads 和 lower comparisons。

| L | Budget | Selector | Recall delta | Hits delta | Reads reduction | Comparisons reduction |
|---:|---:|---|---:|---:|---:|---:|
| 50 | 40 | routing-aware | +0.0151 | +151 | 0.251 / 0.384% | 15.500 / 0.207% |
| 50 | 56 | visit-frequency | +0.0128 | +128 | 0.324 / 0.496% | 38.911 / 0.520% |
| 50 | 56 | distance-regret | +0.0127 | +127 | 0.412 / 0.631% | 40.321 / 0.539% |
| 200 | 56 | visit-frequency | +0.0029 | +29 | 0.063 / 0.030% | 33.087 / 0.149% |
| 200 | 56 | distance-regret | +0.0009 | +9 | 0.214 / 0.101% | 11.920 / 0.054% |

Random 在 15 个点上无严格信号。四类 selector 的严格信号数分别为：

```text
RANDOM           0/15
VISIT-FREQUENCY  2/15
DISTANCE-REGRET  2/15
ROUTING-AWARE    1/15
```

## 配对稳定性

下表为 1K queries paired bootstrap 95% CI；区间单位分别为每查询 hits、
reads 和 comparisons 的改善。

| L/Budget/Selector | Hits delta CI | Reads reduction CI | Comparisons reduction CI | 判断 |
|---|---:|---:|---:|---|
| 50/40/routing-aware | [0.063, 0.240] | [-0.014, 0.515] | [-14.239, 44.794] | work CI 跨 0 |
| 50/56/visit-frequency | [0.058, 0.200] | [0.070, 0.587] | [9.369, 69.080] | 三项稳定 |
| 50/56/distance-regret | [0.056, 0.197] | [0.154, 0.668] | [11.303, 69.967] | 三项稳定 |
| 200/56/visit-frequency | [0.002, 0.057] | [-0.082, 0.209] | [14.236, 51.597] | reads CI 跨 0 |
| 200/56/distance-regret | [-0.019, 0.037] | [0.063, 0.362] | [-5.897, 29.803] | hits/work CI 跨 0 |

因此，唯一三项稳定的 routing-relevant 信号是
`distance-regret, L=50, budget=56`。

## Selector 结构

### 跨 L 的集合稳定性

以下为同 budget、同 selector 在不同 L 两两 Jaccard 的范围：

| Budget | Random | Visit-frequency | Distance-regret | Routing-aware |
|---:|---:|---:|---:|---:|
| 40 | 0.142–0.144 | 0.597–0.833 | 0.522–0.809 | 0.163–0.512 |
| 48 | 0.333–0.334 | 0.670–0.864 | 0.634–0.878 | 0.498–0.765 |
| 56 | 0.599–0.600 | 0.756–0.911 | 0.688–0.930 | 0.637–0.848 |

### Selector 之间的重叠

25% OPQ64 budget 下，跨五个 L：

```text
VISIT vs DISTANCE: 0.192–0.265
VISIT vs ROUTING:  0.180–0.224
DISTANCE vs ROUTING: 0.131–0.190
```

但在唯一稳定点 `L=50, budget=56`，visit-frequency 与 distance-regret 的
Jaccard 达到 `0.828`。这使“量化敏感性而非热点”成为尚未解决的核心反方。

### Score 分布与访问覆盖

- distance-regret 正分节点比例随 L 从 0.745 增至 0.943；
- routing-aware 正分节点比例从 0.092 增至 0.313，零分比例从 0.837 降至
  0.447；
- 25% budget 的访问覆盖范围：
  random 0.249–0.250、visit-frequency 0.561–0.698、
  distance-regret 0.303–0.453、routing-aware 0.275–0.306；
- 75% budget 的访问覆盖范围：
  random 0.749–0.751、visit-frequency 0.943–0.983、
  distance-regret 0.812–0.930、routing-aware 0.595–0.602。

完整 score percentiles 和每个 budget/L 的覆盖率见原始 CSV。

## 最强反方审稿

1. 唯一稳定 routing-relevant 点给 75% 节点使用 OPQ64，不像“精度集中于少数
   节点”。
2. visit-frequency 在相同点几乎给出同等收益，distance-regret 尚未证明超越
   简单热点。
3. routing-aware 的唯一严格点在 work metrics 上不稳定。
4. 60 点 hindsight 扫描存在多重比较和 selection bias。
5. test-trace selector 不能说明 held-out 或 deployable selector。
6. mixed56 在 1M actual-memory 口径需对比 OPQ61；小于 1% 的 algorithmic
   收益很可能被固定模型开销或 OPQ61 吞没。

## 可支持与不可支持的 Claim

可支持：

> 在固定 GIST1M test trace 上，per-L hindsight distance-regret 在 L=50、
> 75% OPQ64 allocation 下，相对 uniform OPQ56 出现小幅但 paired-bootstrap
> 稳定的 Recall–reads–comparisons 联合改善。

不可支持：

- static selective OPQ 一般有效；
- OPQ64 路由价值集中于少量、可泛化的静态节点；
- 当前 selector 可部署；
- actual-resident-memory 或 system Pareto 已通过。

## 下一步建议

保持：

```text
HOLD-STAGE-B-FOR-REVIEW
DO-NOT-ENTER-STAGE-B-AUTOMATICALLY
```

建议向 Gpt 申请更小的 Stage A.5，而不是直接完整 Stage B：

1. 预注册 `L=50, budget=56`；
2. calibration queries 构建 selector，held-out queries 评估；
3. 直接做 distance-regret 与 visit-frequency 的 paired 差异；
4. 若 held-out 联合改善仍稳定，再优先申请 mixed56 vs OPQ61 的
   actual-memory algorithmic gate；
5. 只有该 gate 通过后才实现 compact layout 和 system repeats。

## 原始结果

- `uniform_summary.csv`：15 个 uniform 点；
- `stage_a_comparison.csv`：60 个 mixed 对比和全部 delta；
- `paired_stability.json`：五个严格点的 paired bootstrap；
- `within_selector_L_jaccard.csv`：120 个跨 L overlap；
- `cross_selector_jaccard.csv`：45 个跨 selector overlap；
- `selector_score_distributions.csv`：15 组完整 score 分布；
- `selector_visit_coverage.csv`：60 组访问覆盖；
- `decision.json`：机器可读 Stage-A 裁决；
- `result_to_claim_review.md`：独立 claim reviewer 结论。

