# SELECTIVE-OPQ-ORACLE-A0 Stage A Findings

## Status

```text
STAGE-A-COMPLETE
PASS-ALGORITHMIC-SELECTIVITY-SIGNAL
HOLD-STAGE-B-FOR-REVIEW
claim_supported: partial
confidence: high
STAGE-B-BLOCKED
```

## What was tested

- GIST1M-960D, byte-identical frozen graph, official 1K queries and GT.
- Reused OPQ32/64 and trained only OPQ40/48/56 on the same audited 100K rows.
- Five independent `L` values: 50, 100, 200, 400, 800.
- Four per-L selectors: random, visit-frequency, distance-regret, and
  routing-aware.
- Three mixed payload budgets: 40, 48, and 56 bytes/vector.
- Stage-A metrics only: Recall@10, reads/query, and comparisons/query.

## Main finding

Five of 60 mixed points strictly improved Recall, reads, and comparisons over
the same-budget, same-L uniform baseline. Three belong to routing-relevant
selectors. The strongest stable routing-relevant point is:

```text
DISTANCE-REGRET, L=50, budget=56
Recall:      0.8605 -> 0.8732  (+0.0127, +127 hits)
reads:       65.344 -> 64.932  (-0.412, -0.631%)
comparisons: 7486.820 -> 7446.499 (-40.321, -0.539%)
```

Its paired-query bootstrap 95% intervals are positive for hit delta
`[0.056, 0.197]`, reads reduction `[0.154, 0.668]`, and comparisons reduction
`[11.303, 69.967]`.

## Why this is only partial support

- The stable point uses OPQ64 for 75% of nodes, which is weak evidence of
  strong concentration.
- Visit-frequency at the same `L=50, budget=56` gives nearly the same outcome:
  +128 hits, -0.496% reads, and -0.520% comparisons.
- Distance-regret and visit-frequency overlap strongly at that point
  (`Jaccard=0.828`), so quantization sensitivity is not separated from
  hotness.
- Routing-aware's strict `L=50, budget=40` point improves Recall by 0.0151,
  but its paired reads and comparisons intervals cross zero.
- The other distance-regret point at `L=200, budget=56` gains only 9 hits;
  its hit and comparison intervals cross zero.
- All work reductions are below 1%.
- The selector uses test-trace hindsight and was chosen from 60 scanned
  configurations.
- Matched code payload is not matched actual resident memory at 1M nodes.

## Negative-result constraints

Future work must not claim that:

- routing-aware is already validated as the mechanism;
- static selective OPQ is generally effective across workloads or datasets;
- the current selector is deployable;
- matched-payload gains imply a 1M actual-memory win;
- the dual-dense adapter establishes QPS, latency, or system Pareto gains.

## Recommended next gate

Do not run Stage B without review. A smaller Stage A.5 should first freeze the
single primary configuration `L=50, budget=56`, construct selectors on a
calibration split, evaluate on held-out queries, and test the paired
distance-regret versus visit-frequency difference. Only a stable held-out
joint improvement should authorize an OPQ61 actual-memory gate.

