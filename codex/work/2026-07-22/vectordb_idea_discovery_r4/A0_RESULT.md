# R4 A0: Motion-Bounded ANN

## Hypothesis and pre-registered gate

若同一 embedding 空间内只有少量对象小幅移动，则 per-object displacement envelope 可能给出比固定 overfetch 更小、同时 sound 的 fresh top-k 候选集。

进入论文开发的必要门为：至少存在一个工作区间同时满足：

1. stale Recall@10 `<= 0.95`，问题确实非平凡；
2. sound envelope 的 candidate expansion p95 `<= 5k`；
3. 旧排序 top-50 经 fresh-vector rerank 后 Recall@10 `< 0.99`，简单基线确实不足。

## Setup

- 60K MiniLM Quora corpus vectors，160 个 held-out queries，k=10；
- 10%/20% 对象移动；
- random direction 与朝 16 个 workload intent 移动的 coherent stress；
- 位移半径为旧空间 median exact kth distance 的 0.05/0.1/0.2；
- 比较 stale、旧 top-20/50/100/200/500 fresh rerank 与 sound displacement envelope。

## Results

| motion | moved | radius/kth | stale recall | envelope p95 / k | old top-20 | old top-50 | old top-100 |
|---|---:|---:|---:|---:|---:|---:|---:|
| random | 10% | 0.10 | 0.9925 | 2.60× | 1.0000 | 1.0000 | 1.0000 |
| random | 20% | 0.10 | 0.9838 | 4.01× | 1.0000 | 1.0000 | 1.0000 |
| workload-aligned | 10% | 0.10 | 0.9106 | 2.30× | 0.9731 | 0.9994 | 1.0000 |
| workload-aligned | 20% | 0.10 | 0.8838 | 3.50× | 0.9713 | 0.9994 | 1.0000 |
| workload-aligned | 10% | 0.20 | 0.8256 | 21.26× | 0.9069 | 0.9738 | 0.9988 |
| workload-aligned | 20% | 0.20 | 0.7813 | 42.73× | 0.9094 | 0.9900 | 1.0000 |

所有 sound-envelope 查询的 Recall@10 都是 1.0，但这仅验证 triangle-inequality construction；并不说明检索这些候选的实际 index cost 低。

## Initial decision and reviewer correction

初始 gate 为 `FAIL`，但独立审阅指出：sound exact envelope 与无证书的 top-50 empirical recall 不是同保证级比较。该结果只能杀“普通近似质量下胜过 fixed overfetch”的叙述，不能裁决“可认证 bounded-motion enumeration”。因此追加一个不读取全库旧距离的 corrective A0。

存在清楚的 phase transition：

- 界紧时，old top-50/100 已经等价解决问题；
- old top-50 真正不足时，sound envelope 的尾部膨胀到 21–43×k；
- 实现 envelope retrieval 还需要 additive-weighted range/NN 结构或 radius buckets，而 old top-100 只需普通旧索引 overfetch。

## Corrective A0: actual sound enumeration

固定 4,096 个旧空间 Lloyd cells，每个 cell 保存 center、覆盖旧成员的球半径和最大 displacement。查询按

\[
LB(C,q)=\|q-c_C\|-R_C-\max_{i\in C}r_i
\]

best-first 枚举；当下一个 cell 的 lower bound 超过当前 fresh kth 才停止。搜索路径禁止读取全库 `old_dist` 或 exact old order。

固定 gate：160/160 exact；p95 `centroid + fresh point distances <= 6000`；median wall time `<= 0.5×` flat scan。结果：

- exactness：`160/160`，通过；
- p95 distance calls：`64,047`，失败；
- p95 visited cells：`4,047/4,096`；
- median latency：`0.1143 s` vs flat `0.02758 s`，即 `4.15×` flat，失败。

这定位了 oracle candidate-size 与可实现 enumeration 的差异：真正可能改变 top-k 的点很少，但高维球形 cell bound 几乎不能找到它们。

## Final decision

**KILL-MECHANISM：仅否定 motion-expanded spherical-cell certified enumeration。** 不声称 bounded-motion ANN 这个问题在所有未来机制下永久无解；本轮不再用 radius buckets、delta graph 或调 cell 数续命。

复现：

```bash
OPENBLAS_NUM_THREADS=8 OMP_NUM_THREADS=8 \
python3 a0/motion_bounded_a0.py \
  --radius-fractions 0.05 0.1 0.2 \
  --output results/motion_bounded_a0_stress.json

python3 a0/motion_cell_enumeration.py \
  --output results/motion_cell_enumeration_a0.json
```
