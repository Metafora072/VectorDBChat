# Idea Discovery Report

**Direction**: Disk-resident ANN and vector search (systems + AI venues)
**Date**: 2026-07-18
**Pipeline**: research-lit → idea-creator → novelty-check → research-review → research-refine-pipeline

## Executive Summary

After surveying 32 recent papers, generating 21 ideas (10 Claude + 11 Codex GPT-5.4), deep novelty checking, external reviewer simulation, and 3-round method refinement, the recommended top idea is:

**ANN-on-ZNS Feasibility Frontier** — a trace-driven characterization of the GC write amplification boundary for graph ANN update workloads on append-only (ZNS) storage. This is the first GC feasibility analysis for this workload class, enabled by our unique M0-M3 syscall-level page-write dataset. Key empirical finding already confirmed: graph ANN has quasi-uniform page-touch distribution (Gini 0.03-0.29), unlike concentrated B-tree/Zipfian patterns (Gini ~0.82).

**Recommended next step**: Re-instrument M3 trace emission, implement zone-packing simulator, execute experiment plan (5-6 weeks).

---

## Literature Landscape
(Full report: `claude/share/2026-07-18/disk_ann_vector_search_landscape_0718.md`)

32 papers surveyed across 7 thematic areas. 7 structural gaps identified:
- G1: ZNS SSD + ANN (zero prior work) ← **TOP IDEA TARGETS THIS**
- G2: I/O complexity lower bounds (PODS 2020 partially covers)
- G3: KV cache vector index on SSD (very crowded — KVDrive, RetroInfer, ParisKV)
- G4: Quantization-topology co-design
- G5: Crash-consistent dynamic disk ANN
- G6: Formal freshness-recall tradeoff
- G7: Dynamic filtered ANN on SSD

---

## Ranked Ideas

### 🏆 Idea 1: ANN-on-ZNS Feasibility Frontier — RECOMMENDED

- **Hypothesis**: GC write amplification for graph ANN on append-only storage crosses practical thresholds at identifiable rewrite intensity
- **Novelty**: 9/10 — CONFIRMED (zero prior work)
- **Reviewer score**: Sig 8, Nov 7, Feas 8 (Paper A standalone)
- **Refine score**: 6.4/10 after 3 rounds (converged; remaining issues = implementation details)
- **Feasibility**: LOW risk, 5-6 weeks, <35 CPU-hours, no GPU
- **Contribution**: First GC feasibility analysis + controlled skewness effect
- **Key data**: Gini = 0.035 (DGAI 50K) to 0.290 (OdinANN 400K); ρ = 1.04 to 5.00
- **Pilot result**: M3 data already shows clear regime transition in page-rewrite patterns
- **Venue**: EuroSys 2027 or FAST 2027 short paper
- **Refined proposal**: `refine-logs/FINAL_PROPOSAL.md`
- **Experiment plan**: `refine-logs/EXPERIMENT_PLAN.md`

### Idea 2: PageTxn-ANN — BACKUP (REVISE needed)

- **Hypothesis**: Multi-page transactional crash recovery for disk graph ANN, with navigability preservation guarantee
- **Novelty**: 8/10 — CONFIRMED (zero disk-resident crash-consistent ANN)
- **Reviewer score**: Sig 7, Nov 4, Feas 7 — "just WAL" novelty risk
- **Risk**: MEDIUM — needs formalization of what makes graph ANN crash recovery unique (multi-page atomicity, navigability preservation under partial failure)
- **Venue**: FAST 2027
- **Status**: Needs 2-3 months of theoretical work on crash recovery protocol

### Idea 3: ZoneEpoch-ANN — DEFERRED (depends on Idea 1)

- **Hypothesis**: Navigability-constrained zone reclamation reduces GC WA by 3-5× vs naive append
- **Novelty**: 10/10 — CONFIRMED (absolute zero prior ZNS + graph ANN)
- **Reviewer score**: Sig 8, Nov 7, Feas 3 (system build) — navigability certificate undefined
- **Risk**: HIGH — 3-4 months, depends on Idea 1 showing feasibility
- **Venue**: FAST 2027
- **Status**: Proceed only if Idea 1 shows tractable regime

### Idea 4: FreshCert — REDUCED (REVISE needed)

- **Hypothesis**: Per-query freshness certificate for streaming graph ANN without graph repair
- **Novelty**: 6/10 — REDUCED (INSQ safe-region paradigm exists)
- **Reviewer score**: Sig 7, Nov 5, Feas 6, Venue 4 — logical gap in certificate claim
- **Risk**: MEDIUM — needs narrowing to conditional certificate, venue pivot to VLDB
- **Venue**: VLDB 2027 (pivoted from NeurIPS)

### Idea 5: Selectivity Is Not Enough — VIABLE BACKUP

- **Novelty**: 7/10 — CONFIRMED
- **Not reviewed in Phase 4**
- **Venue**: VLDB experiment track

---

## Eliminated Ideas

| Idea | Phase Eliminated | Reason |
|------|-----------------|--------|
| GraphKV | Phase 3 (novelty) | KVDrive (2026) already does SSD KV retrieval with index |
| Block-Probe Navigability | Phase 3 (novelty) | PODS 2020 has I/O kNN lower bounds |
| Summary-Bit/Probe LB | Phase 3 (novelty) | Same PODS 2020 issue |
| AttentionLoop-SSD | Phase 3 (deferred) | Depends on SSD KV system |
| Dynamic Vamana write optimization | Pre-pipeline | Novelty 2/10 |
| ContractANN | Pre-pipeline | KILLED |
| Page-cost-aware navigability | Pre-pipeline | KILLED |
| Learned repair oracle | Pre-pipeline | KILLED |
| Self-improving graph ANN | Pre-pipeline | KILLED |
| Non-uniform degree | Pre-pipeline | KILLED |
| Amortized maintenance | Pre-pipeline | KILLED |

---

## Refined Proposal (Top Idea)
- Proposal: `refine-logs/FINAL_PROPOSAL.md`
- Experiment plan: `refine-logs/EXPERIMENT_PLAN.md`
- Tracker: `refine-logs/EXPERIMENT_TRACKER.md`
- Pipeline summary: `refine-logs/PIPELINE_SUMMARY.md`

---

## Suggested Execution Order

1. **Start now**: Idea 1 (ANN-on-ZNS Feasibility, 5-6 weeks) — lowest risk, M3 data ready
2. **If Idea 1 positive**: Idea 3 (ZoneEpoch-ANN, 3-4 months) — full ZNS system
3. **If Idea 1 negative**: Idea 2 (PageTxn-ANN, 3 months) — pivot to crash consistency
4. **Parallel theory**: Idea 4 (FreshCert) — needs repositioning, lower priority
5. **Opportunistic**: Idea 5 (Selectivity) — clean VLDB contribution

## Next Steps
- [ ] Re-instrument M3 trace emission (2 days)
- [ ] FEMU smoke test (1 day)
- [ ] Re-collect 8 traces
- [ ] Implement zone-packing simulator
- [ ] Execute B1-B4 per EXPERIMENT_PLAN.md
- [ ] Paper writing (weeks 5-6)
