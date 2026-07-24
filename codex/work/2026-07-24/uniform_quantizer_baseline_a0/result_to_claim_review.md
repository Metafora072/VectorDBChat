# Independent result-to-claim review

## Decision

```text
claim_supported: yes
quality/work confidence: high
QPS/tail-latency confidence: medium
route: PASS-A0 → HOLD-MIXED-PRECISION
```

`OPQ32-CLOSES-PQ64-GAP` is supported only as a GIST1M-960D, frozen-graph,
sampled high-recall baseline conclusion. It is not a paper mechanism PASS and
does not mean OPQ32 globally dominates PQ64.

## Evidence

- L800: OPQ32 has 99.62% Recall vs PQ64 99.08%, effectively identical
  reads, 1.15% more comparisons, and about 43.6% fewer representation bytes.
- L400: at about 410 reads, OPQ32 has 98.67% Recall vs PQ64 96.82%.
- Frozen graph SHA, training rows, code shapes and orthogonal rotations all
  pass artifact audit.

## Limitations

- The 120-minute wall was exceeded; the partial run was excluded and complete
  repeats were rerun, so quality/work remain valid, but the budget claim fails.
- PQ and OPQ performance runs were not randomized and interleaved. Host load
  and SSD/OS state can affect QPS and latency.
- OPQ32 L100 has no stable pair across three runs. Only its deterministic
  Recall/reads/comparisons are reliable.
- Even at L800, report QPS 17.03–21.21 and p99 59.28–76.81ms ranges.

## Allowed claims

- OPQ32 strongly improves ordinary PQ32 navigation quality in this setup.
- OPQ32 reaches ordinary PQ64 in the sampled high-recall region with less
  representation memory.
- The earlier PQ32→PQ64 result does not establish that extra bytes or mixed
  precision are necessary.

## Forbidden claims

- global OPQ32 dominance over PQ64;
- cross-dataset or cross-index generality;
- OPQ novelty;
- mixed-precision superiority or necessity;
- stable QPS/p99 superiority or completion within 120 minutes.

If a mixed-precision candidate cannot identify and exploit a structural gap
that remains after OPQ, and beat the strong uniform memory–Recall–work
frontier, the original mixed-precision mainline should be killed.
