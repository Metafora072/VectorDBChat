# T2-A0: Deterministic State-Machine Closure Spec

**Date**: 2026-07-19
**Goal**: Verify whether a capacity-limited memory system with semantic miss intervention creates path-dependent behavior in a deterministic agent.

---

## Agent State Machine

### States
```
S = (task_phase, memory_set, active_cache, capacity)
```

- `task_phase ∈ {0, 1, 2, ..., P}` — current step in a multi-step task
- `memory_set: Dict[int, Memory]` — all stored memories (durable)
- `active_cache: Set[int]` — IDs currently in cache (size ≤ capacity)
- `capacity: int` — max cache entries

### Memory Object
```python
Memory = {
    "id": int,
    "content": str,       # deterministic content
    "importance": float,   # used for eviction priority
    "access_count": int,
    "created_at": int      # step when created
}
```

### Transition Rules (deterministic)

At each step t, the agent:

1. **Query**: Generate a deterministic query based on (task_phase, last_action_result)
   - Query = hash(task_id, task_phase, last_result) → selects which memory IDs are "relevant"

2. **Retrieve**: Look up relevant memories
   - If relevant ID ∈ active_cache → **HIT**: return memory content
   - If relevant ID ∈ memory_set but ∉ active_cache → **SEMANTIC MISS**: return `None` (NOT the memory content — this is the key intervention)
   - If relevant ID ∉ memory_set → **ABSENT**: return `None`

3. **Act**: Deterministic action based on (task_phase, retrieved_content_or_None)
   - If retrieved = content → action_A (uses the information)
   - If retrieved = None → action_B (acts without the information, possibly worse)
   - Action may create new memories or modify existing ones

4. **Write**: If action creates/modifies a memory, add to memory_set. If cache full, evict lowest-importance entry.

5. **Evaluate**: After P steps, check if task succeeded (deterministic success criterion)

### Key Design Choice: Semantic Miss ≠ Transparent Miss

In a traditional cache, a miss fetches from backing store — same result, just slower. Here, a semantic miss returns `None` because the agent's "attention" is capacity-limited. This models:
- LLM context window limits (can't fit everything)
- Agent memory retrieval budget (can only retrieve K items per step)
- Cognitive load (agent processes only what's in working memory)

This IS the feedback loop: miss → different action → different writes → different future cache contents → different future misses.

---

## Experiment Protocol

### Tasks

5 deterministic tasks, each with P=20 steps. Each task has:
- A set of 50 "useful" memories (seeded at start)
- 10 "critical" memories (without these, task fails with high probability)
- 40 "helpful" memories (improve success but not required)
- Success criterion: deterministic function of actions taken

### Capacity Sweep with Carried State

**Phase 1 — Downward sweep (carried state)**:
```
Step 1: capacity=50 (full). Run all 5 tasks. Record success, cache contents, writes.
Step 2: capacity=40. Evict 10 lowest-importance. Run 5 NEW tasks. State carries forward.
Step 3: capacity=30. Evict 10 more. Run 5 NEW tasks.
Step 4: capacity=20. Evict 10 more. Run 5 NEW tasks.
Step 5: capacity=10. Evict 10 more. Run 5 NEW tasks.
```

**Phase 2 — Upward sweep (carried state from Phase 1 endpoint)**:
```
Step 6: capacity=20. No eviction needed (cache has ≤10). Run 5 NEW tasks.
Step 7: capacity=30. Run 5 NEW tasks.
Step 8: capacity=40. Run 5 NEW tasks.
Step 9: capacity=50. Run 5 NEW tasks.
```

**Fork control** at capacity=30 (Step 3 checkpoint):
- Fork A: continue downward (→20→10→20→30)
- Fork B: stay at 30, run same task sequence as Fork A
- Compare: does Fork A at capacity=30 (reached via 10) differ from Fork B at capacity=30 (never went lower)?

### Measurements

For each step:
- Task success rate (out of 5 tasks)
- Cache contents (which IDs are cached)
- Memory set (what was written during tasks)
- Jaccard distance of cache contents vs full-capacity baseline
- Number of semantic misses per task

### Decision Criteria

**Path dependence exists if**: Fork A (went through capacity=10) has different cache contents AND different success rate compared to Fork B (stayed at capacity=30), even though both are now at capacity=30.

**Path dependence is from feedback loop if**: The difference is NOT explained by accumulated memory differences alone (check by resetting memory_set to fork point while keeping different caches).

**Hysteresis exists if**: Downward curve (success at 30 when coming from 50) ≠ upward curve (success at 30 when coming from 10), and the difference is stable across random seeds (5 seeds).

---

## Implementation Notes

- Pure Python, no external dependencies
- Deterministic PRNG with seed for reproducibility
- All state serializable to JSON for checkpointing
- ~100 lines of agent logic, ~50 lines of experiment harness
- Expected runtime: <5 minutes
- Output: `t2_a0_results.md` with success curves, cache divergence, fork comparison

---

## What This Does NOT Test

- LLM stochasticity (eliminated by design)
- Real task complexity (toy tasks only)
- Real memory retrieval quality (deterministic lookup)
- "Phase transition" (too small to see critical phenomena)

## What This DOES Test

- Whether semantic miss intervention creates feedback loop (vs transparent miss)
- Whether carried state produces path dependence (vs fresh reset)
- Whether fork control can isolate cache-content vs memory-content effects
- Whether the experimental protocol is sound before investing in LLM-based scaling
