# DENSE-OPQ-KERNEL-GATE-A0 Results

## Verdict

```text
claim_supported = partial
verdict = HOLD-DENSE-OPQ-BOTTLENECK
structured/Fast-OPQ priority = LOW/HOLD
```

The prior `~1.14 ms/query` OPQ rotation is mostly an unoptimized DiskANN native implementation artifact. A simple loop-interchange and reusable scratch baseline reduces 960D rotation-only latency to `~123 us/query`.

However, the result does not support making structured/Fast-OPQ a strong mainline idea yet. In end-to-end search, optimized dense rotation is small at high recall (`L>=400`) and only potentially material around `L=100-200`.

## Setup

- Dataset: GIST1M-960D OPQ32.
- Frozen artifacts: same OPQ rotation, codebook, codes, queries, GT and byte-identical graph as OPQ-A0.
- Search: `K=10`, `W=4`, `L={50,100,200,400,800}`, zero cache, full 1K queries.
- Repeats: exactly 2 complete repeats, no drift-triggered third repeat.
- Threads: `MKL_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`, search threads `1`.
- Backend caveat: this host uses `DISKANN_USE_SYSTEM_BLAS=ON` with system `libblas`, not Intel oneMKL.

## Rotation-Only Microbenchmark

960D actual GIST OPQ rotation, 1000 queries:

| Impl | Meaning | mean us | p50 us | p95 us | Error |
|---|---:|---:|---:|---:|---:|
| V0 | DiskANN native | 1143.66 | 1130.82 | 1190.37 | reference |
| V1 | loop + scratch | 123.15 | 122.80 | 125.98 | max abs `4.47e-08`, rel L2 `1.93e-07` |
| V2 | system-BLAS SGEMV-compatible | 327.17 | 325.56 | 330.81 | max abs `0` |

V1 is the strongest optimized dense baseline on this host. V2 is useful as the protocol's BLAS baseline, but it is slower than V1 here.

## End-to-End Search

Recall, reads and comparisons are unchanged across V0/V1/V2. Key averaged results over two repeats:

| L | Impl | Recall@10 | QPS | p50 us | p99 us | rotation p50 us | rotation share | zero-rotation p50 upper bound |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 200 | V0 | 0.9575 | 53.81 | 11048.5 | 20510.9 | 4839.6 | 43.8% | 1.78x |
| 200 | V1 | 0.9575 | 69.18 | 10408.5 | 18202.8 | 2360.3 | 22.7% | 1.29x |
| 200 | V2 | 0.9575 | 68.54 | 10877.0 | 20709.5 | 1447.2 | 13.3% | 1.15x |
| 400 | V0 | 0.9867 | 35.86 | 19935.3 | 32901.4 | 4917.2 | 24.7% | 1.33x |
| 400 | V1 | 0.9867 | 40.20 | 19922.5 | 32717.7 | 2391.1 | 12.0% | 1.14x |
| 400 | V2 | 0.9867 | 43.16 | 19790.8 | 31590.8 | 1447.8 | 7.3% | 1.08x |
| 800 | V0 | 0.9962 | 21.16 | 38349.8 | 61510.6 | 4877.3 | 12.7% | 1.15x |
| 800 | V1 | 0.9962 | 21.60 | 39262.5 | 61788.6 | 2362.1 | 6.0% | 1.06x |
| 800 | V2 | 0.9962 | 20.85 | 39904.5 | 73816.4 | 1450.6 | 3.6% | 1.04x |

## Interpretation

The old native rotation cost should be killed as a research motivation:

```text
KILL-UNOPTIMIZED-OPQ-AS-RESEARCH-MOTIVATION
```

Structured/Fast-OPQ is not dead, but it is not yet a strong candidate. The only plausible remaining window is low/mid L, especially `L=100-200`, and even there the attribution is not clean enough for a paper mechanism.

## Critical Caveat

Search-process sampled `rotation_us` is much larger than standalone microbench timing for all implementations. For example, V1 is `~123 us` standalone but `~2360 us` sampled in search at L200/L800. This could be wall-time interruption, cache/memory context, or instrumentation artifact. Therefore exact bottleneck percentages are medium-confidence.

## Resource Budget

- Wall time: `665s`.
- GPU: `0`.
- New work artifacts: about `1.8MB`.
- New external result data: about `6.2MB`.

## Artifacts

- Work directory: `codex/work/2026-07-24/dense_opq_kernel_gate_a0/`
- Summary: `codex/work/2026-07-24/dense_opq_kernel_gate_a0/results/curve_summary.csv`
- Decision: `codex/work/2026-07-24/dense_opq_kernel_gate_a0/results/decision.json`
- Result-to-claim review: `codex/work/2026-07-24/dense_opq_kernel_gate_a0/result_to_claim_review.md`
