# Findings: PQ-RP-HIGHDIM-DISCOVERY

## Supported

- On the frozen GIST1M-960D graph and coarse `L` grid, uniform PQ code
  length strongly shifts the Recall–reads frontier.
- PQ64 L400 conservatively dominates PQ32 L800 at the 94.5% target:
  Recall is higher (96.82% versus 94.83%) while reads fall 49.29%.
- The structural signal is corroborated by comparisons and hops, which
  fall 46.27% and 48.97%.
- PQ16/PQ32/PQ64 timing is stable under the preregistered 25% rule.
- The uniform-memory cost is material at scale: PQ32→PQ64 adds 32
  B/vector, or 3.2/32 GB at 100M/1B vectors.

## Not supported

- This does not show that mixed precision can reproduce the PQ64 curve
  near PQ32 average memory.
- It does not show that PQ64 benefits concentrate on a small set of
  nodes, queries, or frontier decisions.
- GIST is a dimension-stress control, not a modern semantic embedding
  workload. The result cannot be generalized to high-dimensional vector
  search or attributed to dimension alone.
- The coarse `L` grid yields conservative threshold matches with higher
  Recall on the higher-precision side; it does not provide exact
  equal-Recall interpolation.

## Gate

The preregistered exploration gate supports:

```text
PASS-DISCOVERY-UNIFORM-PRECISION-TRADEOFF
```

The next research gate, if approved separately, must test selectivity
before implementing a large mixed-precision system: determine whether a
small Oracle subset can approach uniform-PQ64 Recall/reads at an average
code budget near PQ32. Novelty and prior-work checks remain mandatory.

## Result-to-claim

The independent reviewer returned:

```text
claim_supported: yes
confidence: high
```

This applies only to the narrow GIST1M-960D discovery claim. The reviewer
agreed with `PASS-DISCOVERY-UNIFORM-PRECISION-TRADEOFF` and required the
comparison to be described as threshold-matched or no-lower-Recall
Pareto dominance, not strict matched Recall. The prospective
mixed-precision algorithmic claim remains untested.

Before an idea-level PASS, missing evidence includes a modern semantic
embedding dataset and a fixed-byte-budget Oracle showing that PQ64
benefits are sufficiently selective to recover near-PQ64 behavior at an
average budget near PQ32.
