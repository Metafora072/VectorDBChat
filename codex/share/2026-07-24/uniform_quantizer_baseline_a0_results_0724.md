# UNIFORM-QUANTIZER-BASELINE-A0 结果

## 裁决

```text
OPQ32-CLOSES-PQ64-GAP
RPQ-REPRODUCIBILITY-RISK
```

在 GIST1M-960D、byte-identical frozen graph 和同一搜索路径下，OPQ32
已经达到并轻微支配普通 PQ64 的采样高-recall 前沿。因此普通 PQ32/PQ64
不再是 mixed-precision selectivity 的足够强对照。

## OPQ 核心证据

```text
L=800
OPQ32: Recall 99.62%, reads 809.03, QPS 20.75, p99 73.44ms
PQ64:  Recall 99.08%, reads 809.38, QPS 18.84, p99 79.29ms

L=400
OPQ32: Recall 98.67%, reads 410.33, QPS 36.34, p99 36.83ms
PQ64:  Recall 96.82%, reads 410.64, QPS 37.92, p99 40.95ms
```

OPQ32 完整表示占 36,677,548B，包括 32MB codes、约 0.99MB codebook
和 3.69MB rotation；仍明显小于普通 PQ64 的 64,991,268B
codes+codebook。OPQ query
rotation 平均约 1.14ms/query，已计入 QPS/latency。

完整五点结果见
[`EXPERIMENT_RESULTS.md`](../../work/2026-07-24/uniform_quantizer_baseline_a0/EXPERIMENT_RESULTS.md)。

## 公平性

- graph SHA：
  `52827694a9e8dcf64037639e594ed9855f514aa2ebbcb5a4d25f4c1921fa1c37`；
- 两种 OPQ prefix 均指向同一 graph realpath；
- 同一 100K training rows/IDs、seed `20260724`；
- 20 OPQ iterations、960×960 rotation、256 centroids/chunk；
- W4/K10、单线程、zero cache、同一 ADC/SSD read/full rerank；
- rotation 正交误差低于 `1.8e-6`；
- codes、codebooks、queries 或 base 编码均未修改 graph。

## 成本与稳定性

- OPQ32：training 5937.47s，coding 673.11s，峰值 12,945,248KiB；
- OPQ64：training 6165.51s，coding 676.30s，峰值 13,003,932KiB；
- 两者并行，训练/编码总墙钟由 OPQ64 的 1:54:02 决定；
- 0 GPU；新增 NVMe 约 108MB。

两种表示均因前两次性能漂移触发完整第三次，最终取三次中位数。
OPQ32-L100 三次仍没有满足 25% p50/QPS 门禁的稳定 pair，因此只报告
QPS 79.13–106.73、p50 4.956–8.180ms 范围；高-recall L200/400/800
均有稳定 pair。L800 三次范围仍应披露为 QPS 17.03–21.21、p99
59.28–76.81ms。

自动 pipeline 在 120 分钟时中止于 partial OPQ32 repeat 2。partial
工件已隔离并排除；随后仅补跑完整 repeat 2 和门禁要求的 repeat 3，
没有重训或修改搜索设置。总实验墙钟 129m43s，不能声称在原 120 分钟
hard wall 内完成。

独立 result-to-claim reviewer 判断：

```text
claim_supported = yes（仅限窄化的高-recall baseline claim）
quality/work confidence = high
QPS/tail-latency confidence = medium
route = PASS-A0 → HOLD-MIXED-PRECISION
```

## 对 mixed precision 的含义

本结果没有证明 mixed precision 不可能，但显著抬高了门槛：

1. selector 必须与 uniform OPQ，而不是只与普通 PQ 比；
2. 同平均 bytes/vector 下仍必须严格优于 uniform
   PQ40/PQ48/PQ56/OPQ-style 前沿；
3. 需要证明选择性机制的收益不是 OPQ rotation/codebook 已能吸收的；
4. RPQ 仍是 routing-aware 最强邻近威胁，不能因官方代码复现风险而忽略。

RPQ 的独立审计见
[`rpq_compatibility_audit_0724.md`](rpq_compatibility_audit_0724.md)。
