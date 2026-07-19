# VectorDB Research Direction Gate

**Date:** 2026-07-19
**Purpose:** Freeze the current decision state and define the only allowed next actions for the VectorDB research thread.

## 1. Current decision

Do **not** make any of the following moves yet:

- Do not abandon the ZNS direction before Z0B finishes.
- Do not promote Ambiguity-Monotone Graph into an implementation project.
- Do not start implementing PageTxn-ANN.
- Do not rerun a broad, unconstrained idea-discovery round.

The current strategy is:

1. Let **ZNS Z0B** finish naturally.
2. In parallel, finish the low-cost **Ambiguity A0 paper gate**.
3. Keep **PageTxn-ANN** as the third-priority paper-only fallback.
4. Start a new problem-discovery round only if all three directions fail their gates.

---

## 2. ZNS direction

### Current status

Z0A-R2 established only a sequence-level foundation:

- stable logical-page identity;
- complete application-write sequence;
- page-version lifecycle;
- initial packing;
- event-by-event agreement between the main simulator and an independent reference;
- sequence-based reclaim replay.

It did **not** establish trustworthy timestamps, update rates, bandwidth, endurance, or wall-clock conclusions.

Therefore, the only current interpretation is:

> ZNS has a trustworthy sequence/reclaim simulator, but the existence and stability of a meaningful reclaim signal are still unproven.

### Z0B question

Z0B must answer only:

> Do real long-running dynamic-ANN write sequences generate repeated, stable fill-relocate-reset cycles under non-Oracle placement?

The intended workloads include at least:

- DGAI-50K;
- OdinANN-400K.

OdinANN-400K must produce enough complete reclaim cycles to support a stability judgment. A short trace or a few initial cycles are insufficient.

### Allowed Z0B outcomes

Use exactly one of:

- `PASS-SEQUENCE-RECLAIM-SIGNAL`
- `KILL-NO-RECLAIM-SIGNAL`
- `KILL-PLACEMENT-SEQUENCE-UNSTABLE`
- `INCONCLUSIVE-TRACE-TOO-SHORT`
- `INCONCLUSIVE-IMPLEMENTATION-ERROR`

Do not convert an inconclusive result into a pass.

### What a Z0B pass does not prove

Even if Z0B passes, it does not yet prove:

- ANN-specificity;
- superiority over conventional SSDs;
- a ZNS feasibility boundary;
- a new ZoneEpoch design;
- lower write amplification in a real implementation;
- publishable novelty.

A pass only permits the next gate:

### ZNS ANN-specificity gate

Compare the observed reclaim behavior against matched counterfactual workloads that preserve basic overwrite/lifetime statistics while removing graph-specific structure.

At minimum consider:

1. shuffled write order while preserving per-page update counts;
2. matched hot/cold overwrite distribution;
3. generic KV/B-tree-like update streams;
4. lifetime-aware placement without ANN semantics;
5. an Oracle lower bound, used only as a bound rather than a deployable baseline.

The direction survives only if graph/update semantics explain a material part of the reclaim behavior that generic lifetime or placement policies cannot reproduce.

---

## 3. Ambiguity-Monotone Graph

### Current status

The original formulation is likely invalid because ambiguity is generally query-dependent and search-state-dependent.

Potential ambiguity measures depend on variables such as:

- query \(q\);
- current top-k threshold \(\tau_t\);
- quantization estimate;
- lower and upper distance bounds;
- the set of already verified candidates.

This makes a global, query-independent monotone order on a static graph difficult to define.

### A0 goal

A0 is an impossibility-first, paper-only gate. It must determine whether there exists a nontrivial formal object stronger than existing bound-guided probing.

Allowed outcomes:

- `PASS-ORIGINAL`
- `PASS-SALVAGED-FORMAL-OBJECT`
- `KILL`

### Minimum requirements for `PASS-SALVAGED-FORMAL-OBJECT`

A salvaged formulation must provide all of the following:

1. A precise uncertainty or ambiguity definition.
2. A graph property or search invariant that is not merely a heuristic score.
3. A proof, lower bound, or counterexample-based theorem with meaningful consequences.
4. A clear distinction from:
   - RaBitQ-style error bounds;
   - SymphonyQG-style quantized graph traversal;
   - δ-EMG / δ-EMQG;
   - QuIVer-style quantized topology construction;
   - ordinary branch-and-bound or bound-guided exact probing.
5. A disk-system consequence:
   - fewer full-vector page reads;
   - fewer exact probes;
   - better batching/locality;
   - or a new correctness/recall guarantee tied to I/O.

If it only produces a candidate priority score such as

\[
\widehat d(q,x) + \lambda \epsilon_x,
\]

it must be killed as a heuristic unless \(\lambda\) follows from a proved invariant rather than tuning.

### Coupled versus decoupled storage

The analysis must explicitly separate:

- **coupled layout:** adjacency and full vector share a page;
- **decoupled layout:** topology/quantized code and full vector live on different pages.

Skipping exact distance computation is not automatically an SSD-I/O saving in a coupled layout.

---

## 4. PageTxn-ANN

### Current status

The crash-consistency problem is real, but a generic multi-page WAL/redo protocol is not sufficient novelty.

Do not implement PageTxn-ANN yet.

### Paper-only uniqueness gate

PageTxn survives only if it identifies an ANN-specific intermediate-state invariant unavailable to a generic WAL design.

Examples of questions to settle:

- Can a partially installed graph update remain query-safe?
- Which missing reverse edges are temporarily tolerable?
- Can reachability or recall degradation be bounded during recovery?
- Can commit latency be reduced by exposing query-safe partial states?
- Can recovery exploit graph redundancy to avoid replaying all writes?
- Is there a graph-specific atomicity unit smaller than the full multi-page update?

Allowed outcomes:

- `PASS-ANN-SPECIFIC-INVARIANT`
- `KILL-GENERIC-TRANSACTION-PACKAGING`
- `INCONCLUSIVE`

Only `PASS-ANN-SPECIFIC-INVARIANT` permits implementation.

---

## 5. Decision tree

### Case A: Z0B passes, Ambiguity A0 is killed

Proceed to the ZNS ANN-specificity gate.

### Case B: Z0B fails, Ambiguity A0 yields a valid salvaged object

Build only a small proof-of-concept for the salvaged object.

### Case C: Z0B passes and Ambiguity A0 passes

Compare them using:

- novelty strength;
- ability to state a theorem or invariant;
- system depth;
- implementation effort;
- evaluation clarity;
- risk of direct prior-work overlap.

Select exactly one.

### Case D: both fail

Run the PageTxn paper-only uniqueness gate.

### Case E: all three fail

Close the current local search space. Then run a new **problem-discovery** process, not another free-form idea-generation process.

The new discovery process must begin from measured system pathologies or unavailable capabilities, and must forbid renaming or recombining the following exhausted axes:

- local graph repair;
- lazy repair without a new invariant;
- ordinary batching/coalescing;
- page-layout repacking;
- beam/degree tuning;
- cache policy variants;
- arbitrary quantization heuristics;
- generic WAL/MVCC packaging;
- hot/cold ZNS placement without ANN-specific evidence.

---

## 6. Required reporting style

For each active gate, report:

1. exact question;
2. evidence collected;
3. failed assumptions;
4. pass/kill outcome;
5. what the result proves;
6. what it explicitly does not prove;
7. files and commands needed for reproduction.

Avoid roadmap inflation. Do not design a full system before the preceding gate passes.

---

## 7. Immediate next actions

1. Check Z0B execution status without changing the experimental protocol.
2. If Z0B is complete, evaluate it strictly under the allowed outcomes.
3. If Z0B is still running, continue Ambiguity A0.
4. Do not start PageTxn implementation.
5. Do not run broad idea-discovery.
6. Return a concise status message and place detailed reasoning/results in `share/`.
