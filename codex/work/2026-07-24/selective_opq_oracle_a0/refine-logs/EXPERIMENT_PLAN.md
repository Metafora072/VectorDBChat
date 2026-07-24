# Experiment Plan

**Problem**: Determine whether OPQ64's routing value is concentrated on a
static subset of graph nodes, first at matched code payload and then under
actual 1M-node resident memory.
**Method Thesis**: If higher precision has genuine node-level selectivity,
multiple independent test-trace selectors should improve Recall–reads–
comparisons before compact-layout and dual-preprocessing system costs are
considered.
**Date**: 2026-07-24
**Revision**: 2, incorporating GPT's oracle/decision-logic review
**Status**: `PLAN-ONLY / WAITING-FOR-GPT-APPROVAL`

No coding, OPQ training, trace generation, or search is authorized by this
revision.

## Accepted Audit Findings

The following findings have passed review and remain frozen:

- Native DiskANN supports OPQ40=`40×24D`, OPQ48=`48×20D`, and native uneven
  OPQ56=`8×18D + 48×17D` at 960D.
- OPQ32 and OPQ64 have independent codebooks, centroids, and rotations.
- A mixed query must execute both centering/rotation paths and build both ADC
  tables.
- The compact low/high arrays plus bit tag and rank-prefix layout supports
  O(1) node access without 64-byte holes.
- The correctness gates for hashes, offsets, ranks, endpoint parity, distance
  parity, preprocessing placement, and allocation accounting remain required.

Current audit verdict:

```text
PASS-COMPATIBILITY-AND-LAYOUT-AUDIT
NEEDS-REVISION-ON-ORACLE-AND-DECISION-LOGIC
PLAN-ONLY
```

## Frozen Workload

- GIST1M-960D, treated only as a dimension-stress control.
- Existing official 1K queries and audited GT.
- Existing deterministic 100K training row IDs.
- Byte-identical graph SHA-256
  `52827694a9e8dcf64037639e594ed9855f514aa2ebbcb5a4d25f4c1921fa1c37`.
- Seed `20260724`, 20 OPQ iterations, 256 centroids/chunk.
- `W=4`, `K=10`, one search thread, zero node cache, V1 dense rotation.
- `Λ={50,100,200,400,800}`.
- No new graph, graph mutation, new dataset, GPU, reranking change, or
  deployable-selector claim.

## Claim Map

| Claim | Minimum Convincing Evidence | Linked Stage |
|---|---|---|
| C1: higher OPQ precision has static algorithmic selectivity | At least one per-L, routing-relevant selector gives no-lower Recall and strictly lower reads and comparisons than the matched-payload uniform OPQ baseline | Stage A |
| C2: the selectivity survives 1M actual memory and system costs | A Stage-A-positive selector passes the OPQ45/53/61 actual-memory algorithmic gate and moves QPS/p50/p99 in both raw repeats | Stage B |
| Anti-claim: a surrogate-specific artifact or hotspot explains the gain | Distance-regret and boundary-inversion selectors are evaluated independently against random and visit-frequency | Stage A |

## Memory Accounting: Two Required Views

The accepted compact layout uses:

```text
low_codes[(N-H)][32]
high_codes[H][64]
high_tag[ceil(N/64)]
rank1_prefix[ceil(N/64)+1]
```

At `N=1,000,000`, aligned tag+rank is 187,584B and the two online OPQ models
occupy 9,347,072B. Therefore:

| Mixed payload | 1M total bytes | 1M bytes/vector | Actual-memory guard |
|---|---:|---:|---|
| 40 B/vector | 49,534,656 | 49.534656 | OPQ45: 49.673472 B/vector |
| 48 B/vector | 57,534,656 | 57.534656 | OPQ53: 57.673536 B/vector |
| 56 B/vector | 65,534,656 | 65.534656 | OPQ61: 65.673536 B/vector |

Every result must report both views:

1. **1M actual resident**: mixed40/48/56 versus OPQ45/53/61. This is the
   actual-memory gate.
2. **Scale-normalized / variable bytes**: mixed40/48/56 versus OPQ40/48/56.
   This is a matched-code-payload diagnostic for a large-N regime, not an
   equal-total-byte claim.

The scale view must still disclose metadata. For general `N`:

```text
B_mix(N,c) =
  c + aligned_tag_rank(N)/N + 9,347,072/N

B_uniform(N,m) =
  m + M_m/N
```

At one billion nodes, the two-model fixed allocation is about
`0.009347 B/vector`, while tag+rank remains about `0.1875 B/vector`.
Consequently mixed40 is about `40.196847 B/vector`, not exactly 40. This
prevents the scale-normalized result from being mislabeled as exact
equal-memory evidence.

If mixed beats OPQ40/48/56 but loses to OPQ45/53/61, the verdict is:

```text
HOLD-SCALE-DEPENDENT
```

It is not a direction-level KILL.

## Per-L Trace Policy

Selectors are constructed independently for each `L`. There are five separate
score vectors per selector family:

```text
s_v^(50), s_v^(100), s_v^(200), s_v^(400), s_v^(800)
```

For each `(q,L)`, the trace source is the deduplicated union of node-distance
events from deterministic OPQ32 and OPQ64 searches under the frozen policy.
Boundary traces additionally record candidate-list insertion/eviction
comparisons. Test queries and exact distances are allowed because this is an
optimistic hindsight gate.

The primary selector evaluated at `L` must use only `s_v^(L)`. Directly summing
all five traces is prohibited in the decision gate because nested searches
double-count events and imply an unstated workload distribution.

An optional aggregate selector may be reported only after Stage A's primary
gate and only as a diagnostic with an explicit uniform-over-L workload:

```text
s_v^agg = (1/5) sum_L s_v^(L) / max(1, |E_L|)
```

It cannot change any PASS/KILL/HOLD label.

## Selector 1: Distance-Regret

For fixed `L`, trace event `e=(q,L,v)` has exact squared-L2 distance `d*` and
ADC estimates `d32`, `d64`. Define:

```text
delta_DR(e) = (d32-d*)^2 - (d64-d*)^2
s_DR,L(v)   = sum_{e in E_L(v)} delta_DR(e)
J_DR,L(S)   = sum_{v in S} s_DR,L(v), |S|=H
```

Top-H is exactly optimal only for this modular surrogate. It is not an oracle
for mixed-search trajectories. Therefore:

```text
distance-regret failure -> KILL-DISTANCE-REGRET-SELECTOR
```

and never, by itself, `KILL-SELECTIVE-OPQ`.

## Selector 2: Routing-Aware Boundary-Inversion

For fixed `L`, record every frozen candidate-list boundary event
`e=(q,L,a,b)`, where incoming/evaluated node `a` is compared with the current
worst retained node `b` immediately before an insertion/eviction decision.
Take the deduplicated union of such boundary pairs from OPQ32 and OPQ64
endpoint traces.

Let the exact ordering label and all-low prediction be:

```text
y_e    = 1[d*(q,a) < d*(q,b)]
y_0(e) = 1[d32(q,a) < d32(q,b)]
```

For a single-node counterfactual:

```text
y_a(e) = 1[d64(q,a) < d32(q,b)]
y_b(e) = 1[d32(q,a) < d64(q,b)]

delta_RA(e,a) = 1[y_0 != y_e] - 1[y_a != y_e]
delta_RA(e,b) = 1[y_0 != y_e] - 1[y_b != y_e]
```

All other nodes receive zero from this event. Then:

```text
s_RA,L(v) = sum_e delta_RA(e,v)
J_RA,L(S) = sum_{v in S} s_RA,L(v), |S|=H
```

This directly scores correction of frozen beam-boundary ranking inversions. It
is independent of squared distance-regret and contains no threshold,
centrality weight, or fitted coefficient. Top-H is exact for this modular
single-node counterfactual objective, but not for the joint, non-additive
mixed-search trajectory; it is named `ROUTING-AWARE-SELECTOR`, not global
oracle.

Failure label:

```text
routing-aware failure -> KILL-ROUTING-AWARE-SELECTOR
```

## Control Selectors

All controls are also per-L:

- `RANDOM`: the first H nodes of a permutation fixed by seed `20260724`;
- `VISIT-FREQUENCY`: top-H by per-L trace event count, ties by node ID;
- `DISTANCE-REGRET`: top-H by `s_DR,L`, ties by node ID;
- `ROUTING-AWARE`: top-H by `s_RA,L`, ties by node ID.

Trace generation, exact-distance computation, score construction, sorting, and
online search are timed separately. Selector construction time is offline and
never hidden in QPS.

## Two Separate Gates

### Algorithmic-Selectivity

Metrics:

```text
Recall@10
reads/query
comparisons/query
```

At no-lower Recall, the mixed method must have both strictly lower reads and
strictly lower comparisons than the applicable uniform frontier. Recall,
reads, and comparisons are deterministic under the frozen policy, so Stage A
uses one complete run per point; performance repetitions are not used to
decide this gate.

### System-Pareto

Metrics:

```text
QPS
p50
p99
dual-query-preprocessing time
compact-accessor time
actual allocated bytes/vector
```

The final compact layout and both rotation/ADC paths must be active inside the
query timer. Exactly two interleaved complete performance repeats are
reported; there is no third repeat.

QPS/p50/p99 may strengthen a PASS only when their direction is favorable in
both raw repeats. System failure may yield `HOLD-SYSTEM-OVERHEAD` or
`KILL-CURRENT-SYSTEM-REALIZATION`; it cannot, by itself, KILL algorithmic
selectivity or the research direction.

## Stage A: Algorithmic Selectivity

### Scope

Train only:

```text
OPQ40 / OPQ48 / OPQ56
```

Reuse audited OPQ32/64. Do not train OPQ45/53/61 and do not implement the final
compact layout.

Stage A may use a dual-dense-code experimental adapter holding the existing
OPQ32 and OPQ64 arrays solely to dispatch node distances. Its memory and system
timings are explicitly non-claimable. It must still compute the correct two
query representations; only Recall/reads/comparisons enter the gate.

### Matrix

Uniform payload frontiers:

```text
OPQ40 / OPQ48 / OPQ56
× L={50,100,200,400,800}
× full 1K queries
```

Mixed:

```text
3 payload budgets
× {RANDOM, VISIT-FREQUENCY, DISTANCE-REGRET, ROUTING-AWARE}
× per-L selector matched to evaluation L
× full 1K queries
```

### Stage-A Decisions

- A selector family that fails every budget/L receives its selector-specific
  KILL label.
- If either routing-relevant selector passes the matched-payload
  Algorithmic-Selectivity gate at any budget/L:

  ```text
  PASS-ALGORITHMIC-SELECTIVITY-SCALE
  GO-STAGE-B
  ```

- If both independent routing-relevant selectors fail at all three budgets and
  all five per-L hindsight gates, despite test leakage:

  ```text
  KILL-SELECTIVE-OPQ-STATIC-NODE-A0
  ```

  This is scoped to static OPQ32/64 node allocation on the frozen GIST1M graph;
  it is not a universal theorem about every adaptive or query-dependent mixed
  quantizer.

Random or visit-frequency success without either routing-relevant selector
does not establish a precision-specific mechanism; verdict:

```text
HOLD-HOTNESS-ONLY
```

## Stage B: Actual Memory and System Gate

Stage B is forbidden unless Stage A returns `GO-STAGE-B`.

### Scope

1. Train OPQ45/53/61.
2. Implement the accepted compact low/high/tag/rank layout.
3. Carry forward only Stage-A-positive routing-relevant selector/budget/L
   configurations; random and visit-frequency remain controls.
4. Run actual-memory Algorithmic-Selectivity against OPQ45/53/61.
5. Run exactly two interleaved System-Pareto repeats.

### Stage-B Decisions

- Scale-normalized pass versus OPQ40/48/56 but actual-memory algorithmic
  failure versus OPQ45/53/61:

  ```text
  HOLD-SCALE-DEPENDENT
  ```

- Actual-memory algorithmic pass, but QPS/p50/p99 fail after dual preprocessing
  and compact access:

  ```text
  PASS-ALGORITHMIC-SELECTIVITY
  HOLD-SYSTEM-OVERHEAD
  ```

- Actual-memory algorithmic pass and favorable QPS/p50/p99 direction in both
  raw repeats:

  ```text
  PASS-HINDSIGHT-SELECTIVITY
  HOLD-DEPLOYABLE-SELECTOR
  ```

- QPS/p50/p99 failure alone cannot produce a direction-level KILL.

Any PASS remains GIST1M-specific and only authorizes a later held-out-query
selector gate.

## Experiment Blocks

### B1: Per-L Trace and Selector Correctness

- Claim: two independent routing-relevant selectors are correctly defined.
- Evidence: raw per-L traces, exact score recomputation, top-H/tie audit.
- Failure: `INVALID`; no search.
- Priority: MUST-RUN after approval.

### B2: Stage-A Uniform Payload Frontiers

- Claim: OPQ40/48/56 are strong same-payload controls.
- Evidence: independent rotations/codebooks and audited artifacts.
- Priority: MUST-RUN.

### B3: Stage-A Algorithmic Selectivity

- Claim: precision-sensitive allocation improves navigation work, independent
  of system layout.
- Evidence: Recall–reads–comparisons against random, frequency and uniform
  frontiers.
- Priority: MUST-RUN.

### B4: Stage-B Actual-Memory Gate

- Claim: Stage-A selectivity survives OPQ45/53/61.
- Evidence: actual allocated bytes and Algorithmic-Selectivity.
- Priority: CONDITIONAL MUST-RUN.

### B5: Stage-B System Gate

- Claim: the compact implementation converts selectivity into end-to-end value.
- Evidence: two raw repeats of QPS/p50/p99 with dual preprocessing.
- Priority: CONDITIONAL MUST-RUN.

## Correctness Gates

1. Recompute frozen graph/query/GT/training-row hashes.
2. Audit OPQ40/48/56 and, conditionally, OPQ45/53/61 shapes, chunk offsets,
   centroid count, and rotation orthogonality.
3. Store separate per-L trace files and reject any selector whose score includes
   another L.
4. Recompute every distance-regret and boundary-inversion score from raw events.
5. Verify top-H exactness for each stated modular objective and deterministic
   node-ID tie-breaking.
6. Stage-A all-low dispatch must reproduce OPQ32 and all-high dispatch OPQ64
   ADC/search results.
7. Stage-B compact layout must exhaustively validate tag/rank/slot uniqueness
   over all 1M nodes and preserve endpoint parity.
8. Sampled mixed distances must match the selected standalone OPQ table within
   `1e-5` absolute error.
9. Stage-B allocation capacity must match or exceed the analytical accounting;
   measured larger bytes control comparison.
10. Both query rotations and ADC tables must be inside Stage-B query timing.
11. Exactly two interleaved Stage-B performance repeats; no partial or third
    repeat.

Any mismatch is `INVALID`, never PASS.

## Expected Implementation Scope After Approval

Stage A only:

- Work-local scripts for OPQ40/48/56 training/audit.
- `pq_flash_index.cpp` and work-local instrumentation for per-L node events,
  boundary pairs, and dual-dense experimental dispatch.
- Work-local selector, audit, search, and analysis scripts.
- No compact persistent layout or allocator optimization.

Conditional Stage B:

- `include/pq_flash_index.h`, `src/pq_flash_index.cpp`: compact mixed store and
  accessor.
- `include/pq_scratch.h`: dual query and ADC scratch.
- `include/pq.h`, `src/pq.cpp`: common compact OPQ table ownership and
  preprocessing accounting.
- `include/percentile_stats.h`, `apps/search_disk_index.cpp`: dual
  preprocessing/accessor and actual-byte reporting.
- Work-local OPQ45/53/61 and two-repeat system scripts.

No VectorDB service, graph redesign, SSD layout project, deployable selector,
RPQ, or structured OPQ is in scope.

## Run Order, Budget and Hard Walls

### Stage A

| Milestone | Work | Expected Wall |
|---|---|---:|
| A0 | trace/score/dispatch implementation and canary | 2–4 h |
| A1 | concurrent OPQ40/48/56 training and encoding | 2–3 h |
| A2 | per-L trace, four selectors, algorithmic matrix | 1–2 h |
| A3 | audit and Stage-A verdict | 0.5 h |

```text
GPU: 0
CPU: at most 3 concurrent builds × 24 threads; search 1 thread
RAM cap: 48 GiB
incremental NVMe reserve: 2 GiB on /dev/nvme8n1
expected Stage-A wall: 5–9 h
Stage-A hard wall: 10 h
```

At the hard wall, stop and report the current stage. Do not train OPQ45/53/61,
add L points, or enter Stage B.

### Stage B, Conditional

| Milestone | Work | Expected Wall |
|---|---|---:|
| B0 | concurrent OPQ45/53/61 training and encoding | 2–3 h |
| B1 | compact layout implementation and parity audit | 2–4 h |
| B2 | actual-memory algorithmic and two-repeat system matrix | 1.5–2.5 h |
| B3 | final audit and verdict | 0.5 h |

```text
GPU: 0
CPU: at most 3 concurrent builds × 24 threads; search 1 thread
RAM cap: 48 GiB
additional NVMe reserve: 2 GiB on /dev/nvme8n1
expected Stage-B wall: 6–10 h
Stage-B hard wall: 11 h
combined maximum after both approvals: 21 h
```

Stage B requires a separate approval after a positive Stage-A report. It does
not start automatically.

## Paper Storyline Boundary

- Main evidence: static precision selectivity first, system realization second.
- Supporting evidence: two independent routing-relevant selectors beat
  hotness/random controls.
- Appendix-only: explicit-workload aggregate-L selector.
- Intentionally cut: deployable/learned selector, held-out generalization, new
  dataset, graph changes, RPQ, structured OPQ, caching, and system services.

## Final Checklist

- [x] Per-L selectors replace implicit cross-L averaging
- [x] Distance-regret KILL is selector-specific
- [x] Independent routing-aware surrogate added
- [x] Scale-normalized and 1M actual-memory views separated
- [x] Algorithmic and system gates separated
- [x] Stage A and conditional Stage B budgets frozen
- [ ] GPT approval for Stage A received
- [ ] Any coding or experiment authorized
