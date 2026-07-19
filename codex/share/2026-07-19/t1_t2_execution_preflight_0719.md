# T1/T2 execution preflight

**Date**: 2026-07-19 (UTC+8)  
**Inputs**: `claude/share/2026-07-19/t1_t2_experiment_plan_0719.md`, `claude/share/2026-07-19/IDEA_REPORT_agent_infra_0719.md`  
**Scope**: read-only plan and local-readiness audit; no implementation, API generation, dependency install, or experiment

## 0. Outcome

```text
T1 = HOLD-METRIC-AND-ATTRIBUTION-CLOSURE
T2 = HOLD-INVALID-CLOSED-LOOP/HYSTERESIS-PROTOCOL
overall = DO-NOT-START-WEEK-1/2-CAMPAIGN
```

T1 can proceed only through a small metric/semantic-contract A0. T2 requires a new state-transition and counterfactual protocol before even a pilot. The current “T1 primary + T2 parallel pilot” schedule, 3–5 week estimate, and “negative result is publishable” fallback are hypotheses, not execution authorization.

## 1. Claim map and minimum evidence

| Candidate | Remaining defensible claim | Anti-claim that must be ruled out | Minimum evidence before scaling |
|---|---|---|---|
| T1 | agent-memory mutation has a reproducible, operation-dependent host write cost not captured by ordinary logical payload accounting | apparent amplification is created by a tiny denominator, unequal system semantics, deferred work, or mislabeling syscall/block bytes as physical NAND writes | canonical operation/post-state contract; multi-layer byte ledger with unattributed bucket; durability/quiescence closure; metric stability on 100-op/1K-object A0 |
| T2 | an endogenous memory/action/write loop creates a nonlinear capacity effect beyond transparent-cache I/O and task hard thresholds | miss is only a transparent disk read; order/learning creates fake hysteresis; coarse grid and binary success create a fake knee | explicit miss intervention; deterministic finite state machine; paired path-dependent protocol; bistability/critical-point evidence with uncertainty; valid fixed-trace counterfactual |

## 2. T1 blockers

### 2.1 SWA denominator is not defined across operations

`physical bytes / logical operation payload bytes` is not comparable across the proposed operations. An insert/update carries text, while forget/merge may carry only IDs and model-upgrade may carry one model identifier while invalidating the whole corpus. This mechanically makes forget/upgrade look enormous regardless of storage behavior. It also makes the proposed ordering `INSERT << UPDATE < MERGE < FORGET < MODEL_UPGRADE` partly an API-encoding artifact.

The plan simultaneously asks for “10K each of MODEL_UPGRADE” in E1 and one upgrade over 10K memories in E6. The former can imply roughly 100 million object reprocessings and is not a bounded run.

Required metrics must be reported separately:

* absolute attributed bytes per operation/event;
* request-envelope bytes (`B_req`), for interface cost only;
* authoritative logical-state delta or deleted/source-object bytes (`B_auth`);
* affected-object count (`N_aff`), especially for global upgrade;
* per-layer ratios only where the denominator is nonzero and semantically comparable.

Global upgrade must be one corpus event and be normalized per affected object and per authoritative corpus byte. A near-zero command envelope must not be used as its main denominator.

### 2.2 “Physical writes” conflates layers

The plan mixes:

```text
W_syscall: application requested write/pwrite/writev bytes
W_page/fs: dirty/writeback and filesystem effects
W_block: host block requests submitted to the device
W_NAND: controller-internal flash programming/relocation
```

These quantities are not interchangeable. Extent mapping does not measure write traffic, and host block I/O is not NAND physical write amplification. T1 may report `W_syscall`, a rigorously defined page/filesystem quantity if implemented, and `W_block`; it must not claim `W_NAND` without device telemetry that actually exposes it.

Journal, compaction, checkpoint, GC, and asynchronous writeback can cross operation boundaries. Every measured operation needs an operation ID, process/cgroup/inode mapping, explicit commit/durability boundary, bounded quiescence rule, idle/background subtraction, randomized run order, and an `unattributed` byte bucket. Bytes that cannot be mechanically mapped must not be assigned to text/embedding/provenance/etc. by assumption.

### 2.3 Cross-system semantics are not comparable yet

Mem0, Zep, Letta, and a slim GEM-like layer do not necessarily implement the same merge, forget, provenance, summary, conflict, or model-upgrade postcondition. A system that performs fewer derived updates will appear to have lower SWA. Before cross-system measurement, define a canonical operation contract and a post-state oracle; compare only shared postconditions, and report extra semantics separately.

Evidence/interpretation separation and epoch consolidation are prior-work baselines/engineering variants, not the remaining novelty. Epoch batching must be evaluated at fixed correctness and freshness, preferably as an I/O–staleness Pareto curve; otherwise an apparent improvement may simply defer or omit required work.

### 2.4 Negative results are not automatically publishable

The novelty review rates T1 incremental. “SWA is low” or “API embedding dominates” does not alone guarantee a FAST paper. Scaling beyond A0 requires at least one of:

1. a stable metric with non-trivial cross-operation/system dynamic range and an explanatory mechanism;
2. a surprising, reproducible boundary showing when storage design does and does not matter;
3. an optimization benefit at fixed postcondition, durability, and freshness.

If none appears, T1 is killed rather than expanded on the premise that any negative result is publishable.

## 3. The claimed M0–M3 reuse does not exist as a general stack

The local artifacts are valuable but application-specific:

* `codex/share/2026-07-17/dynamic_vamana_atlas/m0_write_profiler_v4.cpp` recognizes DGAI/OdinANN filenames and phases. Its partly portable component is an LD_PRELOAD ledger for several write/fsync-family calls and `(device,inode,4KiB offset)` requested-byte/page touches. It does not currently cover all mmap/msync, truncate/allocation, rename/unlink, direct-syscall, child/container, or external DB-daemon paths.
* M1 is the DGAI/OdinANN 50K–400K scale gate, not a generic per-file XFS attribution module.
* M2 is a source-integrated Vamana neighbor-repair fanout/page-mapping/temporal-rewrite collector.
* M3 is a source-integrated DGAI/OdinANN background page-version lifecycle collector.

Thus only part of M0 can be adapted. M1–M3 must be redesigned for the new workload; “directly reuse M0–M3” must not support the low-risk or 3–5 week estimate. The genuinely reusable engineering pieces are `codex/share/2026-07-15/dynamic_vamana_atlas/resource_probe.py` (process-tree RSS, `/proc` and cgroup I/O, directory apparent/allocated bytes), the systemd resource-limit pattern, and the prior self-test/manifest discipline.

Local readiness is currently zero for the application layer: no Mem0/Zep/Letta repository, real trajectory dataset, slim GEM implementation, A/B/C schema, operation adapter, embedding stack, or LLM-context cache was found. Python has stdlib SQLite, but the audited environment lacks the proposed Mem0/Zep/Letta/FAISS/Chroma/Qdrant/SQLAlchemy packages.

Python's local SQLite 3.45.1 does include `DBSTAT`, so a SQLite-only A0 is feasible. It still needs new semantic attribution: multiple logical tables share the same database and WAL files, so filename/offset hooks cannot identify `text/embed/provenance/conflict` writes. A0 needs an application change ledger plus SQLite VFS/WAL-frame or `DBSTAT` evidence, or an explicitly separated-file diagnostic layout. A client-side preload cannot observe a black-box backend running in another daemon/container/remote service.

The currently prepared data roots `/home/ubuntu/pz/VectorDB/data` (`/dev/nvme8n1`) and `/mnt/agentstorage_nvme` (`/dev/nvme6n1`) are ext4, not XFS. Unmounted XFS devices exist, but no T1 mount/ownership/isolation plan has been prepared. Therefore the current “XFS extent mapping” setup is not merely missing instrumentation; it also does not describe the proposed execution root.

## 4. T2 blockers

### 4.1 A transparent cache miss does not close the claimed loop

If a miss reads the same memory from SQLite/FAISS backing storage and returns it, capacity changes latency and I/O but not recalled content. The claimed path

```text
cache state -> recalled content -> action -> memory write -> future requests
```

does not follow. T2 must specify the semantic intervention: for example, a deadline that skips a slow miss, a degraded retrieval result, or a capacity-limited active memory set. That intervention is then part of the treatment and must be compared with a transparent-cache null control. Otherwise the experiment measures ordinary cache I/O.

### 4.2 The down/up sweep does not measure hysteresis

If each capacity point starts from a fresh reset, downward and upward sweeps differ only in execution order; their expected curves are identical. If state is carried across runs, repeated task learning and accumulated writes can create an order effect that looks like hysteresis.

A valid protocol needs:

* a fully specified state `(external task, durable memory, cache, capacity, policy, time)`;
* common exogenous inputs and deterministic transition rules;
* a capacity ramp with defined dwell/equilibration and carried state;
* paired observations at the same capacity reached from high and low sides;
* a checkpoint/fork construction or another control that separates path dependence from irreversible learning;
* evidence of bistability or stable loop area, not only two independently averaged curves.

### 4.3 “Every possible memory context” is combinatorial

The set and order of recalled memories plus dynamic writes create a branching context space. The proposed 500K count multiplies memories by configurations; it is not the number of reachable contexts. It cannot be used as an API/time/space estimate.

T2-A0 must use a finite deterministic agent/policy with no LLM call. A later LLM variant may use on-demand memoization with hard call/token/storage caps, but only after the reachable-context budget is measured.

### 4.4 Decision criteria permit false positives

“30% drop within a 2x capacity window” can arise from one task's hard minimum-information threshold, a coarse capacity grid, or averaging ten binary outcomes. Fixed thresholds of 10% hysteresis and 15% feedback have no confidence intervals or paired test. Five tie-breaking seeds are not five independent tasks and task×seed observations must not be treated as independent.

At minimum, report per-task paired curves, refine the grid around any knee, use task-level paired bootstrap or a hierarchical model, and pre-register a minimum effect with uncertainty. The term “phase transition” requires stronger evidence such as critical-point stability under pool/horizon scaling, bistability, or finite-size scaling; before that, call the observation a nonlinear knee.

The full-cache Jaccard metric is mechanically capacity-dependent, and KL is undefined without a common support/smoothing rule. Compare requested-ID/write sets and semantic state using a predeclared event vocabulary and a stable distance such as smoothed JS/OT when justified.

### 4.5 Fixed-trace control is incomplete

Replaying an access sequence has no agent action or task-success output by itself, so its success cannot be subtracted from closed-loop success. The control must state exactly which causal edge is frozen while retaining the same exogenous events, miss/deadline policy, and outcome function. It should distinguish:

1. transparent-cache null control;
2. exogenous fixed request/write trace;
3. endogenous agent policy with the capacity treatment.

## 5. Only safe next step

### T1-A0: metric and semantic closure

No third-party system and no real/API workload yet. Use a 1K-object deterministic local prototype and at most 100 mutations to verify:

1. canonical INSERT/UPDATE/MERGE/FORGET and one corpus-level UPGRADE postconditions;
2. all denominator definitions and absolute counters;
3. `W_syscall` ledger closure and clearly separated `W_block` observation;
4. commit/quiescence and unattributed-byte accounting;
5. identical post-state hashes across layout variants.

Proposed hard bounds: zero LLM/embedding API calls; root, DB, WAL, traces, venv/cache all under `/mnt/agentstorage_nvme`; <= 2 h wall time; <= 5 GiB NVMe; <= 1 GiB system-disk delta; <= 8 GiB RSS. Stop on any bound violation. The server currently has about 2.8 TiB free on `/mnt/agentstorage_nvme`; the system disk has about 148 GiB free but is explicitly excluded for experiment data and dependency/container caches.

T1-A0 passes only if the logical post-state oracle, operation ledger, layer naming, and byte attribution close mechanically. It does not establish a paper claim.

### T2-A0: deterministic state-machine closure

Write the formal state and transition rules first, then run only a tiny deterministic toy with:

* transparent miss as the required null;
* one explicit semantic miss/deadline intervention;
* common external event streams;
* checkpointed high-side/low-side initial states at the same capacity;
* exact replay showing whether any path dependence remains after controlling learning.

No LLM, no 500K response generation, and no “phase transition” claim. T2-A0 passes only if the experiment can distinguish true state-dependent feedback from reset/order/learning artifacts.

## 6. Execution decision

Do not begin T1 Week 1–2 implementation, cross-system deployment, 10K runs, LLM trajectory generation, or T2 capacity sweep under the current plan. Ask Gpt to review this preflight and choose exactly one first action:

```text
T1-A0-METRIC-CLOSURE
T2-A0-STATE-MACHINE-CLOSURE
REVISE/STOP
```

No campaign should run until that choice and its hard resource limits are accepted.

## 7. Independent checks

Two independent read-only audits were used:

1. an experiment-design adversary checked false-signal, falsifiability, denominator, counterfactual, and resource gates;
2. a local-feasibility auditor checked the actual M0–M3 artifacts, installed dependencies/data, and storage placement.

Both returned HOLD. The experiment-design audit found T2's current closed-loop/hysteresis definitions fatal and T1 salvageable only through A0. The local audit found the general M0–M3 reuse claim false: only part of M0 is portable, while M1–M3 require new instrumentation.
