# T2-A0-R2 closed-loop path-dependence prelaunch gate

**Attempt:** `t2_a0_r2_20260720_001`
**Frozen configuration:** `codex/share/2026-07-20/t2_a0_r2/config.json`
**Authorizing gate:** `gpt/share/2026-07-20/agent_infra_0720_t2_a0_r2_gate.md`
**Authorizing gate SHA-256:** `acb2ce14da3629cb09e24cb5c31a6d365d57bab89716bb6b0a1bf2a859a6c3c7`

## 1. Scope and stop conditions

This single attempt tests only whether temporary retrieval-capacity loss can alter actions and writes, then alter later queries and preserve paired divergence after capacity restoration. It does not test or claim phase transition or hysteresis. T1 remains stopped. LLM/API calls, GPUs, and external agent frameworks are all zero.

The only outcomes are:

```text
PASS-ENDOGENOUS-PATH-DEPENDENCE
KILL-NO-CLOSED-LOOP-SEPARATION
FAIL-PROTOCOL-CLOSURE
```

`FAIL-PROTOCOL-CLOSURE` takes precedence. There is no automatic retry. After the result is sealed, execution stops before A1.

## 2. Frozen matrix and horizons

The formal matrix contains exactly `2 policies × 5 capacity triplets × 20 immutable workload instances × 4 models = 800` paired fork cells and 1,600 branch trajectories. Steps and branches are not independent samples.

Policies:

```text
LRU
LFU with recency then memory-ID tie-break
```

Capacity triplets `(C_mid, C_low, C_restore)`:

```text
(12,10,12), (12,8,12), (12,6,12), (12,4,12), (12,2,12)
```

Every formal trajectory has a 48-step common high-capacity prefix, a 36-step fork interval, and a fixed 96-step post-restoration evaluation. The 20 workloads are four locality families (`cyclic`, `bursty`, `interleaved`, `reversal`) with five immutable instances each. Instance derivation changes only event ordering and numeric payloads, not state-machine semantics, memory count, or outcome definition. All events, IDs, numeric fields, and open-loop tokens are materialized and hashed before sanity inspection.

Sanity uses two disjoint IDs, one capacity triplet, and `12/12/24` prefix/low/evaluation steps. It cannot select or modify the formal matrix. A sanity failure ends this attempt; any code or configuration repair requires a new attempt ID.

## 3. Deterministic state machine

There are exactly 12 logical durable memories. State serialization covers:

```text
event cursor
append-only version log and latest version per logical memory
query head/token per logical memory
active set
LRU/LFU request metadata
capacity
previous action and action history
cumulative continuous outcome
logical clock
```

Each frozen event contains an event ID, logical memory ID, signal, delta, target, and an independently generated open-loop token. At step `t`:

```text
q_t = Q(e_t, a_(t-1), head_(t-1))
r_t = Retrieve(q_t, durable_memory, active_set)
a_t = (event.signal + semantic_query_token + visible_payload) mod 257
v_t = Write(a_t, parent_version, event.delta, semantic_query_token)
head_t = (v_t, next_token derived from a_t)
```

The continuous outcome contribution is:

```text
1 - circular_distance(action, event.target, 257) / 128
```

No binary success or critical-item threshold is used. Query semantic hashes cover only fields consumed by `Retrieve`/`Act`; branch labels, object addresses, lineage-only source IDs, mutable counters, wall time, and file paths are excluded.

Every durable update is an append-only version with a content-addressed ID derived from immutable instance/event data, parent version, action, and payload. Capacity transitions never delete durable versions. `durable_live_hash` covers current semantic versions; the append-only audit hash is reported separately and cannot by itself establish persistence.

## 4. Retrieval and replacement semantics

For a resident logical memory, retrieval returns the latest durable payload. For a nonresident durable memory in the three semantic models, the current step returns no payload, records a capacity miss, updates request metadata, and applies the same deterministic Top-C selector used by hits and resize. Thus a miss affects the current action but makes the requested item eligible for later steps. Transparent retrieval performs the identical policy transition while returning byte-identical durable content; its cost marker is log-only.

LRU ranks by `(last_request, memory_id)`. LFU ranks by `(frequency, last_request, memory_id)`. Hits, misses, ordinary admission, shrink, and restore call one selector; no free-slot-only path exists. Policy metadata persists for every durable logical ID. Because `C_restore=12` equals the logical-memory count, both branches are fully occupied before the first evaluation event, eliminating a treatment-only empty-slot advantage.

## 5. Four causal models

All models start from the same serialized high-capacity prefix state within each policy/instance cell; interventions begin only after fork.

1. `closed_loop`: query consumes the token written by the prior action; retrieval changes action; action appends a durable version and updates the future query head.
2. `open_loop_query`: both branches replay the same pre-materialized semantic query tokens. Retrieval, action, and writes remain enabled, but branch execution cannot alter future query tokens.
3. `write_disabled`: retrieval and immediate actions remain enabled, but durable append, latest-version update, and head update are all disabled.
4. `transparent_retrieval`: identical to closed loop except a capacity miss returns the same durable semantic payload. The marker cannot enter query, action, write, outcome, or semantic hashes.

The validator reconstructs, rather than trusts, at least one complete witness per claimed-positive instance:

```text
low-window retrieval difference
→ action difference
→ branch-differential version created_by that action
→ post-restoration query consumes that version's token
→ retrieval references the exact logical memory/version
→ downstream action/outcome difference
```

## 6. Fork, log, and provenance closure

Both branches are independently deserialized from identical canonical JSON bytes. Before execution, the runner proves byte identity, deep-copy isolation, and branch-order invariance. A/B receive identical frozen exogenous event bytes at every paired step. All IDs use canonical JSON plus SHA-256; Python `hash()`, global RNGs, and mutable global counters are forbidden.

Every step records all GPT-required fields plus pre/post state hashes, fork hash, exogenous payload hash, prior-action dependency, durable versus resident operations, replacement victim/rank, and witness lineage. The validator independently checks transition equations and rejects missing/duplicate cells, unequal fork bytes, unequal exogenous streams, capacity-driven durable deletion, inconsistent replacement, control-edge leakage, source/config/workload/raw hash mismatch, or resource overrun.

Before formal execution, the frozen attempt manifest binds the gate, source bundle, config, formal/sanity workloads, Python executable, serialization schema, mount identity, and every threshold. Formal execution is allowed only if all sanity and negative tamper tests pass and all frozen hashes remain unchanged.

## 7. Mechanical metrics and classifier

For each paired cell over the 96 post-restoration steps:

```text
Q = fraction of semantic query hashes that differ
A = fraction of action hashes that differ
M = fraction of durable_live hashes that differ
Y = fraction of continuous outcome contributions that differ
D = (Q + A + M + Y) / 4
B = (A + Y) / 2
```

`tau_behavior` is the earliest restored step after which query/action/outcome are equal for every remaining suffix step. `tau_state` additionally requires live durable and policy/query/action state equality. A nonreconverged trajectory is right-censored at 97. All 20 paired rows, medians/IQR, witness coverage, and steps to reconvergence are reported; averages alone are forbidden.

An instance qualifies only when all closure checks pass, `Q/A/M/Y > 0`, query/action/live-memory all differ at the final step, `tau_state=97`, a complete witness is reconstructed, open-loop has `Q=0`, write-disabled has `M=0`, transparent semantic `D=0`, and closed-loop behavioral divergence `B` is strictly greater than each control's paired `B`.

A policy/triplet cell is supported only with at least 17/20 qualifying instances and a deterministic paired bootstrap 95% confidence interval whose lower bound for `B_closed - max(B_controls)` is greater than zero. PASS additionally requires at least 3/5 supported triplets under each policy, at least two identical triplets supported by both policies, and at least two qualifying instances from every workload family in every supported cell.

If protocol closure passes but this scientific gate fails, controls reproduce comparable behavior, effects reconverge, witnesses are absent, or the result is limited to a policy/triplet/family, the outcome is `KILL-NO-CLOSED-LOOP-SEPARATION`.

## 8. Resource and storage gate

The writable experiment root is:

```text
/home/ubuntu/pz/VectorDB/data/agent_infra/t2_a0_r2/t2_a0_r2_20260720_001
```

It maps to the dedicated `/dev/nvme8n1` ext4 volume. `/mnt/agentstorage_nvme` is read-only and will not be used. The live runner enforces wall time `≤7200 s`, process-tree RSS `≤1 GiB`, and attempt allocation `≤256 MiB`, which are stricter than GPT's bounds. Temporary files and Python bytecode are redirected inside the attempt. Chat stores only compact source/config/hash/report artifacts.

No parameter, workload, horizon, model rule, or classifier may change after this prelaunch commit based on observed outcomes.
