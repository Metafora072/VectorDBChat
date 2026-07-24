# Experiment Plan

**Problem**: Determine whether OPQ64's routing value is concentrated on a static subset of graph nodes under equal actual resident-representation memory.
**Method Thesis**: A trace-conditioned, per-node allocation of OPQ64 codes may reduce routing-distance error enough to move the Recall–reads–QPS–p99 frontier beyond the strongest equal-memory uniform OPQ baseline.
**Date**: 2026-07-24
**Status**: `PLAN-ONLY / WAITING-FOR-GPT-APPROVAL`

No coding, training, trace generation, or search is authorized by this plan.

## Claim Map

| Claim | Why It Matters | Minimum Convincing Evidence | Linked Blocks |
|---|---|---|---|
| C1: higher OPQ precision has static node-level selectivity | Without concentration, mixed representation has no algorithmic basis | At least one mixed budget strictly and repeat-stably dominates the equal-actual-memory uniform frontier | B1–B4 |
| C2: the gain is precision sensitivity rather than hotness | Visit frequency alone would reduce the idea to cache-like hotspot allocation | Trace-conditioned selection beats random-node and visit-frequency selectors at the same layout and memory | B3–B4 |
| Anti-claim: gains come from free memory or omitted preprocessing | Mixed OPQ carries a second model and two query preprocessing paths | Actual allocated bytes are audited; both rotations and ADC tables are timed inside end-to-end search | B1, B2, B4 |

## Frozen Context

- Dataset: GIST1M-960D only; positive evidence remains a dimension-stress result.
- Queries/GT: the existing official 1K queries and audited ground truth.
- Training rows: the existing deterministic 100K row IDs.
- Graph SHA-256: `52827694a9e8dcf64037639e594ed9855f514aa2ebbcb5a4d25f4c1921fa1c37`.
- Training: seed `20260724`, 20 OPQ iterations, 256 centroids/chunk.
- Search: `W=4`, `K=10`, one search thread, zero node cache, optimized V1 dense rotation.
- Grid: `L={50,100,200,400,800}`.
- No graph rebuild/mutation, new dataset, GPU, reranking change, ADC semantic change, or deployable-selector claim.

## M0 Compatibility Findings

The native path used by `apps/utils/generate_pq.cpp` calls
`generate_opq_pivots()` and `generate_pq_data_from_pivots()`, not the
divisibility-restricted `*_simplified` helpers. It accepts any
`num_pq_chunks <= dim`, stores explicit `chunk_offsets`, and both the encoder
and ADC search loop consume those offsets.

- OPQ40: 40 chunks × 24 dimensions; offsets `0,24,...,960`.
- OPQ48: 48 chunks × 20 dimensions; offsets `0,20,...,960`.
- OPQ56: native uneven partition, 8 chunks × 18 dimensions followed by
  48 chunks × 17 dimensions; offsets end `0,18,...,144,161,...,960`.

Thus OPQ40/48 are directly divisible and OPQ56 is natively supported without
padding or dropped dimensions. Each baseline must train its own rotation and
codebook. The OPQ56 artifact audit must verify exactly 57 offsets, eight
18-dimensional chunks, 48 17-dimensional chunks, and total width 960.

The existing OPQ32 and OPQ64 artifacts have independent 960×960 rotations,
centroids and codebooks. A mixed query therefore requires:

1. centering and V1 rotation under OPQ32;
2. a 256×32 ADC table;
3. centering and V1 rotation under OPQ64;
4. a 256×64 ADC table.

Both rotation and both ADC-table costs must be inside each query's measured
latency. The rotation-only lower estimate from the completed V1 microbenchmark
is approximately `2 × 123.15 us`; it is not an end-to-end prediction. ADC
construction also traverses all 960 dimensions for each model and must be
measured separately. Query scratch requires 98,304 bytes for the two float ADC
tables plus 7,680 bytes for two 960D float query buffers, before existing
distance/coordinate scratch.

## Compact Mixed Layout and Exact Memory Model

Let `N=1,000,000`, `H` be the OPQ64-node count, and `L=N-H`. Use four separate
64-byte-aligned arrays:

```text
low_codes[L][32]       // only low nodes
high_codes[H][64]      // only high nodes
high_tag[ceil(N/64)]   // one bit per original node ID
rank1_prefix[ceil(N/64)+1] // uint32 prefix count per 64-node word
```

For node `i`, with `w=i>>6` and `b=i&63`:

```text
rank1(i) = rank1_prefix[w] +
           popcount(high_tag[w] & ((1ULL << b) - 1))
```

with the `b=0` mask defined as zero. If the tag is one, the code is
`high_codes[rank1(i)]`; otherwise it is `low_codes[i-rank1(i)]`. This gives
constant-time random access with one tag read, one prefix read and one
popcount, and never reserves 64 bytes for an OPQ32 node.

For `N=1,000,000`:

```text
tag words                    = 15,625
tag bytes                    = 125,000; aligned allocation = 125,056
rank entries                 = 15,626
rank bytes                   = 62,504; aligned allocation = 62,528
tag+rank actual allocation   = 187,584 bytes
```

One compact online OPQ model retains one transposed codebook, one centroid,
one rotation, and aligned chunk offsets:

```text
codebook      = 256 × 960 × 4 =   983,040 bytes
centroid      = 960 × 4       =     3,840 bytes
rotation      = 960 × 960 × 4 = 3,686,400 bytes
OPQ32 offsets = 33 × 4, aligned 64 = 192 bytes
OPQ64 offsets = 65 × 4, aligned 64 = 320 bytes
two-model total                         = 9,347,072 bytes
```

The current native loader retains both row-major and transposed codebooks.
Before the full gate, either the unused copy must be released for every
uniform and mixed variant or its allocator capacity must be charged to every
variant. The planned common compact loader counts one physical transposed
codebook per model; parity tests must show this does not alter ADC values.

Exact planned resident-representation allocation, including 64-byte padding:

| Mix | Code payload | Tag+rank | Two models | Total bytes | Bytes/vector |
|---|---:|---:|---:|---:|---:|
| 75% OPQ32 + 25% OPQ64 | 40,000,000 | 187,584 | 9,347,072 | 49,534,656 | 49.534656 |
| 50% OPQ32 + 50% OPQ64 | 48,000,000 | 187,584 | 9,347,072 | 57,534,656 | 57.534656 |
| 25% OPQ32 + 75% OPQ64 | 56,000,000 | 187,584 | 9,347,072 | 65,534,656 | 65.534656 |

Uniform actual resident allocations under the same compact loader are:

| Uniform | Code payload | Model allocation | Total bytes | Bytes/vector |
|---|---:|---:|---:|---:|
| OPQ40 | 40,000,000 | 4,673,472 | 44,673,472 | 44.673472 |
| OPQ48 | 48,000,000 | 4,673,536 | 52,673,536 | 52.673536 |
| OPQ56 | 56,000,000 | 4,673,536 | 60,673,536 | 60.673536 |

Therefore OPQ40/48/56 are same-payload controls, not equal-total-memory
controls. The primary no-free-memory guards are the nearest stronger uniform
models OPQ45/53/61:

| Mixed budget | Mixed total | Nearest stronger uniform | Uniform total |
|---|---:|---|---:|
| 40 payload | 49,534,656 | OPQ45 | 49,673,472 |
| 48 payload | 57,534,656 | OPQ53 | 57,673,536 |
| 56 payload | 65,534,656 | OPQ61 | 65,673,536 |

The full run must report both serialized file bytes and actual allocated
capacity. If measured allocator capacity differs from this model, the measured
larger value controls the comparison.

## Formal Trace-Conditioned Selection Objective

Let `Q` be the official 1K test queries and `Λ={50,100,200,400,800}`. For each
`(q, L)`, record the union of node-distance events from deterministic uniform
OPQ32 and uniform OPQ64 searches under the frozen graph/search policy. Duplicate
visits to the same `(q,L,node)` are counted once. This union avoids conditioning
only on one endpoint while remaining a fixed, reproducible test-trace
feasibility bound.

For event `e=(q,L,v)`, let `d*(q,v)` be exact squared L2 distance and
`d32(q,v)`, `d64(q,v)` be the two ADC estimates. Define:

```text
delta_e = (d32(q,v) - d*(q,v))^2 - (d64(q,v) - d*(q,v))^2
s_v     = sum over trace events e ending at v of delta_e
J(S)    = sum over v in S of s_v, subject to |S|=H
```

There is no threshold, centrality weight, fitted coefficient, or reconstruction
term. The trace is routing-conditioned, while the loss is exact-distance
estimation regret.

Because `J(S)` is modular, an exchange argument proves that choosing the `H`
largest `s_v` is the exact optimum for this stated trace objective: if a chosen
node has smaller score than an unchosen node, swapping them strictly increases
or preserves `J`. Ties are resolved by ascending node ID before any search
result is observed.

This is named `TRACE-CONDITIONED-SELECTOR`, not a global oracle. It does not
optimize the non-additive mixed-search trajectory or its induced future trace,
and it uses test queries and exact distances. A positive result supports only
hindsight selectivity.

Baselines at each `H`:

- `RANDOM-NODE`: one preregistered permutation from seed `20260724`;
- `VISIT-FREQUENCY`: top-H by event count on the same trace, ties by node ID;
- `TRACE-CONDITIONED-SELECTOR`: top-H by `s_v`.

Trace generation time, exact-distance evaluation time, sorting/selection time,
and online search time are reported separately.

## Experiment Blocks

### B1: Compatibility and Artifact Gate

- Claim tested: the uniform and mixed artifacts obey the frozen protocol.
- Systems: existing OPQ32/64; new OPQ40/48/56 and memory guards OPQ45/53/61.
- Success: shapes, offsets, orthogonality, training IDs, graph/query/GT hashes,
  and code counts all pass.
- Failure: any mismatch stops all search.
- Priority: MUST-RUN after approval.

### B2: Uniform Frontier and Memory Guard

- Claim tested: mixed codes face the strongest actual-memory baseline.
- Systems: OPQ32/40/45/48/53/56/61/64.
- Metrics: Recall@10, reads, comparisons, QPS, p50, p99, preprocessing time,
  serialized bytes, allocated bytes/vector.
- Repetitions: exactly two complete, interleaved repeats; report both raw
  repeats; never add a third.
- Priority: MUST-RUN.

### B3: Selector Isolation

- Claim tested: precision sensitivity adds value beyond random placement and
  visit hotness.
- Systems: three budgets × RANDOM-NODE / VISIT-FREQUENCY /
  TRACE-CONDITIONED-SELECTOR.
- Setup: same compact layout and dual-query preprocessing for every selector.
- Failure interpretation: if visit frequency matches the trace-conditioned
  selector, no precision-specific mechanism is established.
- Priority: MUST-RUN.

### B4: Equal-Memory Pareto Gate

- Claim tested: hindsight selectivity moves the actual-memory frontier.
- Primary comparisons: 40/48/56-payload mixes against OPQ45/53/61,
  respectively. OPQ40/48/56 remain same-payload diagnostics.
- PASS requires at least one budget and a pair of points, possibly at different
  L, where in each raw repeat mixed Recall is no lower, reads are strictly
  lower, QPS is strictly higher, and p99 is strictly lower than the uniform
  frontier. Averaging cannot reverse a failed repeat.
- Otherwise: `KILL-SELECTIVE-OPQ`.
- Positive result: `PASS-HINDSIGHT-SELECTIVITY /
  HOLD-DEPLOYABLE-SELECTOR`.
- Priority: MUST-RUN.

## Run Order and Milestones

| Milestone | Goal | Runs | Decision Gate | Estimated Cost | Risk |
|---|---|---|---|---|---|
| M0 | unit/artifact/layout canary | no full search | all parity and byte audits pass | 1–2 h implementation/audit | mixed accessor bug |
| M1 | train/code uniform controls | 40/45/48/53/56/61 | artifact gate passes | 4–7 h wall with 3-way parallel waves | OPQ training contention |
| M2 | generate frozen trace/selectors | OPQ32+64 traces over 5 L | deterministic scores and exact top-H audit | 0.5–1.5 h | trace volume |
| M3 | uniform and mixed search | 8 uniform + 9 mixed variants, 5 L, 2 repeats | strict raw-repeat Pareto gate | 1.5–3 h | host latency noise |
| M4 | audit/report only | no new runs | issue one frozen verdict | 0.5–1 h | metric mistakes |

## Correctness Gates

1. Recompute all frozen SHA-256 values before work and before reporting.
2. Verify OPQ40/48/56/45/53/61 chunk counts, offsets, centroid count and
   rotation orthogonality.
3. Exhaustively verify tag popcount, prefix ranks, unique dense slots and exact
   low/high cardinalities for all one million node IDs.
4. All-low mixed mode must reproduce uniform OPQ32 per-node ADC values and
   search outputs; all-high must reproduce OPQ64.
5. For sampled selected/unselected nodes, mixed distances must equal the
   corresponding standalone OPQ64/32 distances within `1e-5` absolute error.
6. Measure two rotations and two ADC tables inside query latency; no pre-rotated
   query may enter final QPS/p50/p99.
7. Verify optimized V1, one search thread, zero cache, `W=4`, `K=10`, and exact
   L grid from logs.
8. Verify allocated capacity and serialized bytes against the layout model.
9. Recompute selector scores from raw trace and verify top-H exactness and
   deterministic tie-breaking.
10. Exactly two interleaved complete performance repeats; no partial result and
    no third repeat.

Any correctness failure, graph/data mismatch, hidden dense 64-byte allocation,
omitted dual preprocessing, or inability to construct a no-free-memory uniform
guard makes the gate `INVALID`, not PASS.

## Expected Implementation Scope After Approval

- `DiskANN_trace/include/pq_flash_index.h`: second OPQ table, compact code-store
  state and dual scratch ownership.
- `DiskANN_trace/include/pq_scratch.h`: two rotated queries and two ADC tables.
- `DiskANN_trace/include/pq.h` and `src/pq.cpp`: compact online table ownership,
  release of duplicate codebook storage, preprocessing accounting.
- `DiskANN_trace/src/pq_flash_index.cpp`: mixed load/access, dual query
  preprocessing, trace hooks and selector-aware distance dispatch.
- `DiskANN_trace/include/percentile_stats.h` and
  `apps/search_disk_index.cpp`: dual preprocessing and layout-byte reporting.
- New work-local scripts under
  `codex/work/2026-07-24/selective_opq_oracle_a0/` for training, layout packing,
  trace extraction, selector construction, audits, execution and analysis.

No full vector-database, graph mutation, SSD layout redesign, selector model,
or production metadata service is in scope.

## Compute and Data Budget

- GPU: 0.
- CPU: up to three concurrent OPQ builds, 24 OpenMP threads each; search remains
  one thread. Host has 112 logical CPUs.
- RAM: estimated 13 GiB/build; cap concurrent build RSS at 48 GiB; full machine
  availability at planning time is 242 GiB.
- NVMe: reserve 2 GiB incremental on `/dev/nvme8n1` for six uniform artifacts,
  compact mixes, traces, raw repeats and logs. No large artifact may be written
  to the system LV.
- Expected wall time after approval: 7–13 h.
- Hard wall: 16 h for the complete approved pipeline. Stop at the current
  phase on timeout; do not add models, L points or repeats.
- Current NVMe availability: approximately 1.4 TiB.

## Paper Storyline Boundary

- Main evidence if positive: one strict equal-memory hindsight frontier shift.
- Supporting evidence: trace-conditioned allocation beats random and hotness.
- Intentionally cut: deployable selector, held-out generalization, new graph,
  additional datasets, structured OPQ, RPQ, caching and systems machinery.
- A positive A0 authorizes only a later held-out-query selector gate.

## Final Checklist

- [x] Main claim and anti-claim frozen
- [x] Strong actual-memory baselines specified
- [x] Additive objective and exact top-H scope stated
- [x] Random and visit-frequency controls included
- [x] Dual preprocessing charged
- [x] No-GPU and hard-wall budget specified
- [ ] GPT approval received
- [ ] Implementation or experiments authorized
