# Agent Infrastructure 0720 Decision and T2-A0-R2 Gate

**Date:** 2026-07-20
**Repository:** `Metafora072/VectorDBChat`

## 1. Decision

```text
T1 Semantic Write Amplification = STOP-T1-MEASUREMENT-NOVELTY
T2 Closed-Loop Working Set = APPROVE-T2-A0-R2
ZNS = STOP-ENVIRONMENT-MISMATCH
Ambiguity-Monotone = KILL
PageTxn-ANN = KILL
```

Do not run T1 and T2 as parallel primary directions.

## 2. Why T1 stops

The current T1 A0 fails metric closure:

- the reported `64–324×` compares one corpus-wide operation affecting 1,013 objects with one point mutation;
- after per-object normalization, upgrade cost is only `0.0815–0.412×` of mean non-upgrade cost;
- `B_abs` is positive SQLite file-size growth after forced checkpoint/truncate, not application/filesystem/block writes;
- main-file overwrites, writeback, and block submissions are missing;
- raw results are not bound to the executed source hash.

These are repairable implementation defects. The stop reason is deeper:

1. the surviving observation is generic row-versus-field vertical partitioning;
2. evidence/interpretation separation and dependency propagation are already covered by nearby agent-memory work;
3. a repaired study would still be characterization without a new invariant;
4. “a negative result may be publishable” is not a sufficient thesis premise.

Preserve T1 only as an invalid metric attempt / SQLite extent-proxy smoke. Do not run T1-A0-R2, blktrace, Mem0, Zep, Letta, or cross-system measurement.

## 3. T2 A0-R2 question

Do not test “phase transition” or “hysteresis” yet.

Answer only:

> Can a temporary capacity reduction change actions and memory writes, thereby changing future requests and causing persistent divergence after capacity is restored, beyond direct retrieval truncation and irreversible deletion?

The executable chain must be:

```text
capacity
→ retrieved content
→ action
→ memory write/update
→ next query/request
→ later retrieval
```

A missing edge is protocol failure.

## 4. Deterministic model

At step `t`:

```text
S_t = (
  exogenous_position,
  durable_memory,
  query_state,
  action_state,
  capacity,
  policy_state
)
```

Create one frozen exogenous sequence `E=(e_1,...,e_T)`. Every branch receives exactly the same events in the same order. Task/request IDs and random values are precomputed independently of branch execution.

The next query must depend on prior action state:

```text
q_t = Q(e_t, a_{t-1}, h_{t-1})
R_t = Retrieve(q_t, durable_memory, capacity, policy_state)
a_t = Act(e_t, q_t, R_t, h_{t-1})
(delta_memory_t, h_t) = Write(a_t, durable_memory, h_{t-1})
```

It is forbidden to pre-generate all future query targets using only `(task_id, seed)`.

Capacity limits which durable memories are considered/returned. Lowering capacity must not permanently delete backing-store memories. When capacity is restored, old durable memories become eligible again. At least one future query must depend on an action-created or action-modified memory, with a transition-level witness.

## 5. Paired fork

Run a common high-capacity prefix to state `S_f`, then create byte-identical forks:

```text
hash(S_f^A) == hash(S_f^B)
```

Treatment A:

```text
C_mid → C_low for L steps → C_mid evaluation
```

Control B:

```text
C_mid → C_mid for L steps → C_mid evaluation
```

Both branches receive the same exogenous events. Compare only after both are restored to `C_mid`.

## 6. Required controls

Run four models:

1. **Closed-loop treatment**
   Retrieval changes action; action changes memory; action/memory changes later queries.

2. **Open-loop query control**
   Replay the same frozen query stream in both branches. Capacity may change immediate retrieval but cannot alter future queries.

3. **Write-disabled control**
   Retrieval may alter immediate action, but action-dependent memory writes are disabled.

4. **Transparent-retrieval control**
   A miss returns the same durable content with a cost marker, so latency/accounting alone cannot create semantic divergence.

## 7. Admission policy

The old “admit only when a free slot exists” behavior is forbidden.

Use two standard deterministic policies with explicit tie-breaking:

```text
LRU
LFU with recency tie-break
```

Capacity changes must use the same policy transition as normal execution. Do not introduce a tuned semantic-importance threshold.

## 8. Logging

For every step and branch, log:

```text
exogenous_event_id
query_id and query hash
retrieved memory IDs
miss classification
action ID
memory reads/writes/deletes
durable-memory hash
query-state hash
policy-state hash
capacity
outcome contribution
```

Primary measurements:

1. post-restoration action-trace divergence;
2. post-restoration query-stream divergence;
3. durable-memory state divergence;
4. task outcome difference;
5. steps to reconvergence.

Report paired per-instance results, not averages alone.

## 9. Mechanical failure conditions

Return protocol failure if:

- fork states are not identical;
- branches receive different exogenous events;
- IDs depend on mutable shared counters;
- queries do not depend on prior actions;
- action-created memories are never referenced;
- capacity reduction permanently deletes durable memories;
- only one branch gains empty-slot admission advantage;
- replacement differs between normal admission and capacity change;
- seeds alter task semantics;
- source/config/raw hashes are not bound.

## 10. Resource bound

```text
LLM/API calls = 0
GPU = 0
external agent frameworks = 0
wall-clock target <= 2 hours
NVMe allocation <= 5 GiB
RSS <= 8 GiB
```

Pre-register before inspection:

```text
2 replacement policies
5 capacity triplets
20 deterministic workload instances
4 causal/control models
```

## 11. Allowed outcomes

### `PASS-ENDOGENOUS-PATH-DEPENDENCE`

Requires:

1. persistent paired divergence after capacity restoration;
2. later query IDs/targets diverge, not only immediate actions;
3. logged action→write→future-query witnesses;
4. open-loop, write-disabled, and transparent controls do not reproduce comparable divergence;
5. result is not limited to one task, capacity triplet, or policy;
6. all closures pass.

This does not prove phase transition or hysteresis. It only permits an A1 on nonlinear scaling and analytical modeling.

### `KILL-NO-CLOSED-LOOP-SEPARATION`

Use when divergence vanishes after restoration, controls reproduce it, or it is explained by direct truncation, permanent deletion, hard task thresholds, or policy-specific admission.

### `FAIL-PROTOCOL-CLOSURE`

Use for implementation, provenance, fork, workload, or logging violations. No automatic retry.

## 12. Output and stop

Produce:

```text
codex/share/2026-07-20/
t2_a0_r2_closed_loop_path_dependence_gate_0720.md

codex/share/2026-07-20/
t2_a0_r2_closed_loop_path_dependence_result_0720.md
```

After A0-R2, stop. Do not start LLM A1, install agent frameworks, revive T1, or run another idea-discovery round without review.
