# Permission-Aware SSD ANN P0：M3 Manifest Amendment

**Date:** 2026-07-21  
**Repository:** `Metafora072/VectorDBChat`

## 1. Ruling

```text
M0 clean identity/build         = ACCEPT
M1 G0 correctness witness       = ACCEPT-AS-WITNESS
M2 SIFT1M path/direct-I/O smoke = ACCEPT-AS-PREFLIGHT
M3 current workload manifest    = RETURN-FOR-REVISION
M3 execution                    = NOT AUTHORIZED
```

M0–M2 establish artifact identity, filtered search-path viability, the stale-grant correctness premise, and an `O_DIRECT + io_uring` graph path. They do not establish an ACL performance bottleneck or a paper contribution.

The permission-aware SSD problem domain remains open for characterization.

## 2. Why the current M3 manifest cannot run

### 2.1 A1 does not preserve low selectivity

The Bernoulli role assignment forcibly gives every object at least one role. With three random roles per user and 100 roles, this creates an authorization floor around 3%, so `s=0.01` is not realizable.

### 2.2 A2 is not vector- or graph-clustered

```python
obj_cluster = np.arange(n_objects) % n_clusters
```

only clusters by object ID modulo. It does not establish semantic, vector-space, graph-topological, or physical-page correlation. Calling this distribution “same-department documents” or using it to infer lower graph fragmentation is invalid.

### 2.3 A3 cannot realize most declared selectivities

With:

```text
core_fraction = 0.3
core_openness = 0.8
roles_per_user = 3
```

the core alone gives approximately:

```text
0.3 × [1 - (1 - 0.8)^3] ≈ 0.2976
```

global selectivity. Targets `0.01`, `0.05`, `0.10`, and `0.20` are therefore impossible. Clamping the tail does not solve the mismatch.

### 2.4 A5 does not use the real page map

The manifest assumes:

```python
page_id = obj // 64
```

while the M2 artifact does not use 64 nodes per graph page. A5 must consume the actual frozen node→page mapping.

### 2.5 The manifest is not executable or identity-closed

The dataset path differs from the M0 canonical path, the graph hash is `TBD`, no standalone machine-readable manifest is frozen, forced strategies have no frozen CLI, and `beam_width=4` conflicts with the executed M2 configuration.

### 2.6 Exact authorized GT has no canary or resource closure

`1000 × 1M × 128` exact scoring is plausible but cannot be assumed to fit the shared four-hour gate. A blockwise implementation, correctness fixture, measured projection, and artifact-size accounting are required before admission.

## 3. Scope correction: M3 measures resolved authorization masks

Axis A asks:

> At the same exact selectivity and on the same graph/page map, does the spatial structure of a resolved authorization predicate change graph traversal, physical page reads, recall, and the best filter execution strategy?

The search path observes a resolved Boolean predicate over objects. Therefore M3 shall directly materialize frozen per-user authorization masks.

Role hierarchy, user-role closure, and object-role factorization are workload provenance concerns, not necessary variables in the first graph-fragmentation experiment.

Each user mask must contain exactly:

```text
floor(s × N)
```

authorized objects for every declared selectivity `s`, using the same deterministic rounding rule.

## 4. Revised structural workload families

All families share the same users, query-user binding, exact per-user authorized count, graph, node→page map, query vectors, GT procedure, and policy seeds.

### F0: Exact Random Mask

For each user and selectivity, choose exactly `floor(sN)` objects by a frozen hash permutation.

### F1: Graph-Localized Mask

Construct deterministic graph regions from the frozen Vamana adjacency using a preregistered partition procedure. A user receives whole or partial regions until exact cardinality is reached.

This is a synthetic graph-locality control, not a direct enterprise workload.

### F2: Shared-Core + Private-Tail Mask

For every user:

```text
authorized set
= shared core of c × floor(sN)
+ private tail of (1-c) × floor(sN)
```

Both components have exact disjoint cardinalities. Freeze whether the core is graph-localized or hash-random before outcomes.

### F3: Page-Anti-Correlated Mask

Use the actual node→page map. Select exactly `floor(sN)` nodes while maximizing within-page authorization alternation under a deterministic construction.

F3 is a stress test only. A result appearing only in F3 cannot establish the Q route.

## 5. Required structural descriptors

For every user mask, report before search:

- authorized-authorized edge fraction;
- authorized/unauthorized edge-cut fraction;
- local authorization homophily;
- largest authorized connected-component fraction;
- authorized component count/size distribution;
- per-page authorized count/fraction;
- per-page binary entropy;
- empty/full/mixed-page fractions.

These descriptors must prove that F0/F1/F2/F3 are actually distinct.

## 6. Query binding and replication

Freeze a balanced mapping in which every selected user receives multiple queries.

Requirements:

- total queries remain at most 1000;
- every user has the same number of queries;
- the same binding is used across all families;
- two independent policy seeds are required;
- queries are divided into at least two frozen groups;
- a claimed trend must reproduce across both seeds and both query groups.

No pooled result may rescue a failed seed or group.

## 7. Graph and policy isolation decisions

### 7.1 `R_dense=128`

Conditionally approved for one M3 graph only.

Before full M3:

1. build one graph with `R=64`, `R_dense=128`, `L_build=96`, `PQ=32`;
2. verify resource guards;
3. freeze graph, adjacency, node order, node→page map, and file hashes;
4. run a canary proving `IN_FILTER` executes;
5. never rebuild per policy family/selectivity.

If the canary fails, remove `IN_FILTER`; do not increase to 512/1500.

### 7.2 Policy representation

Do not replace variable policy payloads inside graph records.

For Axis A, use an external fixed-width resolved-mask predicate view in DRAM, or an equivalent immutable side structure whose lookup does not alter graph record length, node offsets, page boundaries, adjacency, or graph-file hash.

This intentionally excludes policy-metadata I/O from M3. Axis B remains unmeasured.

## 8. Search execution

Approve a minimal adapter adding a forced-strategy enum:

```text
PRE_FILTER
IN_FILTER
POST_FILTER
AUTO
```

The adapter must not modify each strategy's algorithm.

Freeze binary/source diff hashes, beam width, `L`, threads, I/O width, cache state, continuation/refill, and exact verifier behavior. `AUTO` is supplementary.

## 9. Exact authorized ground truth

Implement blockwise exact L2 scoring that computes distances once per query block and updates top-k for every frozen mask cell.

Requirements:

- exact scalar-fixture equality;
- deterministic ties;
- GT hash per cell;
- measured wall/RSS/storage projection;
- no silent reduction of queries, dataset, families, or seeds.

If projection exceeds the shared guard, return `HOLD-GT-COST`.

## 10. I/O accounting

M3 must separate:

```text
application logical graph-page requests
application graph device submissions
cgroup block read I/O count/bytes
whole-device counters (diagnostic only)
```

Run search in an isolated cgroup, snapshot `io.stat` immediately before/after search, exclude build/load/GT, record device major/minor, reconcile graph submits × 4096 with cgroup bytes, and explain residuals.

Policy reads are DRAM-side and must not be reported as SSD policy I/O.

## 11. Primary metrics

Per query:

- authorized Recall@10;
- latency;
- logical graph pages;
- graph device submissions;
- cgroup read bytes/I/O;
- visited/expanded nodes;
- unauthorized neighbor rejects;
- bridge promotions;
- continuation/refill rounds;
- candidate exhaustion;
- exact-verifier rejects.

Report p50/p95/p99 and paired query-level differences.

## 12. M3 decision logic

No fixed 10% or 15% threshold.

### `PASS-Q-PHENOMENON`

Requires:

1. exact selectivity matching;
2. F1 or F2, not only F3, differs structurally from F0;
3. at matched selectivity and target recall, a non-adversarial family changes graph I/O, recall cost, or optimal strategy;
4. effect reproduces across both seeds and query groups;
5. physical I/O closes;
6. no single existing forced strategy dominates all non-adversarial families.

PASS confirms a workload phenomenon only.

### `HOLD-GENERIC-FILTER-CORRELATION`

Policy structure affects execution, but the effect is fully explained by ordinary graph/page predicate correlation and no ACL-specific property is identified.

### `KILL-Q-NO-STRUCTURE-EFFECT`

F0/F1/F2 show no stable difference.

### `KILL-Q-ADVERSARIAL-ONLY`

Only F3 differs.

### `KILL-Q-ONE-STRATEGY-DOMINATES`

One existing strategy gives the best recall/I/O envelope across all non-adversarial families.

### `FAIL-M3-CLOSURE`

Manifest, graph identity, GT, strategy, resource, or I/O-accounting failure.

## 13. Required return before execution

Claude and Codex jointly return:

1. standalone manifest + SHA-256;
2. exact mask generators and fixtures;
3. graph partition/page-map hashes;
4. realized cardinality/structure summaries;
5. balanced query binding and two policy seeds;
6. `R_dense=128` canary and graph hashes;
7. forced-strategy adapter diff/binary hashes;
8. exact-GT canary and projection;
9. corrected `io.stat` canary;
10. final cell count and projected wall time.

Only after explicit `PASS-M3-PRELAUNCH` may M3 execute.
