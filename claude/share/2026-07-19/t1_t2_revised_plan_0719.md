# T1/T2 Revised Plan — Addressing Codex Preflight

**Date**: 2026-07-19
**Context**: Codex preflight raised valid technical critiques. PZ directs: don't constrain to M0-M3, focus on publication, AI handles workload.

---

## Accepted Critiques & Fixes

### T1 Fixes

**Issue 1: SWA denominator incomparable across operations**
- Codex is right. `physical_bytes / logical_payload_bytes` breaks for FORGET (payload = 1 ID) and MODEL_UPGRADE (payload = 1 model name).
- **Fix**: Report three metrics per operation:
  - `B_abs(op)` — absolute bytes written (all layers summed)
  - `B_per_obj(op)` — bytes written per affected object
  - `B_ratio(op)` — bytes written / authoritative logical-state delta (only where delta > 0)
- MODEL_UPGRADE is a corpus-level event; normalize by N_affected × mean_object_size
- Drop the `INSERT ≪ UPDATE < MERGE < FORGET < MODEL_UPGRADE` ordering claim until data supports it

**Issue 2: "Physical writes" conflates layers**
- Codex is right. Clearly separate:
  - `W_app` — application write/pwrite/writev bytes (LD_PRELOAD)
  - `W_fs` — filesystem dirty pages (cgroup writeback accounting)
  - `W_blk` — block device I/O (blktrace/cgroup blkio)
  - Do NOT claim W_NAND without device SMART/telemetry
- Add operation ID tagging, commit/quiescence boundary, unattributed bucket
- Use cgroup v2 isolation for clean attribution

**Issue 3: Cross-system semantics not comparable**
- Codex is right. Define canonical postcondition contract FIRST:
  - INSERT: text stored, embedding computed, provenance root created
  - UPDATE: text replaced, embedding recomputed, provenance chain extended, conflicts checked
  - MERGE: two entries unified, embeddings recomputed, provenance merged
  - FORGET: entry marked deleted, downstream summaries invalidated
  - MODEL_UPGRADE: all embeddings recomputed with new model
- Compare only operations where systems implement equivalent postconditions
- Systems with fewer derived representations will naturally have lower B_abs — that IS a finding (simpler systems have lower amplification)

**Issue 4: M0-M3 not directly reusable**
- Accepted. Only M0's LD_PRELOAD write ledger is partially portable. Everything else is new.
- **Not a blocker**: Build new instrumentation from scratch. PZ says AI handles this.
- New stack: LD_PRELOAD write/fsync ledger (adapted from M0) + cgroup v2 blkio + SQLite DBSTAT + application-level change ledger

**Issue 5: No Mem0/Zep/Letta installed, ext4 not XFS**
- Install what's needed. Use ext4 (XFS not required for T1 — we're not doing extent-level attribution, we're doing syscall + cgroup + application-level tracking)
- Mem0 is pip-installable. Zep has a Docker image. Start with SQLite-only prototype, add real systems in Phase C.

### T2 Fixes

**Issue 1: Transparent cache miss doesn't close the loop** ★ Critical
- Codex is absolutely right. If miss = transparent disk read returning the same memory, there's no semantic feedback.
- **Fix**: Define explicit **semantic miss intervention**:
  - Option A: **Deadline miss** — if retrieval exceeds T ms, return empty/degraded result
  - Option B: **Capacity-limited active set** — only top-K most recent/relevant memories are "active"; others are forgotten (not just slow to access)
  - Option C: **Retrieval quality degradation** — under capacity pressure, use cheaper/less accurate retrieval (e.g., keyword-only vs semantic)
- The intervention IS the independent variable, not cache size alone
- **Null control**: same agent with unlimited active set (transparent backing store)

**Issue 2: Fresh-reset down/up sweep can't show hysteresis** ★ Critical
- Codex is right. If each capacity point resets, order doesn't matter.
- **Fix**: **Carried-state protocol**:
  - Start at capacity C_high. Run task batch B1. Memory accumulates.
  - Reduce capacity to C_mid. Memories evicted. Run task batch B2 (different tasks).
  - Reduce to C_low. Run B3.
  - Increase back to C_mid. Run B4 (same task distribution as B2).
  - Compare success(B2 at C_mid, reached from high) vs success(B4 at C_mid, reached from low)
  - If they differ, there's path dependence.
  - **Fork control**: At the C_mid checkpoint, fork state. Run one copy down then back up, another stays. Compare at the same final capacity.

**Issue 3: Combinatorial context space**
- Accepted. Drop the 500K pre-generated responses.
- **Fix for A0**: Use deterministic finite-state agent (no LLM). Define explicit state machine:
  - States: (task_phase, memory_set, active_cache)
  - Transitions: deterministic rules based on recalled content
  - Total reachable states bounded and enumerable
- **Fix for later**: On-demand LLM memoization with hash-based caching, hard cap on unique calls

**Issue 4: Decision criteria false positives**
- Accepted. Replace fixed thresholds with:
  - Per-task paired curves (not averaged)
  - Bootstrap CI on paired difference (down-path vs up-path at same capacity)
  - Grid refinement around any observed knee
  - Don't call it "phase transition" until critical-point evidence; call it "nonlinear knee" or "capacity cliff"

---

## Revised Execution Plan

### Immediate: T1-A0 Metric Closure (2 hours)

**Goal**: Verify that B_abs, B_per_obj, B_ratio are well-defined and measurable on a minimal prototype.

**Setup**:
- SQLite-only, single process, 1K objects, ≤100 mutations
- 3 tables: `memories` (text+metadata), `embeddings` (fake 384-dim float vectors), `provenance` (parent_id links)
- LD_PRELOAD write ledger (adapted from M0) counting bytes per fd per operation
- Application-level change ledger: for each operation, record {op_type, affected_ids, pre/post state hash}
- SQLite DBSTAT for page-level attribution

**Deliverable**:
- Table of B_abs / B_per_obj / B_ratio for INSERT/UPDATE/MERGE/FORGET on 3 layouts
- Unattributed byte bucket (WAL, journal, checkpoint overhead)
- Decision: does the metric have meaningful dynamic range? If B_abs(UPDATE) ≈ B_abs(INSERT), the story is weak.

**Hard bounds**: Zero API calls. All data on `/mnt/agentstorage_nvme`. ≤2h wall, ≤5GiB NVMe, ≤8GiB RSS. Stop on violation.

### Week 1: T1 Full Prototype + T2-A0

**T1**: If A0 shows meaningful dynamic range:
- Install Mem0 (pip install mem0ai)
- Implement canonical operation adapter for Mem0
- Run same mutation workload on Mem0, measure B_abs/B_per_obj via cgroup + strace
- Compare with SQLite prototype

**T2-A0**: Deterministic state-machine closure
- Define 5-state finite agent with explicit memory-dependent transitions
- Implement capacity-limited active set (semantic miss = return nothing)
- Run toy with carried state: C_high→C_low→C_high
- Check if path dependence exists even in toy

### Week 2: Scale + Decision

Based on A0/Week 1 results:
- If T1 has dynamic range + cross-system variation → expand to full paper
- If T2-A0 shows path dependence → design LLM-based full experiment
- If neither → re-examine T7/T8 from Phase 2 backup list

---

## Key Principle Change

PZ's direction is clear: **don't gate-keep endlessly; build and measure**. The A0 exercises above are 2-hour tasks, not multi-week preflight campaigns. If the metric works, scale. If it doesn't, pivot. AI handles implementation velocity.

The original plan overclaimed (M0-M3 reuse, evidence/interpretation novelty, 500K responses). Codex correctly identified those gaps. But the fix is to correct the claims and build, not to add more preflight gates.
