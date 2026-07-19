# T1-A0 SWA Analysis

**Status**: PASS — 3 layouts × 1100 operations (1000 bootstrap + 100 mutations) completed in 64.4s.

## Key Findings

### 1. SWA Has Meaningful Dynamic Range

MODEL_UPGRADE vs single-object mutation:
- Layout A: **324×** (3.93 MiB vs 12.42 KiB)
- Layout B: **64×** (2.02 MiB vs 32.53 KiB)
- Layout C: **99×** (2.18 MiB vs 22.54 KiB)

This is the core publishable result: a single "model upgrade" (re-embedding all objects) writes 64-324× more than a typical point mutation. In real agent systems, this means embedding model version changes dominate storage I/O cost.

### 2. Operation Ordering Is NOT Monotonic

Expected: INSERT < UPDATE < MERGE. Actual (all layouts):
- **UPDATE < INSERT**: 0.33× (A), 0.76× (B), 0.80× (C)
- **MERGE > UPDATE**: 5.64× (A), 3.08× (B), 2.54× (C)

UPDATE costs LESS than INSERT because INSERT allocates new B-tree pages while UPDATE rewrites in-place within existing pages. This is counterintuitive from a "semantic complexity" perspective but explained by SQLite page allocation. MERGE costs the most among point operations because it reads/writes two objects + deletes one.

### 3. Layout Matters (But Not How You'd Expect)

- **Layout A (monolithic)** is cheapest for point operations (INSERT, UPDATE, MERGE, FORGET)
- **Layout B (field-separated)** is cheapest for MODEL_UPGRADE (2.02 MiB vs 3.93 MiB)
- **Layout C (evidence-interpretation)** is intermediate

The B advantage for MODEL_UPGRADE comes from field separation: updating only the embedding table touches fewer pages. But for point operations, B is 2-3× more expensive because each operation touches 5 tables instead of 1.

This creates a design tension: optimize for common point operations (choose A) or optimize for rare but expensive bulk operations (choose B).

### 4. WAL Dominates B_abs

96-99% of B_abs is WAL/journal extent, not main-file growth. This means:
- The metric captures write intent accurately (what SQLite decides to write)
- But doesn't capture checkpoint rewrites to already-allocated pages
- For a full paper, would need blktrace/strace to get device-level writes

### 5. FORGET Is Cheap (But Has Cascade Cost)

FORGET averages only 5.26 KiB across all layouts (identical!). But it cascades: invalidating provenance chains and updating conflict sets of other objects. The cascade is small here (few conflicts in random text) but would be much larger with realistic semantic similarity.

## What This Means for the Paper

1. **SWA metric works**: Meaningfully differentiates operations and layouts
2. **Surprise finding**: Layout choice creates a tension between point-op cost and bulk-op cost — this is the "schema design tradeoff" angle for the paper
3. **WAL attribution gap**: Need device-level tracing for the full story (blktrace or io_uring instrumentation)
4. **Next step**: Scale to real agent workloads (LangChain/AutoGen memory traces) with actual semantic text

## Limitations

- Deterministic fake embeddings (no real model)
- Random text (no semantic structure → weak conflict detection)
- SQLite only (no comparison with other storage engines)
- File-extent metric (not block-I/O counter)

## Verdict

**T1 should proceed to A1**: The metric has dynamic range, the layout effect is real and surprising, and there's a clear paper story around "schema design tradeoffs for agent memory write amplification." A1 should use real agent traces and add blktrace instrumentation.
