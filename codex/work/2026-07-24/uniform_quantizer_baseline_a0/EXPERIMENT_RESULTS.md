# OPQ-A0 Results

**Verdict:** `OPQ32-CLOSES-PQ64-GAP`

## Controlled setup

- GIST1M-960D, official 1K queries and ground truth.
- Same 100K shared training rows and row-ID manifest.
- Same byte-identical R64/L100 full-precision graph:
  `52827694a9e8dcf64037639e594ed9855f514aa2ebbcb5a4d25f4c1921fa1c37`.
- `L={50,100,200,400,800}`, W=4, K=10, one thread, zero node cache.
- Same ADC, SSD-node-read and final full-vector rerank path.
- OPQ32/64 use native DiskANN, 20 iterations, seed `20260724`,
  256 centroids/chunk and a 960×960 rotation.

## Complete frontier

Three-run median for OPQ; completed archived PQ results for PQ32/PQ64.

| Representation | L | Recall@10 | reads/q | comparisons/q | QPS | p99 |
|---|---:|---:|---:|---:|---:|---:|
| PQ32 | 50 | 54.42% | 66.16 | 7,512 | 253.14 | 7.09 ms |
| PQ32 | 100 | 66.95% | 113.93 | 12,409 | 162.42 | 9.97 ms |
| PQ32 | 200 | 79.21% | 212.38 | 22,046 | 83.44 | 19.23 ms |
| PQ32 | 400 | 88.75% | 410.94 | 40,477 | 43.32 | 37.71 ms |
| PQ32 | 800 | 94.83% | 809.73 | 75,497 | 20.62 | 75.28 ms |
| OPQ32 | 50 | 79.12% | 65.69 | 7,522 | 143.11 | 7.31 ms |
| OPQ32 | 100 | 89.51% | 113.36 | 12,478 | 82.11 | 12.03 ms |
| OPQ32 | 200 | 95.75% | 211.66 | 22,258 | 59.67 | 19.81 ms |
| OPQ32 | 400 | 98.67% | 410.33 | 41,006 | 36.34 | 36.83 ms |
| OPQ32 | 800 | 99.62% | 809.03 | 76,582 | 20.75 | 73.44 ms |
| PQ64 | 50 | 69.38% | 65.75 | 7,472 | 215.73 | 7.68 ms |
| PQ64 | 100 | 81.78% | 113.73 | 12,402 | 134.77 | 12.10 ms |
| PQ64 | 200 | 91.05% | 212.00 | 22,048 | 75.58 | 21.00 ms |
| PQ64 | 400 | 96.82% | 410.64 | 40,562 | 37.92 | 40.95 ms |
| PQ64 | 800 | 99.08% | 809.38 | 75,712 | 18.84 | 79.29 ms |
| OPQ64 | 50 | 87.22% | 64.94 | 7,445 | 102.25 | 8.40 ms |
| OPQ64 | 100 | 94.55% | 112.81 | 12,432 | 84.41 | 12.53 ms |
| OPQ64 | 200 | 98.11% | 211.15 | 22,225 | 57.11 | 21.13 ms |
| OPQ64 | 400 | 99.45% | 409.75 | 41,000 | 30.97 | 42.19 ms |
| OPQ64 | 800 | 99.83% | 808.47 | 76,613 | 18.68 | 78.85 ms |

## Core comparison

At the highest common 99.0% target:

```text
OPQ32 L800: Recall 99.62%, reads 809.03, QPS 20.75, p99 73.44ms
PQ64  L800: Recall 99.08%, reads 809.38, QPS 18.84, p99 79.29ms
```

OPQ32 therefore reaches and slightly dominates the sampled PQ64 high-recall
frontier while using 36,677,548B rather than PQ64's 64,991,268B of
codes+codebook. At L400 it also improves
Recall from 96.82% to 98.67% at effectively identical reads; QPS is 4.2%
lower but p99 is 10.1% lower.

OPQ32 is not a free speedup at low L. Its 960D rotation costs about
1.14 ms/query, and low-L QPS can be lower than PQ32/PQ64. The verdict is about
the complete high-recall Recall–reads–QPS–p99 frontier, not every point.

## Artifacts and cost

| Item | OPQ32 | OPQ64 |
|---|---:|---:|
| Codes | 32,000,008 B | 64,000,008 B |
| Codebook/pivots | 991,132 B | 991,260 B |
| Rotation | 3,686,408 B | 3,686,408 B |
| Total representation artifacts | 36,677,548 B | 68,677,676 B |
| Training | 5,937.47 s | 6,165.51 s |
| Code generation | 673.11 s | 676.30 s |
| Peak RSS | 12,945,248 KiB | 13,003,932 KiB |
| Rotation mean | 1,139.41 us/query | 1,368.83 us/query |
| Reconstruction L2² median | 0.3278 | 0.1936 |
| Reconstruction L2² P99 | 1.6872 | 1.1487 |

The two training processes ran in parallel. OPQ64 determined the training/
coding wall at 1:54:02. Incremental NVMe use was about 108 MB; GPU use was
zero.

## Stability and protocol event

Both representations triggered the preregistered third repeat. OPQ64 has a
stable pair at every L. OPQ32 has stable pairs at L=50/200/400/800, but no
pair at L=100 satisfies both 25% p50 and QPS gates. Its L100 performance must
therefore be reported as a range:

```text
QPS 79.13–106.73; p50 4.956–8.180ms
```

Recall, reads and comparisons remain deterministic.

At L800 the three-run ranges are QPS 17.03–21.21 and p99
59.28–76.81ms. The high-recall navigation-quality result is strong, but
the speed/latency advantage over the older, non-interleaved PQ baseline has
only medium confidence.

The first automated pipeline hit its 120-minute wall during a partial OPQ32
repeat 2. That partial run was archived and excluded. A search-only recovery
reran complete repeat 2 and the gate-required repeat 3 without retraining or
changing any setting. Total experiment wall including recovery was 129m43s.
The experiment did not finish within the original 120-minute hard wall.

## Supported and unsupported claims

Supported:

- native OPQ is compatible with this frozen-graph DiskANN path;
- on GIST1M-960D, OPQ32 closes the sampled ordinary-PQ64 high-recall gap;
- ordinary PQ is not a sufficient strong baseline for mixed-precision
  selectivity on this dataset.

Not supported:

- OPQ32 dominates PQ64 on every L or every dataset;
- mixed precision can beat the uniform OPQ frontier;
- the result generalizes beyond GIST1M-960D;
- RPQ is weaker than OPQ or safely reproducible.

## Routing

Independent result-to-claim review gives `claim_supported=yes` for the narrow
high-recall baseline claim, with high confidence in quality/work and medium
confidence in QPS/tail latency.

`PASS-A0-OPQ32-CLOSES-PQ64-GAP → HOLD-MIXED-PRECISION`, but this is negative evidence for
immediately implementing the mixed-precision selector. The next gate must use
uniform OPQ32/OPQ64 or stronger routing-aware quantization, not ordinary PQ,
and must still beat uniform PQ40/48/56-style memory points under the same
average-byte budget.
