# SELECTIVE-OPQ-ORACLE-A0 Protocol

## Status

```text
PLAN-ONLY
DO-NOT-RUN-WITHOUT-GPT-APPROVAL
```

## Research question

Under a fixed average resident-memory budget, is the value of higher-precision OPQ concentrated on a selectable subset of graph nodes?

The gate must answer whether a static selective representation can strictly improve the Recall–reads–QPS–p99 frontier over the strongest uniform OPQ representation with the same average bytes/vector.

This is a feasibility/oracle gate. It does not authorize a production selector, mixed-precision storage system, RPQ adapter, new graph, or new dataset.

## Frozen workload

Reuse the existing GIST1M-960D workload and artifacts:

- official 1K queries and audited GT;
- the same byte-identical full-precision graph, SHA `52827694a9e8dcf64037639e594ed9855f514aa2ebbcb5a4d25f4c1921fa1c37`;
- the same deterministic 100K training row IDs;
- seed `20260724`, 20 OPQ iterations and 256 centroids/chunk;
- `W=4`, `K=10`, one search thread and zero node cache;
- optimized dense-rotation V1 path from `DENSE-OPQ-KERNEL-GATE-A0`;
- no graph rebuild, graph mutation, new L/W points, GPU training or test-query leakage into any later deployable selector claim.

GIST remains a dimension-stress control. A positive result is dataset-specific feasibility evidence only.

## Phase M0: compatibility and representation audit

Codex must first determine, without running the full experiment:

1. Whether native DiskANN OPQ fairly supports `40/48/56` chunks at 960D, including uneven chunk boundaries where applicable.
2. Whether OPQ32 and OPQ64 use independent rotations/codebooks and therefore require two query rotations and two ADC tables in a mixed representation.
3. A concrete compact mixed-code layout supporting random access by node ID without allocating 64B for every node.
4. Exact memory accounting for:
   - low-precision codes;
   - high-precision codes;
   - per-node representation tags;
   - node-ID-to-code-offset/rank metadata;
   - both codebooks, centroids and rotation matrices;
   - alignment and allocator padding.
5. The expected query-side fixed cost of preparing both OPQ32 and OPQ64 query representations.

A dense 64B array with unused space for low-precision nodes is not an acceptable equal-memory implementation. An analytically exact memory model is acceptable for plan/canary, but the full gate must use either an actual compact layout or explicitly separate algorithmic and unrealized-layout claims.

## Phase M1: strongest uniform baselines

Train and encode:

```text
OPQ40 / OPQ48 / OPQ56
```

Reuse the existing OPQ32 and OPQ64 artifacts only if their training and optimized query path remain byte- and protocol-compatible. Each uniform representation may learn its own optimized rotation and codebooks; this makes the uniform baseline stronger.

Run:

```text
OPQ32 / OPQ40 / OPQ48 / OPQ56 / OPQ64
× L={50,100,200,400,800}
× full 1K queries
```

Performance repetitions and stability policy must be proposed in the plan. Prefer exactly two interleaved complete repeats, with both raw repeats reported and no automatic third repeat.

Report total representation bytes and effective bytes/vector, not code bytes alone.

## Phase M2: trace-conditioned hindsight selector

The selector may use the official test queries and exact distances because this phase is deliberately an optimistic feasibility bound. Therefore a positive result cannot support deployability or generalization.

Codex must define a mathematically explicit trace-conditioned objective before execution. Requirements:

- The trace source and frozen search policy must be specified.
- The node value must be derived from the measured difference between OPQ32 and OPQ64 on recorded routing/distance events.
- No tuned thresholds, manually selected graph-centrality weights or test-result-driven coefficients are allowed.
- If the objective is additive, selecting the top-K nodes must be proven optimal for that stated trace objective.
- If the true objective is non-additive and only an approximation is tractable, it must not be called a global oracle; label it `TRACE-CONDITIONED-SELECTOR` and state the limitation.
- The plan must include random-node and visit-frequency baselines to distinguish precision sensitivity from simple hotness.
- Node-selection time and trace-generation time must be reported separately from online search.

The plan should prefer a routing-relevant objective over raw vector reconstruction error, but must remain implementable without GPU training. Candidate formulations may include exact-distance estimation regret or routing-order inversions; Codex must justify the final choice and explain whether it is additive.

## Phase M3: equal-budget comparisons

Evaluate static mixed representations at three budgets:

```text
Budget 40B/vector:
75% OPQ32 + 25% OPQ64
vs uniform OPQ40

Budget 48B/vector:
50% OPQ32 + 50% OPQ64
vs uniform OPQ48

Budget 56B/vector:
25% OPQ32 + 75% OPQ64
vs uniform OPQ56
```

The percentages define code payload budgets. Final comparisons must use actual total bytes/vector, including tags, rank/offset metadata, codebooks and both rotations. If overhead shifts the effective budget, compare against an interpolated or nearest stronger uniform baseline without giving the selective method free memory.

For every budget and selector:

```text
L={50,100,200,400,800}
Recall@10
reads/query
comparisons/query
QPS
p50 / p99
query preprocessing cost
actual total bytes/vector
```

The mixed search must compute both query rotations/ADC tables and include their cost in QPS and latency.

## Decision rule

Primary requirement:

```text
At the same actual bytes/vector and no-lower Recall,
selective OPQ must reduce reads and move the end-to-end QPS/p99 Pareto frontier
relative to uniform OPQ.
```

Decision labels:

```text
KILL-SELECTIVE-OPQ
```

if the hindsight/trace-conditioned method fails to produce a strict, repeat-stable Pareto improvement over all equal-budget uniform OPQ40/48/56 baselines.

```text
PASS-HINDSIGHT-SELECTIVITY
HOLD-DEPLOYABLE-SELECTOR
```

only if at least one budget shows a strict repeat-stable equal-memory Pareto improvement. This authorizes a separate held-out-query selector gate, not a full system implementation.

A gain over OPQ32 alone, or a gain obtained by ignoring mixed-layout/query-preprocessing overhead, is not a PASS.

## Required plan response before execution

Codex must reply with:

1. native OPQ40/48/56 compatibility findings;
2. mixed-code layout and exact memory model;
3. the formal trace-conditioned selection objective and whether its optimization is exact;
4. trace-generation and search matrix;
5. correctness audits and failure conditions;
6. expected wall time, CPU/RAM/NVMe budget and hard wall;
7. implementation files expected to change;
8. explicit `PLAN-ONLY / WAITING-FOR-APPROVAL` status.

Do not run training, coding, trace generation or search before approval.
