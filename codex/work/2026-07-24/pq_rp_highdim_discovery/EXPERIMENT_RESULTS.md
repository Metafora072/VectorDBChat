# PQ-RP-HIGHDIM-DISCOVERY Results

**Date:** 2026-07-24  
**Status:** complete  
**Scope:** idea-discovery characterization only  
**Dataset:** GIST1M-960D  
**GPU:** 0

## Protocol

This run preserves the archived `PQ-RP-HIGHDIM-A0` and its
`STOP-CANARY` decision. It reuses the audited GIST1M query/ground-truth
files, one byte-identical full-precision R64/L100 graph, and the existing
PQ16/PQ32/PQ64 artifacts. No graph or PQ artifact was rebuilt.

The frozen matrix was:

```text
PQ16 / PQ32 / PQ64 / Exact
× L={50,100,200,400,800}
× full 1,000 queries
× W=4, K=10, one thread, zero node cache
```

Each representation ran twice. If either QPS or p50 drift exceeded 25%
at any `L`, the whole multi-`L` process for that representation ran a
third time. Two-run centers are arithmetic means; three-run centers are
medians.

## Complete RP-memory curve

QPS and latency entries are centers with `[min,max]`. `Reads` and Recall
are deterministic across repeats.

| Rep. | L | Recall@10 | Reads/query | QPS [min,max] | p50 ms [min,max] | p99 ms [min,max] | Nav DRAM |
|---|---:|---:|---:|---:|---:|---:|---:|
| PQ16 | 50 | 36.01% | 67.25 | 268.70 [259.22,278.19] | 3.09 [3.04,3.13] | 7.04 [6.63,7.44] | 16 MB |
| PQ16 | 100 | 46.22% | 114.90 | 137.15 [134.53,139.76] | 5.65 [5.50,5.81] | 11.56 [11.50,11.62] | 16 MB |
| PQ16 | 200 | 57.82% | 213.09 | 86.19 [81.93,90.46] | 9.78 [9.64,9.93] | 18.86 [18.50,19.22] | 16 MB |
| PQ16 | 400 | 69.27% | 411.59 | 43.08 [43.03,43.13] | 18.92 [18.88,18.96] | 36.22 [36.09,36.34] | 16 MB |
| PQ16 | 800 | 80.78% | 810.37 | 23.01 [22.63,23.39] | 36.96 [36.69,37.22] | 68.69 [68.55,68.83] | 16 MB |
| PQ32 | 50 | 54.42% | 66.16 | 253.14 [244.70,261.58] | 3.26 [3.21,3.30] | 7.09 [7.06,7.11] | 32 MB |
| PQ32 | 100 | 66.95% | 113.93 | 162.42 [155.83,169.01] | 5.47 [5.45,5.50] | 9.97 [8.44,11.51] | 32 MB |
| PQ32 | 200 | 79.21% | 212.38 | 83.44 [77.61,89.26] | 10.35 [10.25,10.44] | 19.23 [17.80,20.66] | 32 MB |
| PQ32 | 400 | 88.75% | 410.94 | 43.32 [41.51,45.12] | 19.70 [19.48,19.91] | 37.71 [37.46,37.97] | 32 MB |
| PQ32 | 800 | 94.83% | 809.73 | 20.62 [20.30,20.95] | 40.14 [39.42,40.86] | 75.28 [75.11,75.44] | 32 MB |
| PQ64 | 50 | 69.38% | 65.75 | 215.73 [215.48,215.98] | 3.68 [3.66,3.71] | 7.68 [7.66,7.70] | 64 MB |
| PQ64 | 100 | 81.78% | 113.73 | 134.77 [131.04,138.50] | 6.19 [6.14,6.25] | 12.10 [12.01,12.19] | 64 MB |
| PQ64 | 200 | 91.05% | 212.00 | 75.58 [74.23,76.94] | 11.31 [11.30,11.32] | 21.00 [20.77,21.24] | 64 MB |
| PQ64 | 400 | 96.82% | 410.64 | 37.92 [35.19,40.65] | 22.04 [21.56,22.53] | 40.95 [39.77,42.12] | 64 MB |
| PQ64 | 800 | 99.08% | 809.38 | 18.84 [16.92,20.76] | 46.87 [42.48,51.25] | 79.29 [77.81,80.78] | 64 MB |
| Exact | 50 | 88.80% | 64.00 | 163.62 [83.10,186.29] | 5.22 [4.85,11.91] | 10.35 [9.87,20.62] | 3.84 GB |
| Exact | 100 | 94.70% | 111.80 | 85.36 [78.71,106.49] | 10.15 [9.28,10.54] | 17.64 [11.10,25.34] | 3.84 GB |
| Exact | 200 | 98.24% | 210.20 | 51.45 [41.21,54.38] | 17.90 [17.12,20.16] | 30.18 [30.15,35.03] | 3.84 GB |
| Exact | 400 | 99.44% | 408.89 | 28.44 [26.10,29.42] | 34.54 [33.61,35.15] | 40.49 [38.59,58.12] | 3.84 GB |
| Exact | 800 | 99.82% | 807.68 | 13.33 [12.58,13.84] | 68.92 [67.41,71.41] | 112.92 [112.50,121.74] | 3.84 GB |

## Conditional repeats and stability

- PQ16, PQ32, and PQ64 did not trigger a third run. Every QPS and p50
  drift was at most 25%, so their centers use two-run arithmetic means.
- Exact triggered a third full multi-`L` run because L50 had 96.9% QPS
  drift and 128.3% p50 drift between runs 1 and 2.
- Exact uses the three-run median. At every `L`, at least one pair of
  runs agreed within 25% on both QPS and p50, so it is not marked
  `PERFORMANCE-UNSTABLE`.
- PQ64 L800 was the closest non-trigger: 22.7% QPS drift and 20.6% p50
  drift.

## Threshold-matched Pareto comparisons

The `L` grid is coarse. These are conservative "same threshold or
higher Recall" comparisons, not strict equal-Recall matches or
interpolated estimates.

| Pair | Target | Lower precision | Higher precision | Reads | Comparisons | Hops | QPS | p50 | p99 | DRAM delta |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| PQ16→PQ32 | 80.5% | PQ16 L800, 80.78% | PQ32 L400, 88.75% | −49.29% | −46.23% | −48.97% | 1.883× | −46.71% | −45.10% | +16 B/vector |
| PQ32→PQ64 | 94.5% | PQ32 L800, 94.83% | PQ64 L400, 96.82% | −49.29% | −46.27% | −48.97% | 1.839× | −45.08% | −45.60% | +32 B/vector |

The PQ32→PQ64 DRAM increment extrapolates to 3.2 GB at 100M vectors and
32 GB at 1B vectors. This is the motivation gap: uniform PQ64 produces a
large frontier shift, but its memory cost is material at scale.

A post-hoc paired-query audit found a PQ64 L400 minus PQ32 L800
Recall@10 delta of +1.99pp (10,000-sample bootstrap 95% CI
[+1.50,+2.48]pp; 231 wins, 667 ties, 102 losses). This confirms that the
higher Recall is not an aggregate rounding artifact. The bootstrap is
not part of the preregistered PASS gate.

## Decision

```text
PASS-DISCOVERY-UNIFORM-PRECISION-TRADEOFF
```

The preregistered discovery gate is met: in the full-1K high-Recall
common interval, PQ64 reduces reads by more than 30% relative to the
conservative PQ32 threshold point, with no QPS or tail-latency
regression. This is sufficient to preserve a mixed-precision
idea-discovery candidate, not to validate mixed precision itself.

The result does **not** establish generality beyond GIST, causality from
dimension alone, node/query-level selectivity, or a paper-level
performance claim.

## Cost and integrity

- Wall time: 17m24.52s (1,044 seconds), below the 90-minute hard wall.
- Peak RSS: 3,782,912 KiB (3.61 GiB).
- GPU use: 0.
- New NVMe result footprint: approximately 9 MB; filesystem remains at
  approximately 333 GB used and 1.4 TB available.
- Integrity audit: 2×5,000 raw query-point rows for PQ16/PQ32/PQ64 and
  3×5,000 for Exact; every `(representation, repeat, L)` block contains
  exactly 1,000 queries.

## Independent result-to-claim review

The independent reviewer returned `claim_supported=yes`,
`confidence=high` for the narrow GIST characterization claim and agreed
with `PASS-DISCOVERY-UNIFORM-PRECISION-TRADEOFF`. It explicitly rejected
strict `matched-recall` wording: the evidence is a no-lower-Recall
Pareto-dominating threshold comparison. It also confirmed that mixed
precision, selectivity, cross-dataset generality, and paper-level
superiority remain unsupported.
