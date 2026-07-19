# Phase 4: Critical Review + T5 Novelty Check (Codex GPT-5.6-sol)

**Date**: 2026-07-19
**Method**: Local review loop (no sub-agent delegation) + 8 targeted web searches for T5

---

## T5 Novelty Check: Verifiable Forgetting with Semantic Deletion Closure

**Verdict**: SCOOPED | **Novelty Score**: 2/10

**Direct prior work found**:

1. **MEMOREPAIR** (arXiv:2605.07242, May 2026): Barrier-first cascade-repair contract for agentic memory. Formalizes the cascade update problem (source deletion/correction → derived artifacts become stale). Uses predecessor closure, barrier withdrawal before repair, validated successor republication. Reduces invalidated-memory exposure from 69.8-94.3% to 0%. Solved via s-t min-cut. **This directly covers "semantic deletion closure" with a formal contract.**

2. **Agentic Unlearning / SBU** (arXiv:2602.17692, Feb 2026): Introduces agentic unlearning — removing specified information from both model parameters AND persistent memory. Memory pathway performs **dependency closure-based unlearning**: prunes isolated entities, logically invalidates shared artifacts. Addresses parameter-memory backflow (retrieval reactivates parametric remnants). **This directly covers the "semantic residue" problem.**

3. **FadeMem** (arXiv:2601.18642, Jan 2026): Biologically-inspired forgetting with differential decay, dual-layer memory, LLM-guided conflict resolution. 45% storage reduction.

4. **HUKA** (arXiv:2007.14864): Provenance polynomials for tracking KG query result derivation; maintains provenance under dynamic updates (insertions + deletions).

5. **Certified Data Removal** (ICML 2020, Guo et al.): Formal cryptographic definition of certified removal — model from which data is removed indistinguishable from one that never observed it.

6. **CASCADEKG** (ACL Findings 2026): Multi-hop cascading update formalization for KG.

**Overlap analysis**: T5's five claimed contributions are each individually covered:
- Problem definition (semantic residue from deletion): MEMOREPAIR + Agentic Unlearning
- Derived artifact closure: MEMOREPAIR (predecessor closure) + SBU (dependency closure)
- Minimal support sets: MEMOREPAIR (repair-cost tradeoff via min-cut)
- Retrieval boundary blocking: MEMOREPAIR (barrier-first withdrawal)
- Canary-based evaluation: Agentic Unlearning (residue measurement)

**Remaining space**: Only "incomplete/probabilistic provenance" (when provenance is unknown or approximate) might survive. Or using M0-M3 to trace from semantic impact to physical persistent copies (cross-layer deletion audit).

**Recommendation**: **KILL** as originally framed. MEMOREPAIR + Agentic Unlearning are fatal overlaps.

---

## T1: Semantic Write Amplification of Agent Memory (Measurement Paper)

**Reviewer Score**: 5/10

**Strongest Objection**: "This is incremental view maintenance cost measurement with agent-specific naming. The architecture (evidence/interpretation separation) is covered by Eywa; the propagation is covered by Kumiho/CASCADEKG. What's the systems contribution beyond applying M0-M3 write attribution to a new workload?"

**Most Likely Failure Mode**: Write amplification turns out to be moderate (2-5x) and dominated by embedding recomputation, which is an API cost not a storage cost. The measurement result doesn't motivate a new system design.

**Is Negative Result Publishable?**: Yes — if per-revision amplification is low, it settles the question of whether agent memory needs a custom storage engine (answer: no, use existing KV + embedding service). This is valuable for the community.

**Concrete Improvements**:
1. Don't claim evidence/interpretation separation as novel architecture — cite Eywa, Kumiho, TierMem
2. Define the amplification factor formally and make it reproducible across systems
3. Include model/prompt upgrade as an invalidation source (unique angle)
4. Compare against Mem0, Zep, Letta with real agent trajectories (not synthetic)
5. Show amplification varies by operation type (update vs merge vs forget) — this decomposition is new
6. If epoch consolidation works, demonstrate I/O reduction at fixed freshness/correctness

**Final Recommendation**: PROCEED WITH CAUTION. Viable as measurement/characterization paper for FAST. Must reposition contribution carefully.

---

## T2: Closed-Loop Working Set Phase Transition

**Reviewer Score**: 6/10

**Strongest Objection**: "MemoryArena and 'How Memory Management Impacts LLM Agents' (ACL 2026) already show that memory capacity affects agent behavior. Your claim of 'phase transition' and 'hysteresis' may be artifacts of task structure (hard minimum information requirements) rather than genuine emergent phenomena."

**Most Likely Failure Mode**: Experiments show smooth degradation with a soft knee, not a sharp phase transition. The hysteresis effect is within noise / random model variance. Result reduces to "cache misses change behavior" — already known.

**Is Negative Result Publishable?**: Partially — proving that agent memory degradation is smooth (no phase transition) would counter the intuition, but "we measured and found smooth degradation" is weak for a top venue unless accompanied by a model explaining why.

**Concrete Improvements**:
1. Must explicitly compare against fixed-trace replay (the control) to isolate feedback loop contribution
2. Use deterministic (cached) LLM outputs to eliminate model stochasticity — this is critical for claiming phase transition
3. Run bidirectional capacity sweep (decrease then increase) to test hysteresis — this is the novel experiment
4. Multiple task domains to show generality (code repair, interactive QA, planning)
5. If phase transition exists, build a simple analytical model (mean-field or Markov chain) predicting the critical capacity
6. Cite MemoryArena, Memory in the Loop, ACL 2026 as establishing the feedback loop; position your contribution as the first quantitative characterization of its nonlinear consequences

**Final Recommendation**: PROCEED WITH CAUTION. Highest novelty potential but highest empirical risk. Small-scale pilot FIRST.

---

## Overall Ranking (Updated)

| Rank | Idea | Score | Verdict | Risk | Action |
|------|------|-------|---------|------|--------|
| 1 | **T2 Phase Transition** | 6/10 | INCREMENTAL | HIGH (depends on phenomenon existing) | Pilot first |
| 2 | **T1 Write Amplification** | 5/10 | INCREMENTAL | LOW (measurement always publishable) | Reposition as measurement paper |
| 3 | ~~T5 Verifiable Forgetting~~ | 2/10 | SCOOPED | — | KILL (MEMOREPAIR + SBU) |
| 4 | ~~T4 Code Understanding~~ | 3/10 | INCREMENTAL | HIGH | Deprioritize |
| 5 | ~~T3 Side-Effect Receipts~~ | 2/10 | SCOOPED | — | KILL (ACRFence + DART) |

## Strategic Recommendation

**Start with T1** (measurement paper, low risk, 3-5 weeks, directly reuses M0-M3). Even if the amplification finding is modest, it's publishable as a characterization study. This builds infrastructure that T2 and potential follow-ups can reuse.

**Parallel small pilot for T2** (1-2 weeks): Run the bidirectional capacity sweep with cached model outputs on 10 tasks. If hysteresis is real and reproducible, T2 becomes the stronger paper. If not, T1 is the fallback.

**Do not invest in T3, T4, or T5** — all have fatal novelty issues.
