# PQ-RP-HIGHDIM-A0 Initial Results

**State**: `STOP-CANARY / FULL-FORBIDDEN`

**Selected dataset**: GIST1M-960D fallback

**Freeze time**: 2026-07-24 01:39:02 CST

**Stop time**: 2026-07-24 02:36:53 CST

## M0: dataset gate

The primary Cohere mirror failed before exact-GT auditing because its full base
matrix had `max |norm-1| = 16.4741764`, versus the frozen `1e-4` limit. No
normalization or repair was attempted.

The GIST fallback passed:

- HDF5/base/query/GT hashes all matched the frozen local manifests.
- Shapes were `1,000,000×960`, `1,000×960`, and `1,000×100`.
- Supplied GT distances had zero monotonicity violations.
- Exact top-100 set overlap was 100/100 for query IDs
  `{0,17,101,257,509,997}`.
- GIST is a dimension-stress control; even a positive full result would have
  been capped at `HOLD-DATASET-SPECIFIC`.

## M1: shared graph and PQ artifacts

- One full-precision R64/L100 graph: 8,192,004,096 bytes, SHA256
  `52827694a9e8dcf64037639e594ed9855f514aa2ebbcb5a4d25f4c1921fa1c37`.
- All PQ16/32/64 prefixes resolve to that same graph realpath.
- Shared deterministic 10% training sample: 100,000 rows, seed 20260724,
  ID SHA256 `44b5794112f5aa4025d930d3403240de99df75a863054a9598ed02f7c157024f`.

| Representation | Bytes/vector | bit/dim | Compression | PQ resident | Median L2² residual | P90 | P99 |
|---|---:|---:|---:|---:|---:|---:|---:|
| PQ16 | 16 | 0.1333 | 240× | 16 MB | 0.7959 | 1.3785 | 2.4183 |
| PQ32 | 32 | 0.2667 | 120× | 32 MB | 0.6540 | 1.1282 | 1.9798 |
| PQ64 | 64 | 0.5333 | 60× | 64 MB | 0.5120 | 0.8823 | 1.5874 |
| Exact-nav | 16 auxiliary + full vectors | 32.1333 total | — | 3.856 GB | — | — | — |

## M2: Canary raw RP-memory points

Recall is identical across the two repeats; performance columns show
`repeat-1 / repeat-2`.

| Representation | L | Recall@10 | QPS r1/r2 | p50 ms r1/r2 | p99 ms r1/r2 | reads/query |
|---|---:|---:|---:|---:|---:|---:|
| PQ32 | 100 | 71.35% | 137.67 / 135.41 | 5.93 / 5.69 | 11.18 / 11.82 | 113.62 |
| PQ32 | 200 | 82.70% | 62.76 / 93.37 | 16.60 / 10.06 | 21.16 / 11.97 | 212.30 |
| PQ32 | 400 | 90.55% | 43.18 / 44.28 | 19.46 / 19.79 | 39.28 / 37.71 | 410.71 |
| PQ32 | 800 | 95.80% | 20.70 / 20.17 | 39.46 / 41.15 | 72.84 / 72.85 | 809.46 |
| PQ64 | 100 | 84.75% | 149.71 / 142.85 | 6.00 / 6.06 | 12.08 / 12.51 | 113.42 |
| PQ64 | 200 | 92.75% | 83.82 / 82.14 | 11.15 / 11.14 | 14.79 / 18.44 | 211.73 |
| PQ64 | 400 | 97.25% | 43.32 / 37.81 | 21.69 / 21.96 | 27.93 / 44.41 | 410.46 |
| PQ64 | 800 | 99.30% | 22.52 / 19.65 | 42.42 / 43.01 | 57.83 / 80.68 | 809.17 |
| Exact | 100 | 96.20% | 83.62 / 100.51 | 10.78 / 9.31 | 18.30 / 17.56 | 111.55 |
| Exact | 200 | 98.85% | 50.45 / 37.78 | 18.90 / 24.22 | 30.80 / 49.28 | 209.98 |
| Exact | 400 | 99.65% | 28.70 / 26.22 | 34.30 / 35.69 | 38.65 / 64.81 | 408.70 |
| Exact | 800 | 99.85% | 14.96 / 14.76 | 66.72 / 67.37 | 73.58 / 83.15 | 807.67 |

### Matched-recall diagnostic

The highest shared 0.5pp grid point reachable in Canary is 95.5%. The
conservative measured comparison is PQ32 L800 (95.8%) versus PQ64 L400
(97.25%).

| Repeat | QPS speedup | reads reduction | p99 reduction | Numerical GO gate |
|---:|---:|---:|---:|---|
| 1 | 2.093× | 49.29% | 61.65% | pass |
| 2 | 1.875× | 49.29% | 39.04% | pass |

This is diagnostic only. It cannot issue
`GO-MIXED-PRECISION-NOVELTY-KILL-MAP`: the Canary stability gate failed, the
full 1K-query matrix was not run, PQ16 was not part of Canary, and GIST is the
fallback control.

## Stop gate

All returned IDs were deterministic, Recall was non-decreasing, Exact L800
Recall was 99.85%, and PQ64 was not worse than PQ32. However:

- PQ32 L200 p50 drift was 65.1%.
- Exact L200 p50 drift was 28.1%.
- The frozen limit was 25%.

Therefore the required result is:

```text
STOP-CANARY
NO GO/HOLD/KILL PAPER DECISION
NO FULL MATRIX
NO THIRD REPEAT
```

## Resources

- GPU: 0.
- M1 wall time: 3,214.67 s (53m 34.67s).
- M2 wall time: 136.34 s (2m 16.34s).
- Graph/PQ peak RSS: 13,009,920 KiB (about 12.41 GiB).
- Canary peak RSS: PQ32 43.75 MiB, PQ64 74.38 MiB, Exact 3.60 GiB.
- Data-root allocated size: about 16 GiB, including the hard-linked 3.84GB
  frozen base.
- Actual NVMe used-space increment since pre-run cleanup: 12,265,299,968 bytes
  (11.423 GiB).
- Current NVMe state: about 333G used, 1.4T available.

## Result-to-claim gate

`claim_supported = no` with high confidence for any paper-level claim from
this run. The data supports only: (i) the Cohere mirror violates its declared
unit-norm assumption, (ii) controlled PQ artifacts were successfully built on
GIST, and (iii) the 200-query diagnostic shows a potentially large PQ64
frontier shift. It does not support a stable full-workload RP-memory curve,
selectivity, mixed precision, or a venue-level algorithm claim.

The configured secondary reviewer model (`gpt-5.4`) was unavailable in this
runtime, so this claim judgment is marked **pending external Gpt review**.
