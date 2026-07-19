# Phase 4.5: Method Refinement & Experiment Plan

**Date**: 2026-07-19
**Strategy**: T1 as primary (low risk), T2 as parallel pilot (high reward)

---

## T1: Semantic Write Amplification of Agent Memory

### Problem Anchor (frozen)

> Agent memory systems (Mem0, Zep, MAGMA, Letta) store multiple derived representations per memory object: raw text, embeddings, provenance links, conflict edges, summaries, cached plans. When a memory is revised, how many bytes must be rewritten across all representations? How does this "semantic write amplification" (SWA) vary by operation type, memory layout, and system?

### Contribution Positioning

**NOT claiming**: evidence/interpretation separation as novel (Eywa), dependency propagation as novel (Kumiho/CASCADEKG), agent memory formalization as novel (GEM).

**Claiming**:
1. **New metric**: SWA — per-operation physical write cost normalized by logical operation size, decomposed by target (text, embedding, provenance, conflict, summary, plan cache)
2. **First cross-system measurement**: SWA measured across 3+ agent memory systems under controlled workloads
3. **Operation decomposition**: SWA varies by operation type (insert ≪ update < merge < forget < model-upgrade); this ordering is novel
4. **Layout optimization**: Evidence/interpretation separation (citing Eywa as prior) with epoch consolidation reduces SWA; M0-M3 write attribution quantifies exactly where

### Method

**Phase A: Memory Layer Implementation (Week 1-2)**

Build slim GEM-compatible memory layer with 5 operation types:
- `INSERT(text, metadata)` → create raw + embedding + initial provenance
- `UPDATE(id, new_text)` → revise text + re-embed + update provenance + check conflicts
- `MERGE(id1, id2)` → combine entries + re-embed merged + redirect provenance + resolve conflicts
- `FORGET(id)` → mark deleted + propagate to derived summaries + invalidate cached plans
- `MODEL_UPGRADE()` → re-embed all with new model + re-derive all interpretations

Storage backends:
- Layout A: **Whole-object** (single record per memory, all fields together)
- Layout B: **Field-separated** (text, embedding, provenance, conflict in separate stores)
- Layout C: **Evidence/Interpretation** (immutable evidence log + mutable interpretation versions with epoch consolidation)

**Phase B: Write Attribution (Week 2-3)**

Instrument with M0-M3:
- M0: Per-syscall write bytes (pwrite64 interposition)
- M1: Per-file write distribution (XFS extent mapping)
- M2: Page lifecycle (clean→dirty→writeback→reclaim)
- M3: Cross-layer attribution (operation → file writes → block device I/O)

Key metrics per operation:
- `SWA_total` = total physical bytes written / logical operation payload bytes
- `SWA_text`, `SWA_embed`, `SWA_prov`, `SWA_conflict`, `SWA_summary`, `SWA_plan`
- `API_calls` = number of LLM/embedding API calls triggered
- `p99_latency` = end-to-end operation latency

**Phase C: Workload Generation (Week 2-3, parallel with B)**

Real agent trajectory replay:
1. Code repair tasks (SWE-bench-like): generate 30 episodes, extract memory operations
2. Interactive QA (LoCoMo/LongMemEval subset): 30 sessions, extract operations
3. Planning tasks: 20 multi-step plans with memory revision
4. Synthetic stress: 10K operations with controlled revision ratio (10%, 30%, 50%, 80%)

Also measure Mem0 and Zep (if they expose write paths) on same workloads.

**Phase D: Experiment Execution (Week 3-4)**

| Experiment | Question | Design |
|-----------|----------|--------|
| E1: SWA by operation | Which operations amplify most? | 10K each of INSERT/UPDATE/MERGE/FORGET/MODEL_UPGRADE, Layouts A/B/C |
| E2: SWA by layout | Does separation reduce amplification? | Same workload, 3 layouts, measure total I/O |
| E3: Epoch consolidation | Does batching interpretation updates help? | Layout C with epoch sizes 1/10/100/1000 |
| E4: Real workload | SWA on realistic agent trajectories | Code/QA/Planning workloads, all layouts |
| E5: Cross-system | How do existing systems compare? | Mem0/Zep on same workloads (black-box I/O measurement) |
| E6: Model upgrade storm | What happens when embedding model changes? | Re-embed 10K memories, measure cascade |

**Phase E: Paper Writing (Week 4-5)**

Target: **FAST 2027** (submission ~Sep 2026)

Paper structure:
1. Observation: agent memory is write-heavy with cascading derived representations
2. Metric: SWA definition and decomposition
3. Measurement: cross-system, cross-workload, cross-operation characterization
4. Finding: [expected] embedding recomputation dominates; model upgrade is catastrophic; merge/forget amplify more than insert/update
5. Optimization: epoch consolidation reduces SWA by X% at cost of Y staleness
6. Lesson: when agent memory needs a custom engine (high revision ratio) vs when existing KV suffices (insert-dominant)

### Risk Mitigation

- **If SWA is low across all systems**: publishable negative result ("agent memory doesn't need custom storage")
- **If SWA is high but Eywa-style separation doesn't help**: publishable finding ("the bottleneck is embedding API, not storage layout")
- **If M0-M3 don't capture all writes**: fall back to strace + blktrace + accounting cgroups

---

## T2: Closed-Loop Working Set Phase Transition (Pilot)

### Problem Anchor (frozen)

> When an agent's memory cache is too small, cache misses change what the agent recalls, which changes its actions, which changes what it writes to memory, which changes future access patterns. Does this feedback loop cause nonlinear performance collapse (phase transition)? Does capacity recovery follow a different path (hysteresis)?

### Pilot Design (Week 1-2, parallel with T1 Phase A)

**Setup**:
- 10 long-horizon tasks (code repair + interactive QA), each requiring 50+ memory accesses
- Cached LLM outputs (deterministic): pre-generate model responses for each possible memory context
- Memory pool: 500 memories per task, varying cache sizes from 500 (full) down to 10 (extreme pressure)

**Protocol**:
1. **Downward sweep**: Run each task at cache sizes [500, 400, 300, 200, 150, 100, 75, 50, 25, 10]
2. **Upward sweep**: Run same tasks at cache sizes [10, 25, 50, 75, 100, 150, 200, 300, 400, 500]
3. **Control (fixed-trace)**: Record access sequence from full-cache run, replay same sequence at each cache size (no feedback loop)
4. **5 seeds per configuration** (different random tiebreaking in LRU/cache policy)

**Metrics**:
- Task success rate (binary per task, averaged over seeds)
- Access pattern KL divergence vs full-cache baseline
- NVMe read I/O (cache miss → disk read)
- Memory content drift (Jaccard distance of cached set vs full-cache cached set)

**Decision criteria**:
- **Phase transition**: Success rate drops >30% within a 2x capacity change window
- **Hysteresis**: Downward and upward curves differ by >10% at same capacity point (averaged over tasks)
- **Feedback loop effect**: Real closed-loop curve differs from fixed-trace control by >15%

**If pilot passes**: Expand to 50 tasks, 4 domains, multiple cache policies (LRU, LFU, semantic-heat), build analytical model. Target FAST 2027 or NeurIPS 2027.

**If pilot fails** (smooth degradation, no hysteresis): Document as negative finding, fold into T1 paper as supplementary characterization ("agent cache degradation is smooth, not catastrophic").

### Implementation Notes

- Use SQLite + FAISS for memory store (simple, instrumented)
- Cache policy: LRU with semantic similarity tiebreaking
- LLM caching: map (task_id, memory_context_hash) → pre-generated response
- Need ~500 × 10 tasks × 10 cache sizes × 2 directions × 5 seeds = 500K cached responses
- Estimate: 2-3 days LLM API cost for pre-generation, then experiments run on CPU/NVMe only

---

## Execution Timeline

| Week | T1 | T2 |
|------|----|----|
| 1 | Memory layer + layouts A/B/C | Task selection + LLM response caching |
| 2 | M0-M3 instrumentation + workload generation | Run pilot (down/up sweeps) |
| 3 | E1-E3 experiments | Analyze pilot results → GO/NO-GO |
| 4 | E4-E6 experiments | If GO: expand to full experiment |
| 5 | Paper writing | If GO: integrate into T2 paper |

## Decision Point: End of Week 2

After T2 pilot results:
- **If hysteresis confirmed**: T2 becomes primary paper, T1 becomes supporting measurement
- **If hysteresis absent**: T1 is sole paper, T2 negative result folded in
- **If both negative**: Re-examine T7 (Regret-Driven Memory Admission) or T8 (Prospective Memory Trigger Index) from Phase 2 list
