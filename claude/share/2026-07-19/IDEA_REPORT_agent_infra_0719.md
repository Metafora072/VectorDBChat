# Idea Discovery Report: Agent Infrastructure

**Direction**: Agent-related systems and infrastructure, no GPU dependency
**Date**: 2026-07-19
**Pipeline**: research-lit → idea-creator (Codex brainstorm) → novelty-check (Codex cross-review) → critical-review (Codex) → method-refinement (Claude)
**Ideas evaluated**: 17 generated → 8 survived filtering → 5 novelty-checked → 2 recommended

---

## Executive Summary

From a broad search across Agent infrastructure (memory, tool use, multi-agent coordination, code agents, durable execution, observability), two ideas survived strict novelty checking and critical review:

1. **T1 Semantic Write Amplification of Agent Memory** (FAST 2027) — Define and measure per-operation write amplification across agent memory representations. Low risk, directly reuses M0-M3 infrastructure. Negative result also publishable.

2. **T2 Closed-Loop Working Set Phase Transition** (FAST/NeurIPS 2027) — Test whether agent memory cache exhibits nonlinear collapse and hysteresis under the closed feedback loop. Highest novelty but depends on phenomenon existing. Pilot first.

**Strategy**: Start T1 (primary, 3-5 weeks), run T2 pilot in parallel (1-2 weeks). Decision point at week 2.

---

## Literature Landscape

See `claude/share/2026-07-19/agent_infra_landscape_0719.md` for full survey.

**Key findings**:
- Agent memory is the most active and least mature area (GEM formalization only, no systems paper)
- 2026 explosion: MEMOREPAIR, Agentic Unlearning, Eywa, Kumiho, TierMem, MemoryArena, Memory in the Loop, ACL 2026 memory management study — field is moving FAST
- Tool recovery (ACRFence, DART), code understanding (RepoDoc, Completion Semantics) also rapidly filling
- "Agent Data Management" remains wide open for systems research, but individual sub-problems are being picked off quickly

---

## Recommended Ideas

### T1: Semantic Write Amplification of Agent Memory — PRIMARY

- **Hypothesis**: Agent memory revision cascades across multiple derived representations, causing write amplification far exceeding simple insert. Layout separation and epoch consolidation can reduce it.
- **Contribution**: New metric (SWA) + cross-system measurement + layout optimization
- **Novelty**: INCREMENTAL (4/10) — Eywa/Kumiho cover architecture; SWA metric and cross-system characterization are new
- **Feasibility**: HIGH — 3-5 weeks, M0-M3 ready, no GPU needed
- **Risk**: LOW — even negative result (SWA is low) is publishable
- **Reviewer's likely objection**: "This is view maintenance cost measurement, not a new system"
- **Mitigation**: Don't claim architectural novelty; contribution is the metric and measurement
- **Target venue**: FAST 2027
- **Experiment plan**: `claude/share/2026-07-19/t1_t2_experiment_plan_0719.md`

### T2: Closed-Loop Working Set Phase Transition — PILOT

- **Hypothesis**: Agent cache miss changes subsequent access distribution via feedback loop. Below critical capacity, task success collapses non-smoothly with recovery hysteresis.
- **Contribution**: First quantitative characterization of nonlinear consequences of agent memory feedback loop
- **Novelty**: INCREMENTAL (5/10) — MemoryArena/Memory-in-the-Loop establish feedback; phase transition/hysteresis uncharted
- **Feasibility**: MEDIUM — needs cached LLM outputs for deterministic replay
- **Risk**: HIGH — if no phase transition exists, reduces to known result
- **Reviewer's likely objection**: "Is this a genuine phase transition or just task minimum information requirements?"
- **Mitigation**: Fixed-trace control isolates feedback loop contribution; multiple task domains
- **Target venue**: FAST 2027 or NeurIPS 2027
- **Pilot design**: `claude/share/2026-07-19/t1_t2_experiment_plan_0719.md`

---

## Eliminated Ideas

| Idea | Phase Killed | Reason | Key Scoop |
|------|-------------|--------|-----------|
| T3 Side-Effect Receipts | Phase 3 (novelty) | SCOOPED — ACRFence + DART cover agent-specific recovery | arXiv:2603.20625, 2605.23311 |
| T5 Verifiable Forgetting | Phase 4 (novelty) | SCOOPED — MEMOREPAIR + Agentic Unlearning cover deletion closure | arXiv:2605.07242, 2602.17692 |
| T4 Code Understanding | Phase 3 (novelty) | INCREMENTAL 3/10 — RepoDoc + Completion Semantics combination | arXiv:2604.26523, 2607.12490 |
| T6 Causal Belief Snapshot | Phase 2 (filter) | Medium risk, could be generic MVCC | — |
| T7 Regret Memory Admission | Phase 2 (filter) | HIGH risk, needs counterfactual replay | backup if T1/T2 fail |
| T8 Prospective Memory Index | Phase 2 (filter) | Medium risk, narrow scope | backup |
| Semantic Phantom Read | Phase 2 (filter) | CoAgent (arXiv:2606.15376) overlap | — |
| Minimal Causal Trace | Phase 2 (filter) | Reduces to program slicing | — |
| Context-Consistent Replay | Phase 2 (filter) | Too narrow for full paper | — |
| Experience Graph Compression | Phase 2 (filter) | Depends on Experience Graphs adoption | — |

---

## Pipeline Lessons (vs First Pipeline)

| Issue | First Pipeline (DiskANN) | Second Pipeline (Agent Infra) |
|-------|-------------------------|------------------------------|
| Novelty inflation | 7/10 on average, Gpt found all inflated | Codex cross-review caught early, scored 2-5/10 |
| "Apply X to Y" | 8/10 ideas were this pattern | Filtered in Phase 2 by requiring "why not apply X to Y" for each idea |
| Field coverage | Underestimated 6 crowded areas | 15+ web searches per idea, found 2026 scoops (MEMOREPAIR, ACRFence) |
| Negative results | Not considered | T1 explicitly designed with publishable negative result |
| Risk management | All-or-nothing | T1 (low risk) + T2 (high risk pilot) dual strategy |

---

## Decision Tree

```
Week 2: T2 pilot results
├── Hysteresis confirmed → T2 = primary, T1 = supporting measurement
├── Hysteresis absent → T1 = sole paper, T2 negative folded in
└── Both negative → Re-examine T7 (Regret Admission) or T8 (Trigger Index)
```

---

## References (key prior work to cite)

### Agent Memory Systems
- GEM (arXiv:2605.26252) — formalization of agent memory operations
- Eywa (arXiv:2605.30771) — evidence/interpretation separation
- Kumiho (arXiv:2603.17244) — immutable revisions + dependency cascade
- TierMem (arXiv:2602.17913) — tiered memory with provenance
- MEMOREPAIR (arXiv:2605.07242) — barrier-first cascade repair
- Agentic Unlearning (arXiv:2602.17692) — dependency closure unlearning
- Agent Memory Characterization (arXiv:2606.06448) — construction cost measurement
- CASCADEKG (ACL Findings 2026) — multi-hop cascading KG updates
- FadeMem (arXiv:2601.18642) — biologically-inspired forgetting

### Agent Memory Evaluation
- MemoryArena (arXiv:2602.16313) — closed-loop memory evaluation
- Memory in the Loop (arXiv:2607.05690) — causal intervention on memory latency
- How Memory Management Impacts LLM Agents (ACL 2026) — capacity-constrained experiments
- Pichay (arXiv:2603.09023) — context as working-set cache

### Agent Recovery
- ACRFence (arXiv:2603.20625) — irreversible effect recording + replay-or-fork
- DART (arXiv:2605.23311) — semantic recoverability boundary

### Code Understanding
- RepoDoc (arXiv:2604.26523) — persistent RepoKG + semantic impact propagation
- Completion Semantics (arXiv:2607.12490) — implicit assumption exposure

---

## Files Produced

| File | Content |
|------|---------|
| `claude/share/2026-07-19/agent_infra_landscape_0719.md` | Phase 1: Landscape survey |
| `claude/share/2026-07-19/agent_ideas_phase2_merged_0719.md` | Phase 2: Merged idea list (8 survivors) |
| `codex/share/2026-07-19/agent_ideas_novelty_check_0719.md` | Phase 3: Novelty check T1-T4 |
| `codex/share/2026-07-19/agent_ideas_critical_review_0719.md` | Phase 4: Critical review + T5 novelty |
| `claude/share/2026-07-19/t1_t2_experiment_plan_0719.md` | Phase 4.5: Method refinement + experiment plan |
| `claude/share/2026-07-19/IDEA_REPORT_agent_infra_0719.md` | Phase 5: This report |
